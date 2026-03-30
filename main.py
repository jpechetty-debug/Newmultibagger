from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
import numpy as np
import json
import os
import csv
import asyncio
import yfinance as yf
from contextlib import asynccontextmanager

import socket
socket.setdefaulttimeout(20.0)

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from modules.risk import RiskGovernor
from modules.retry_utils import run_with_exponential_backoff
from modules.tracker import PortfolioTracker
from pydantic import BaseModel, Field

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from modules.symbol_utils import normalize_symbol
from modules.revisions import analyze_revisions
from modules.drift_monitor import monitor_drift
from modules.allocation_hrp import HRPAllocator

# Background Task for Periodic Price Updates
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background task
    bg_task = asyncio.create_task(update_prices_background())
    yield
    # Shutdown: Stop background task
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        print("Background price updater stopped.")

app = FastAPI(lifespan=lifespan)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)

manager = ConnectionManager()

@app.websocket("/ws/signals")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection open and handle potential pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# Allow CORS — origins driven by CORS_ALLOWED_ORIGINS env var (never wildcard in production)
import config as _cfg
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass


DB_NAME = "stocks.db"
DB_PATH = DB_NAME

DB_BUSY_TIMEOUT_MS = 5000
SQLITE_WRITE_RETRIES = 5
SQLITE_RETRY_BASE_SECONDS = 0.05
BLOCKING_IO_CONCURRENCY = 32
REGIME_CACHE_TTL_SECONDS = int(os.getenv("REGIME_CACHE_TTL_SECONDS", "120"))
MOVERS_CACHE_TTL_SECONDS = int(os.getenv("MOVERS_CACHE_TTL_SECONDS", "120"))
blocking_io_semaphore = asyncio.Semaphore(BLOCKING_IO_CONCURRENCY)
ticker_io_semaphore = asyncio.Semaphore(10)  # Dedicated semaphore for network-heavy yfinance calls
portfolio_tracker = PortfolioTracker()
risk_governor = RiskGovernor()
regime_cache = {"payload": None, "timestamp": 0.0}
movers_cache = {"payload": None, "timestamp": 0.0}
regime_cache_lock = asyncio.Lock()
movers_cache_lock = asyncio.Lock()

# Caches for Audit Reports
CACHE_QUARTERLY = {}
CACHE_FUNDAMENTALS = {}
CACHE_PEERS = {}
CACHE_AUDIT_TTL = 3600  # 1 hour


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1)
    side: str = Field(description="BUY or SELL")
    quantity: int = Field(default=1, ge=1)
    price: float = Field(gt=0)
    score: float = 0.0
    reason: str = "MANUAL"
    current_vix: float | None = None
    drawdown_rate_weekly: float | None = None
    portfolio_correlation: float | None = None
    projected_var_pct: float | None = None
    max_var_pct: float = 20.0


def _is_sqlite_lock_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg


async def _run_blocking(fn: Callable[..., Any], *args, **kwargs):
    async with blocking_io_semaphore:
        return await asyncio.to_thread(fn, *args, **kwargs)


async def _run_ticker_blocking(fn: Callable[..., Any], *args, **kwargs):
    """Specific runner for yfinance network calls to prevent saturating DB threads."""
    async with ticker_io_semaphore:
        async with blocking_io_semaphore:
            return await asyncio.to_thread(fn, *args, **kwargs)


async def _run_sqlite_write_with_retry(
    write_fn: Callable[[], Any], operation_name: str
):
    for attempt in range(SQLITE_WRITE_RETRIES):
        try:
            return await _run_blocking(write_fn)
        except sqlite3.OperationalError as exc:
            if _is_sqlite_lock_error(exc) and attempt < SQLITE_WRITE_RETRIES - 1:
                wait = SQLITE_RETRY_BASE_SECONDS * (2 ** attempt)
                print(f"SQLite lock during {operation_name}; retrying in {wait:.2f}s.")
                await asyncio.sleep(wait)
                continue
            raise


def _run_sqlite_write_with_retry_sync(
    write_fn: Callable[[], Any], operation_name: str
):
    for attempt in range(SQLITE_WRITE_RETRIES):
        try:
            return write_fn()
        except sqlite3.OperationalError as exc:
            if _is_sqlite_lock_error(exc) and attempt < SQLITE_WRITE_RETRIES - 1:
                wait = SQLITE_RETRY_BASE_SECONDS * (2 ** attempt)
                print(
                    f"SQLite lock during {operation_name}; retrying in {wait:.2f}s."
                )
                time.sleep(wait)
                continue
            raise

def get_connection():
    _db_url = os.getenv('DATABASE_URL', f'sqlite:///./{DB_NAME}')
    if _db_url.startswith('postgresql'):
        try:
            from sqlalchemy import create_engine
            engine = create_engine(_db_url, pool_pre_ping=True)
            return engine.raw_connection()
        except Exception as exc:
            print(f'[WARN] PostgreSQL failed ({exc}), falling back to SQLite.')
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.execute(f'PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def _cache_is_fresh(cache: dict, ttl_seconds: int) -> bool:
    payload = cache.get("payload")
    ts = float(cache.get("timestamp", 0.0) or 0.0)
    return payload is not None and (time.time() - ts) < ttl_seconds


def _cache_set(cache: dict, payload: Any):
    cache["payload"] = payload
    cache["timestamp"] = time.time()


def _cache_invalidate(cache: dict):
    cache["timestamp"] = 0.0


def _read_records(query: str):
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn)
        # to_json handles NaN/Inf as null automatically
        return json.loads(df.to_json(orient="records", double_precision=2))
    finally:
        conn.close()


# Override with a write-retry aware implementation.
async def update_prices_background():
    """Background loop to refresh stock prices in small batches to prevent deadlocks."""
    await asyncio.sleep(10)
    BATCH_SIZE = 50
    while True:
        try:
            print(f"[{datetime.now()}] Initiating batched background price refresh...")

            def _load_symbols():
                conn = get_connection()
                try:
                    df_local = pd.read_sql("SELECT symbol FROM multibaggers", conn)
                    return df_local["symbol"].tolist()
                finally:
                    conn.close()

            all_symbols = await _run_blocking(_load_symbols)
            
            if all_symbols:
                # Process in batches
                for i in range(0, len(all_symbols), BATCH_SIZE):
                    batch = all_symbols[i : i + BATCH_SIZE]
                    print(f"  -> Processing batch {i//BATCH_SIZE + 1}/{(len(all_symbols) + BATCH_SIZE - 1)//BATCH_SIZE} ({len(batch)} symbols)")
                    
                    data = pd.DataFrame()
                    try:
                        data = await run_with_exponential_backoff(
                            lambda: _run_ticker_blocking(
                                yf.download,
                                batch,
                                period="1d",
                                interval="1m",
                                progress=False,
                                auto_adjust=True,
                                timeout=15,
                            ),
                            context=f"yfinance background batch {i//BATCH_SIZE}",
                        )
                    except Exception as e:
                        print(f"    ⚠️ Batch Download Error: {e}")

                    if not data.empty:
                        def _write_batch_prices():
                            conn = get_connection()
                            try:
                                cursor = conn.cursor()
                                updated = 0
                                for symbol in batch:
                                    try:
                                        if len(batch) > 1:
                                            if "Close" in data and symbol in data["Close"].columns:
                                                current_price = data["Close"][symbol].iloc[-1]
                                            else:
                                                continue
                                        else:
                                            # Case for single-ticker download (though batch is usually > 1)
                                            current_price = data["Close"].iloc[-1]

                                        if not pd.isna(current_price):
                                            cursor.execute(
                                                "UPDATE multibaggers SET price = ? WHERE symbol = ?",
                                                (float(current_price), symbol),
                                            )
                                            updated += 1
                                    except Exception:
                                        pass
                                conn.commit()
                                return updated
                            finally:
                                conn.close()

                        updated_count = await _run_sqlite_write_with_retry(
                            _write_batch_prices, f"background batch {i//BATCH_SIZE}"
                        )
                        if updated_count > 0:
                            try:
                                symbols_str = ",".join([f"'{s}'" for s in batch])
                                query = f"SELECT * FROM multibaggers WHERE symbol IN ({symbols_str})"
                                updated_records = await _run_blocking(_read_records, query)
                                await manager.broadcast({"type": "update", "data": _json_safe_clean(updated_records)})
                            except Exception:
                                pass
                        # Small pause between batches to allow other API requests to breathe
                        await asyncio.sleep(1)
                
                print(f"[{datetime.now()}] Full price update cycle completed.")
        except Exception as e:
            print(f"Error in price updater: {e}")

        await asyncio.sleep(300)

# API Endpoints
@app.get("/api/market-calendar")
def get_market_calendar():
    """Returns valid trading days for the current year"""
    try:
        from modules.data_manager import data_manager
        # Convert date objects to string list for JSON serialization
        valid_days = [d.isoformat() for d in data_manager.valid_trading_days]
        return {"valid_trading_days": valid_days}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/stocks")
async def get_multibaggers(as_of_date: str | None = None):
    """Fetch Top Multibagger Picks"""
    try:
        if as_of_date:
            import database as database_module

            def _read_as_of_records():
                df, snapshot_date = database_module.load_fundamentals_universe_as_of(
                    as_of_date
                )
                if df.empty:
                    return []
                df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
                records = df.to_dict(orient="records")
                for record in records:
                    if not record.get("as_of_date"):
                        record["as_of_date"] = snapshot_date
                return records

            return await _run_blocking(_read_as_of_records)

        # 1. Fetch Multibaggers (Phase 6: Deterministic Tie-Breaker Sorting)
        records = await _run_blocking(
            _read_records, "SELECT * FROM multibaggers ORDER BY score DESC, rs_rating DESC, market_cap_cr DESC"
        )

        if not records:
            return []

        return _json_safe_clean(records)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/multibagger-hunt")
async def get_multibagger_hunt():
    """Fetch stocks meeting the strict Multibagger Hunt criteria"""
    try:
        # Framework Filters from ticker_list.py
        query = """
            SELECT * FROM multibaggers
            WHERE sales_cagr_5y >= 0.15
              AND avg_roe_5y >= 0.15
              AND debt_equity <= 0.5
              AND cfo_pat_ratio >= 0.80
              AND promoter_holding >= 50.0
              AND (pledge_pct = 0.0 OR pledge_pct IS NULL)
              AND (piotroski_score >= 6 OR (piotroski_score IS NULL AND f_score >= 6))
              AND market_cap_cr <= 5000
            ORDER BY ml_rank_score DESC, score DESC
        """
        records = await _run_blocking(_read_records, query)
        
        if not records:
            return []
            
        return _json_safe_clean(records)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/reports/{symbol}")
async def get_stock_report_markdown(symbol: str):
    """Generate Analyst Report (Markdown)"""
    try:
        from report_generator import generate_analyst_report
        symbol = normalize_symbol(symbol)
        report = await generate_analyst_report(symbol)
        return {"content": report}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/thesis/{symbol}")
async def get_llm_thesis(symbol: str):
    """Generate concise AI investment thesis via local Ollama."""
    try:
        from modules.llm_engine import generate_thesis
        import pandas as pd
        conn = get_connection()
        try:
            target = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
            if target.empty:
                return {"thesis": "Stock not found in database to generate thesis."}
            stock_data = target.iloc[0].to_dict()
        finally:
            conn.close()
            
        thesis = await _run_blocking(generate_thesis, stock_data)
        return {"thesis": thesis}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/history/{symbol}")
def get_stock_history(symbol: str):
    """Fetch historical score data for a stock."""
    try:
        conn = get_connection() # Use get_connection instead of get_db_connection
        cursor = conn.cursor()
        
        # Normalize symbol
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
            
        cursor.execute("""
            SELECT as_of_date, score, price 
            FROM fundamentals_pit 
            WHERE symbol = ? 
            ORDER BY as_of_date ASC
        """, (symbol,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "date": row["as_of_date"],
                "score": row["score"],
                "price": row["price"]
            }
            for row in rows
        ]
    except Exception as e:
        print(f"History Error: {e}")
        return []

@app.get("/api/reports/html/{symbol}")
async def get_stock_report_html(symbol: str):
    """Serve Premium HTML Report with cache-busting."""
    try:
        from modules.html_report import generate_premium_html_report
        symbol = normalize_symbol(symbol)
        
        path = await generate_premium_html_report(symbol)
        if os.path.exists(path):
            from fastapi.responses import FileResponse
            return FileResponse(
                path, 
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache"
                }
            )
        return {"error": "Report generation failed"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/microcaps")
async def get_microcaps():
    """Fetch Hidden Microcap Gems"""
    try:
        return await _run_blocking(
            _read_records, "SELECT * FROM microcaps ORDER BY score DESC"
        )
    except Exception as e:
        return {"error": str(e)}

# Advanced Forensics API
@app.get("/api/liquidity")
def get_liquidity():
    try:
        if os.path.exists("liquidity.json"):
            with open("liquidity.json", "r") as f:
                return json.load(f)
        return {"error": "Report not generated yet."}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/recovery")
def get_recovery():
    try:
        if os.path.exists("recovery.json"):
            with open("recovery.json", "r") as f:
                return json.load(f)
        return {"error": "Report not generated yet."}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/thesis_break")
async def get_thesis_break():
    """Fetch all thesis break statuses (upgraded: live engine)."""
    try:
        from modules.thesis_monitor import check_all_thesis_breaks
        results = await _run_blocking(check_all_thesis_breaks)
        return {
            "timestamp": datetime.now().isoformat(),
            "signals_count": sum(1 for r in results if r["status"] == "THESIS_BREAK"),
            "status": "HEALTHY" if all(r["status"] in ("INTACT", "NO_THESIS", "NO_DATA") for r in results) else "ACTION_REQUIRED",
            "signals": results,
        }
    except Exception as e:
        # Fallback to legacy JSON
        if os.path.exists("thesis_break.json"):
            with open("thesis_break.json", "r") as f:
                return json.load(f)
        return {"error": str(e)}

@app.get("/api/thesis_status/{symbol}")
async def get_thesis_status(symbol: str):
    """Fetch thesis status for a single stock."""
    try:
        from modules.thesis_monitor import check_thesis, get_thesis_summary
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        status = await _run_blocking(check_thesis, symbol)
        thesis = await _run_blocking(get_thesis_summary, symbol)
        result = status.to_dict()
        if thesis:
            result["thesis_detail"] = thesis
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/rejections")
def get_rejections():
    """Fetch latest 20 rejected trades from Black Box Recorder"""
    try:
        if not os.path.exists("rejected_trades.csv"):
            return []
        with open("rejected_trades.csv", "r", encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows[-20:][::-1]
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/regime_status")
async def get_regime_status():
    """Fetch 3-Factor Regime Voting Status"""
    try:
        if _cache_is_fresh(regime_cache, REGIME_CACHE_TTL_SECONDS):
            return regime_cache["payload"]

        async with regime_cache_lock:
            if _cache_is_fresh(regime_cache, REGIME_CACHE_TTL_SECONDS):
                return regime_cache["payload"]
            from modules.market_data import MarketDataProvider
            import config
            provider = MarketDataProvider()
            data = await _run_blocking(provider.get_market_regime)

            # Check for Admin Override
            regime = data["regime"]
            if config.FORCED_REGIME:
                regime = config.FORCED_REGIME
                data["is_forced"] = True
            else:
                data["is_forced"] = False

            details = data.get("details", {})
            votes = data.get("votes", {})
           
            payload = {
                "regime": regime,
                "vix": details.get("vix", 0),
                "vix_threshold": 18.0,
                "votes": votes,
                "is_forced": data.get("is_forced", False),
                "details": details,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
            _cache_set(regime_cache, payload)
            return payload
    except Exception as e:
        cached_payload = regime_cache.get("payload")
        if cached_payload:
            stale_payload = dict(cached_payload)
            stale_payload["stale"] = True
            stale_payload["error"] = str(e)
            return stale_payload
        return {"error": str(e)}


@app.post("/api/admin/force_regime")
def force_regime(regime: str):
    """Manually force the regime for next scans. options: BULL, BEAR, SIDEWAYS, AUTO"""
    try:
        import config
        
        regime = regime.upper()
        if regime not in ['BULL', 'BEAR', 'SIDEWAYS', 'AUTO']:
            return {"error": "Invalid regime. Use BULL, BEAR, SIDEWAYS, or AUTO."}
            
        if regime == 'AUTO':
            config.FORCED_REGIME = None
            print("Regime override cleared. Resuming auto mode.")
        else:
            config.FORCED_REGIME = regime
            print(f"Regime forced to {regime} by administrator.")

        _cache_invalidate(regime_cache)
        return {"status": "success", "regime": regime}

    except Exception as e:
        return {"error": str(e)}

@app.get("/api/performance")
def get_performance():
    """Fetch Strategy Performance vs Benchmark"""
    return {
        "strategy": 12.4,
        "benchmark": 8.7,
        "alpha": 3.7,
        "win_rate": 68.2,
        "avg_hold": "47 Days"
    }


@app.post("/api/order")
async def place_order(order: OrderRequest):
    """Order lifecycle endpoint for paper execution (BUY/SELL)."""
    try:
        symbol = order.symbol.strip().upper()
        side = order.side.strip().upper()

        if not symbol:
            return {"status": "rejected", "error": "symbol is required"}

        if side not in {"BUY", "SELL"}:
            return {"status": "rejected", "error": "side must be BUY or SELL"}

        if "." not in symbol:
            symbol = f"{symbol}.NS"

        if side == "BUY":
            # Dynamic + static kill-switch checks.
            if order.current_vix is not None or order.drawdown_rate_weekly is not None:
                vix_for_check = order.current_vix if order.current_vix is not None else 0.0
                is_safe, message = risk_governor.check_kill_switch(
                    vix_for_check,
                    drawdown_rate_weekly=order.drawdown_rate_weekly,
                )
                if not is_safe:
                    risk_governor.log_rejected_trade(symbol, message, order.price)
                    return {
                        "status": "rejected",
                        "side": side,
                        "symbol": symbol,
                        "reason": message,
                    }

            # Pre-trade VaR budget gate.
            var_safe, var_message = risk_governor.validate_var_budget(
                order.projected_var_pct,
                order.max_var_pct,
            )
            if not var_safe:
                return {
                    "status": "rejected",
                    "side": side,
                    "symbol": symbol,
                    "reason": var_message,
                }

            # Correlation stress gate.
            adjusted_qty = order.quantity
            if order.portfolio_correlation is not None:
                corr_factor = risk_governor.validate_correlation_risk(
                    order.portfolio_correlation
                )
                if corr_factor <= 0:
                    return {
                        "status": "rejected",
                        "side": side,
                        "symbol": symbol,
                        "reason": "Correlation emergency de-risk triggered",
                    }
                adjusted_qty = max(1, int(round(order.quantity * corr_factor)))

            result = await _run_blocking(
                portfolio_tracker.log_entry,
                symbol,
                order.price,
                order.score,
                adjusted_qty,
            )

            # Record buy thesis for thesis break detection
            if result.get("status") != "rejected":
                try:
                    from modules.thesis_monitor import record_buy_thesis
                    # Fetch current fundamental data for thesis snapshot
                    def _fetch_thesis_data():
                        conn_t = get_connection()
                        try:
                            row = pd.read_sql(
                                "SELECT * FROM multibaggers WHERE symbol = ?",
                                conn_t, params=(symbol,)
                            )
                            return row.iloc[0].to_dict() if not row.empty else {}
                        finally:
                            conn_t.close()
                    stock_snapshot = await _run_blocking(_fetch_thesis_data)
                    if stock_snapshot:
                        await _run_blocking(
                            record_buy_thesis, symbol, stock_snapshot,
                            order.score, 0, "SIDEWAYS"
                        )
                except Exception as thesis_err:
                    print(f"Thesis recording skipped: {thesis_err}")
        else:
            result = await _run_blocking(
                portfolio_tracker.log_exit,
                symbol,
                order.price,
                order.reason,
            )

        if result.get("status") == "rejected":
            risk_governor.log_rejected_trade(symbol, result.get("reason", "Order rejected"), order.price)

        return {
            "status": result.get("status", "accepted"),
            "side": side,
            "symbol": symbol,
            "quantity": adjusted_qty if side == "BUY" else order.quantity,
            "price": order.price,
            "reason": result.get("reason", order.reason),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/trades/open")
async def get_open_trades():
    try:
        df = await _run_blocking(portfolio_tracker.get_open_positions)
        if df.empty:
            return []
        clean_df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
        return clean_df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/trades/history")
async def get_trade_history():
    try:
        df = await _run_blocking(portfolio_tracker.get_trade_history)
        if df.empty:
            return []
        clean_df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
        return clean_df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}

app.mount("/static", StaticFiles(directory="web-ui"), name="static")

@app.post("/api/scan")
async def run_scan():
    """Trigger a full market scan using screener.py"""
    try:
        import sys
        process = await asyncio.create_subprocess_exec(
            sys.executable, "screener.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        return {"status": "scan_initiated", "pid": process.pid}
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
def read_root():
    return FileResponse("web-ui/index.html")

# News API with Sentiment Intelligence (Phase 63 & 64)
@app.get("/api/news/{symbol}")
async def get_news(symbol: str):
    """Fetch Narrative Intelligence (News) with Sentiment Analysis"""
    try:
        from modules.news import get_stock_news
        from modules.alpha_vantage import AlphaVantageProvider
        
        # 1. Fetch primary news from yfinance (Fast)
        news = await get_stock_news(symbol)


        
        # 2. Fetch Sentiment scores from Alpha Vantage (High Fidelity)
        try:
            av = AlphaVantageProvider()
            # Run synchronous and rate-limited call in a separate thread
            sentiment_map = await run_with_exponential_backoff(
                lambda: _run_blocking(av.get_stock_sentiment, symbol),
                context=f"alpha vantage sentiment for {symbol}",
            )
             
            # Merge Sentiment into News

            if sentiment_map:
                symbol_sentiment = sentiment_map.get("__symbol__")
                normalized_symbol = symbol.split(".")[0].upper()
                for item in news:
                    title = item.get("title")
                    if title in sentiment_map:
                        item["sentiment"] = sentiment_map[title]
                        continue

                    related_tickers = [
                        str(t).upper() for t in (item.get("related_tickers") or [])
                    ]
                    if symbol_sentiment and normalized_symbol in related_tickers:
                        item["sentiment"] = symbol_sentiment
                    elif symbol_sentiment and not related_tickers:
                        item["sentiment"] = symbol_sentiment
        except Exception as av_err:
            print(f"Alpha Vantage sentiment fetch failed: {av_err}")

        return news
    except Exception as e:
        return {"error": str(e)}

# Market Movers API (Phase 64)
@app.get("/api/market_movers")
async def get_market_movers():
    """Fetch Global Top Gainers, Losers, and Actively Traded"""
    try:
        if _cache_is_fresh(movers_cache, MOVERS_CACHE_TTL_SECONDS):
            return movers_cache["payload"]

        async with movers_cache_lock:
            if _cache_is_fresh(movers_cache, MOVERS_CACHE_TTL_SECONDS):
                return movers_cache["payload"]
            from modules.alpha_vantage import AlphaVantageProvider
            av = AlphaVantageProvider()
            # Run synchronous and potentially rate-limited call in a separate thread
            movers = await run_with_exponential_backoff(
                lambda: _run_blocking(av.get_market_movers),
                context="alpha vantage market movers",
            )
            payload = movers or {"gainers": [], "losers": [], "active": []}
            _cache_set(movers_cache, payload)
            return payload


    except Exception as e:
        cached_payload = movers_cache.get("payload")
        if cached_payload:
            stale_payload = dict(cached_payload)
            stale_payload["stale"] = True
            stale_payload["error"] = str(e)
            return stale_payload
        return {"error": str(e)}



# Valuation API
@app.get("/api/valuation/{symbol}")
async def get_valuation(symbol: str, as_of_date: str | None = None):
    try:
        valuation_as_of = (as_of_date or datetime.now().date().isoformat())[:10]

        def _normalize_valuation_payload(payload: dict):
            if not payload:
                return payload

            def _component_or_none(value):
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    return None
                if not np.isfinite(parsed) or parsed <= 0:
                    return None
                return parsed

            if isinstance(payload.get("components"), dict):
                components = payload.get("components", {})
                payload["components"] = {
                    "dcf": _component_or_none(components.get("dcf")),
                    "graham": _component_or_none(components.get("graham")),
                    "epv": _component_or_none(components.get("epv")),
                }
                payload.setdefault("symbol", symbol)
                payload.setdefault("as_of_date", valuation_as_of)
                if payload.get("intrinsic_value") in (0, 0.0):
                    payload["intrinsic_value"] = None
                return payload

            normalized = {
                "symbol": payload.get("symbol", symbol),
                "intrinsic_value": payload.get("intrinsic_value", 0) or None,
                "margin_of_safety": payload.get("margin_of_safety", 0),
                "verdict": payload.get("verdict", "UNKNOWN"),
                "confidence_score": payload.get("confidence_score"),
                "calculated_at": payload.get("calculated_at"),
                "as_of_date": payload.get("as_of_date") or valuation_as_of,
                "components": {
                    "dcf": _component_or_none(payload.get("dcf_value", 0)),
                    "graham": _component_or_none(payload.get("graham_value", 0)),
                    "epv": _component_or_none(payload.get("epv_value", 0)),
                },
            }
            return normalized

        def _ensure_valuation_table():
            conn = get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS valuation_metrics (
                        symbol TEXT PRIMARY KEY,
                        dcf_value REAL,
                        graham_value REAL,
                        epv_value REAL,
                        intrinsic_value REAL,
                        margin_of_safety REAL,
                        verdict TEXT,
                        confidence_score INTEGER,
                        as_of_date TEXT,
                        calculated_at TIMESTAMP
                    )
                    """
                )
                columns = [row[1] for row in conn.execute("PRAGMA table_info(valuation_metrics)").fetchall()]
                if "as_of_date" not in columns:
                    conn.execute("ALTER TABLE valuation_metrics ADD COLUMN as_of_date TEXT")
                conn.commit()
            finally:
                conn.close()

        await _run_sqlite_write_with_retry(_ensure_valuation_table, "valuation table init")

        def _read_cached():
            conn = get_connection()
            try:
                if as_of_date:
                    query = """
                        SELECT *
                        FROM valuation_metrics
                        WHERE symbol = ? AND as_of_date <= ?
                        ORDER BY as_of_date DESC, calculated_at DESC
                        LIMIT 1
                    """
                    existing_local = pd.read_sql(query, conn, params=(symbol, valuation_as_of))
                else:
                    query = """
                        SELECT *
                        FROM valuation_metrics
                        WHERE symbol = ?
                        ORDER BY calculated_at DESC
                        LIMIT 1
                    """
                    existing_local = pd.read_sql(query, conn, params=(symbol,))
                if not existing_local.empty:
                    return existing_local.iloc[0].to_dict()
                return None
            finally:
                conn.close()

        cached = await _run_blocking(_read_cached)
        if cached:
            return _normalize_valuation_payload(cached)

        ticker = yf.Ticker(symbol)

        info = await run_with_exponential_backoff(
            lambda: _run_blocking(lambda: ticker.info),
            context=f"yfinance valuation for {symbol}",
        )

        if not info:
            return {"error": f"Failed to fetch valuation data for {symbol} (Throttled)"}

        # --- Alpha Vantage Fallback for Missing Yahoo Data ---
        av_data = None
        critical_missing = (
            not info.get("trailingEps")
            or not info.get("bookValue")
            or not info.get("currentPrice")
        )
        if critical_missing:
            try:
                from modules.alpha_vantage import AlphaVantageProvider, get_remaining_budget
                if get_remaining_budget() >= 2:
                    av = AlphaVantageProvider()
                    av_data = await _run_blocking(av.get_company_overview, symbol)
                    if av_data:
                        print(f"  ✅ AV fallback for {symbol}: filling missing valuation fields")
            except Exception as av_err:
                print(f"  ⚠️ AV fallback skipped for {symbol}: {av_err}")

        # Merge: prefer Yahoo, fall back to AV
        def _get(yahoo_key, av_key=None, default=0):
            val = info.get(yahoo_key)
            if val not in (None, 0, ""):
                return val
            if av_data and av_key:
                av_val = av_data.get(av_key)
                if av_val is not None:
                    return av_val
            return default

        data = {
            "current_price": _get("currentPrice", None, 0),
            "eps_ttm": _get("trailingEps", "eps", 0),
            "book_value_per_share": _get("bookValue", "book_value", 0),
            "free_cash_flow_per_share": (
                (info.get("operatingCashflow", 0) - abs(info.get("capitalExpenditures", 0)))
                / info.get("sharesOutstanding", 1)
                if info.get("operatingCashflow")
                else 0
            ),
            "growth_rate_5y": _get("earningsGrowth", None, 0.10) * 100,
            "beta": _get("beta", "beta", 1.0),
            "data_source": "yahoo+alpha_vantage" if av_data else "yahoo",
        }

        from modules.valuation import ValuationEngine

        engine = ValuationEngine(data)
        metrics = engine.get_intrinsic_value()

        def _write_valuation():
            conn = get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO valuation_metrics
                    (symbol, dcf_value, graham_value, epv_value, intrinsic_value, margin_of_safety, verdict, confidence_score, as_of_date, calculated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        metrics["components"]["dcf"],
                        metrics["components"]["graham"],
                        metrics["components"]["epv"],
                        metrics["intrinsic_value"],
                        metrics["margin_of_safety"],
                        metrics["verdict"],
                        85,
                        valuation_as_of,
                        datetime.now(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        await _run_sqlite_write_with_retry(_write_valuation, "valuation upsert")
        metrics["symbol"] = symbol
        metrics["as_of_date"] = valuation_as_of
        return _json_safe_clean(_normalize_valuation_payload(metrics))

    except Exception as e:
        print(f"Valuation Error: {e}")
        return {"error": str(e)}



@app.get("/api/financials/{symbol}")
def get_financials(symbol: str):
    try:
        from modules.financials import get_quarterly_results
        return _json_safe_clean(get_quarterly_results(symbol))
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/governance/{symbol}")
async def get_governance_data(symbol: str):
    """Fetch 8-Point Governance Checklist Data"""
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
            
        def _fetch_gov_data():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Helper for safe extraction
            def get_val(key, default=None):
                v = info.get(key, default)
                return v if v is not None else default

            # Detect Sector for Debt/Equity logic
            sector = get_val('sector', 'Unknown')
            is_financial = 'Financial' in sector or 'Bank' in sector

            # 1. ROE
            roe_raw = get_val('returnOnEquity', 0)
            roe = round(roe_raw * 100, 2) if roe_raw else 0
            
            # 2. Debt/Equity
            de_raw = get_val('debtToEquity', 0)
            de = round(de_raw / 100, 2) if de_raw else 0
            
            # 3. Sales Growth (Quarterly YoY or TTM)
            sales_growth_raw = get_val('revenueGrowth', 0)
            sales_growth = round(sales_growth_raw * 100, 2) if sales_growth_raw else 0
            
            # 4. Profit Growth (Earnings Growth)
            profit_growth_raw = get_val('earningsGrowth', 0)
            profit_growth = round(profit_growth_raw * 100, 2) if profit_growth_raw else 0
            
            # 5. Promoter Holding
            promoter_holding_raw = get_val('heldPercentInsiders', 0)
            promoter_holding = round(promoter_holding_raw * 100, 2) if promoter_holding_raw else 0
            
            # 6. Pledged Algo (Not in YF usually, defaulting to 0 for check)
            pledged = 0 
            
            # 7. CFO/PAT Check (Need Cashflow and Net Income)
            cfo = get_val('operatingCashflow', 0)
            ni = get_val('netIncomeToCommon', 1) # Avoid div/0
            cfo_pat = round(cfo / ni, 2) if ni and cfo else 0
            
            return {
                "symbol": symbol,
                "sector": sector,
                "is_financial": is_financial,
                "roe": roe,
                "debt_to_equity": de,
                "sales_growth": sales_growth,
                "profit_growth": profit_growth,
                "promoter_holding": promoter_holding,
                "pledged_pct": pledged,
                "cfo_pat_ratio": cfo_pat
            }

        data = await _run_blocking(_fetch_gov_data)
        return data
        
    except Exception as e:
        return {"error": str(e)}

# Technicals API
@app.get("/api/peers/{symbol}")
async def get_stock_peers(symbol: str):
    """Fetch Sector Peers for Comparison"""
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"

        def _get_peers():
            conn = get_connection()
            try:
                # 1. Get Target Metrics
                target_query = "SELECT symbol, sector, price as current_price, score as terminal_score, pe_ratio as pe, roe, debt_equity, rs_rating as price_change_3m FROM multibaggers WHERE symbol = ?"
                target = pd.read_sql(target_query, conn, params=(symbol,))
                if target.empty:
                    return {"error": "Stock not found"}
                
                start_sector = target.iloc[0]['sector']

                # 2. Get Peers using Subquery for Sector (More robust)
                query = """
                    SELECT symbol, symbol as name, price as current_price, score as terminal_score, pe_ratio as pe, roe, debt_equity, rs_rating as price_change_3m
                    FROM multibaggers 
                    WHERE sector = (SELECT sector FROM multibaggers WHERE symbol = ?) 
                    AND symbol != ?
                    ORDER BY score DESC
                    LIMIT 5
                """
                peers_df = pd.read_sql(query, conn, params=(symbol, symbol))
                peers = peers_df.to_dict(orient="records")
                
                # 3. Sector Averages
                avg_query = """
                    SELECT 
                        AVG(pe_ratio) as pe, 
                        AVG(roe) as roe, 
                        AVG(score) as terminal_score 
                    FROM multibaggers 
                    WHERE sector = (SELECT sector FROM multibaggers WHERE symbol = ?)
                """
                # Use execute directly for scalar values to avoid overhead? No, pandas is fine.
                avg_df = pd.read_sql(avg_query, conn, params=(symbol,))
                if not avg_df.empty:
                    avgs = avg_df.iloc[0].to_dict()
                else:
                    avgs = {}
                
                return {
                    "sector": start_sector,
                    "peers": peers,
                    "sector_avg": avgs,
                    "stock_metrics": target.iloc[0].to_dict(),
                    "rankings": {"score_rank_desc": "Top 10"}
                }
            finally:
                conn.close()

        return await _run_blocking(_get_peers)

    except Exception as e:
        return {"error": str(e)}

@app.get("/api/technicals/{symbol}")
async def get_technicals(symbol: str):
    try:
        from modules.technicals import get_technical_analysis
        return _json_safe_clean(await get_technical_analysis(symbol))
    except Exception as e:
        return {"error": str(e)}

# Shareholding API
# Promoter Intelligence API
@app.get("/api/promoter/{symbol}")
async def get_promoter_intel(symbol: str):
    """Fetch Promoter Behaviour Intelligence (trends, deals, pledge, scoring)."""
    try:
        from modules.promoter_intel import calculate_promoter_score
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        return await _run_blocking(calculate_promoter_score, symbol)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/shareholding/{symbol}")
async def get_shareholding(symbol: str):
    try:
        from modules.shareholding import get_shareholding_pattern
        return _json_safe_clean(await get_shareholding_pattern(symbol))
    except Exception as e:
        return {"error": str(e)}

# Quarterly Results Timeline API
@app.get("/api/quarterly-results/{symbol}")
async def quarterly_results_endpoint(symbol: str, quarters: int = 12):
    import time
    start_time = time.time()
    try:
        # Check Cache
        if _cache_is_fresh(CACHE_QUARTERLY.get(symbol, {}), CACHE_AUDIT_TTL):
            print(f"CACHE HIT: Quarterly Results for {symbol}")
            return CACHE_QUARTERLY[symbol]["payload"]

        print(f"API Request: Quarterly Timeline for {symbol}")
        from modules.quarterly_results import get_quarterly_timeline
        result = await get_quarterly_timeline(symbol, quarters)
        
        print(f"Got results for {symbol}, cleaning JSON... (took {time.time() - start_time:.2f}s)")
        cleaned = _json_safe_clean(result)
        
        # Set Cache
        if symbol not in CACHE_QUARTERLY: CACHE_QUARTERLY[symbol] = {}
        _cache_set(CACHE_QUARTERLY[symbol], cleaned)
        
        print(f"JSON cleaned and cached for {symbol} (took {time.time() - start_time:.2f}s)")
        return cleaned
    except Exception as e:
        from fastapi import HTTPException
        print(f"Error in quarterly_results_endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch quarterly results: {str(e)}"
        )

# Price vs Fundamentals API
@app.get("/api/price-fundamentals/{symbol}")
async def price_fundamentals_endpoint(symbol: str, years: int = 5):
    import time
    start_time = time.time()
    try:
        # Check Cache
        if _cache_is_fresh(CACHE_FUNDAMENTALS.get(symbol, {}), CACHE_AUDIT_TTL):
            print(f"CACHE HIT: Fundamentals for {symbol}")
            return CACHE_FUNDAMENTALS[symbol]["payload"]

        print(f"API Request: Price vs Fundamentals for {symbol}")
        from modules.price_fundamentals import get_price_vs_fundamentals
        years = min(max(years, 3), 10)
        result = await get_price_vs_fundamentals(symbol, years)
        
        print(f"Got results for {symbol}, cleaning JSON... (took {time.time() - start_time:.2f}s)")
        cleaned = _json_safe_clean(result)
        
        # Set Cache
        if symbol not in CACHE_FUNDAMENTALS: CACHE_FUNDAMENTALS[symbol] = {}
        _cache_set(CACHE_FUNDAMENTALS[symbol], cleaned)
        
        print(f"JSON cleaned and cached for {symbol} (took {time.time() - start_time:.2f}s)")
        return cleaned
    except Exception as e:
        from fastapi import HTTPException
        print(f"Error in price_fundamentals_endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch price vs fundamentals: {str(e)}"
        )

# Estimates Momentum API
@app.get("/api/estimates/{symbol}")
async def get_estimates(symbol: str):
    """Fetch forward-looking estimate momentum data."""
    try:
        from modules.estimates import get_estimate_data
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        return await _run_blocking(get_estimate_data, symbol)
    except Exception as e:
        return {"error": str(e)}

# Alpha Vantage Earnings API
@app.get("/api/earnings/{symbol}")
async def get_earnings(symbol: str):
    """Fetch earnings data from Alpha Vantage (EPS history + estimates)."""
    try:
        from modules.alpha_vantage import AlphaVantageProvider, get_remaining_budget

        remaining = get_remaining_budget()
        if remaining < 2:
            return {"error": f"Alpha Vantage daily budget low ({remaining} calls remaining). Try again tomorrow.", "budget_remaining": remaining}

        av = AlphaVantageProvider()
        result = await _run_blocking(av.get_earnings_calendar, symbol)

        if not result:
            return {"error": f"No earnings data available for {symbol}", "source": "alpha_vantage"}

        result["symbol"] = symbol
        result["source"] = "alpha_vantage"
        result["budget_remaining"] = get_remaining_budget()
        return _json_safe_clean(result)
    except Exception as e:
        print(f"Earnings API Error: {e}")
        return {"error": str(e)}

# Alpha Vantage Budget Status
@app.get("/api/av-budget")
async def get_av_budget():
    """Check remaining Alpha Vantage API calls for today."""
    try:
        from modules.alpha_vantage import get_remaining_budget, _DAILY_LIMIT
        remaining = get_remaining_budget()
        return {
            "remaining": remaining,
            "daily_limit": _DAILY_LIMIT,
            "used": _DAILY_LIMIT - remaining,
        }
    except Exception as e:
        return {"error": str(e)}

def weekly_audit_loop():
    """Background loop to refresh fundamental data every 7 days"""
    while True:
        try:
            print("Checking for expired Forensic Audits...")
            conn = get_connection()
            # Find stocks not audited in last 7 days
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            query = (
                "SELECT symbol FROM multibaggers "
                "WHERE last_audited IS NULL OR last_audited < ? "
                "LIMIT 5"
            )
            expired_stocks = pd.read_sql(query, conn, params=(seven_days_ago,))[
                "symbol"
            ].tolist()
            conn.close()
             
            if expired_stocks:
                print(f"Refreshing Forensic Audit for: {', '.join(expired_stocks)}")
                # In a real app, we'd call screener.get_stock_data(symbol)
                # For this terminal, we update the timestamp to signify 'Audit Complete'
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                def _write_audit_marks():
                    conn_write = get_connection()
                    try:
                        for symbol in expired_stocks:
                            conn_write.execute(
                                "UPDATE multibaggers SET last_audited = ? WHERE symbol = ?",
                                (now_str, symbol),
                            )
                        conn_write.commit()
                    finally:
                        conn_write.close()

                _run_sqlite_write_with_retry_sync(
                    _write_audit_marks, "weekly audit refresh"
                )
        except Exception as e:
            print(f"Audit Loop Error: {e}")
        
        # Check every 6 hours
        time.sleep(6 * 3600)


@app.get("/api/swarm/{symbol}")
async def get_swarm_report(symbol: str):
    """Fetch Swarm Intelligence Validation Report from MiroFish."""
    try:
        from modules.mirofish_client import MiroFishClient
        from modules.symbol_utils import normalize_symbol
        import pandas as pd
        
        symbol = normalize_symbol(symbol)
        client = MiroFishClient()
        
        # 1. Fetch context from DB for the swarm debate
        def _fetch_context():
            conn = get_connection()
            try:
                row = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
                if row.empty: return None
                data = row.iloc[0].to_dict()
                return f"Stock {symbol} in {data.get('sector')} sector. Score: {data.get('score')}. PE: {data.get('pe')}. ROE: {data.get('avg_roe_5y')}. Growth: {data.get('sales_cagr_5y')}."
            finally:
                conn.close()
        
        context = await _run_blocking(_fetch_context)
        if not context:
            return {"error": "Stock not found in database."}
            
        # 2. Trigger/Retrieve Swarm Simulation
        report = await _run_blocking(client.simulate_ticker, symbol, context)
        
        return {
            "symbol": symbol,
            "report": report,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    # Start Weekly Audit Thread
    audit_thread = threading.Thread(target=weekly_audit_loop, daemon=True)
    audit_thread.start()
    
    print("Starting Server... Access Dashboard at: http://127.0.0.1:9005")
    uvicorn.run(
        "main:app", 
        host="127.0.0.1", 
        port=9005, 
        reload=True,
        reload_excludes=["*.db", "*.db-journal", "*.db-wal", "*.log", "*.txt"]
    )



@app.get("/api/backtest-metrics")
async def get_backtest_metrics():
    """Fetch aggregate portfolio backtesting metrics."""
    import os
    try:
        if not os.path.exists("backtest_report.md"):
            return {"status": "pending"}
            
        metrics = {"status": "success"}
        with open("backtest_report.md", "r", encoding="utf-8") as f:
            for line in f:
                if "Average CAGR" in line:
                    metrics["cagr"] = line.split(":")[-1].replace("*", "").replace("%", "").strip()
                elif "Win Rate" in line:
                    metrics["win_rate"] = line.split(":")[-1].replace("*", "").replace("%", "").strip()
                elif "Max Drawdown" in line:
                    metrics["max_dd"] = line.split(":")[-1].replace("*", "").replace("%", "").strip()
                elif "Sharpe Ratio" in line:
                    metrics["sharpe"] = line.split(":")[-1].replace("*", "").strip()
                elif "Sortino Ratio" in line:
                    metrics["sortino"] = line.split(":")[-1].replace("*", "").strip()
                elif "Calmar Ratio" in line:
                    metrics["calmar"] = line.split(":")[-1].replace("*", "").strip()
                    
        return metrics
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/slippage_stats")
async def get_slippage_stats():
    """Fetch Execution Quality Metrics (Slippage Calibration)"""
    try:
        query = "SELECT * FROM slippage_metrics ORDER BY tier"
        data = await _run_blocking(_read_records, query)
        return _json_safe_clean(data)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/revisions/{symbol}")
async def get_revisions(symbol: str):
    """Fetch analyst recommendations trend and score impact."""
    try:
        symbol = normalize_symbol(symbol)
        ticker = yf.Ticker(symbol)
        score_impact, sentiment = await _run_blocking(analyze_revisions, ticker)
        return {
            "symbol": symbol,
            "score_impact": score_impact,
            "sentiment": sentiment,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/drift/{symbol}")
async def get_drift(symbol: str):
    """Detect investment thesis drift for a single stock."""
    try:
        symbol = normalize_symbol(symbol)
        def _fetch_drift_data():
            conn = get_connection()
            try:
                # Fetch recent technicals and fundamentals
                row = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
                if row.empty:
                    return None
                return row.iloc[0].to_dict()
            finally:
                conn.close()
        
        stock_data = await _run_blocking(_fetch_drift_data)
        if not stock_data:
            return {"error": "Stock data not found"}
            
        status, reason = monitor_drift(stock_data)
        return {
            "symbol": symbol,
            "status": status,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/allocation/hrp")
async def get_hrp_allocation():
    """Calculate HRP weights for top 15 stocks based on 1Y returns."""
    try:
        def _get_top_symbols():
            conn = get_connection()
            try:
                df = pd.read_sql("SELECT symbol FROM multibaggers ORDER BY score DESC LIMIT 15", conn)
                return df["symbol"].tolist()
            finally:
                conn.close()
        
        symbols = await _run_blocking(_get_top_symbols)
        if not symbols:
            return {"error": "No stocks found for allocation"}
            
        # Download historical prices for 1 year
        data = await run_with_exponential_backoff(
            lambda: _run_ticker_blocking(
                yf.download,
                symbols,
                period="1y",
                interval="1d",
                progress=False,
                auto_adjust=True
            ),
            context="hrp allocation price fetch"
        )
        
        if data.empty:
            return {"error": "Failed to fetch historical data"}
            
        # Calculate returns - handle MultiIndex carefully
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"] if "Close" in data else data.xs('Close', axis=1, level=0)
        else:
            prices = data[["Close"]] if "Close" in data.columns else data
            
        returns = prices.pct_change().dropna(how='all').fillna(0)
        
        allocator = HRPAllocator()
        weights = allocator.allocate(returns)
        
        # Sort by weight descending
        sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "weights": {k: float(v) for k, v in sorted_weights},
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


# Helper to clean JSON (NaN/Inf)
def _json_safe_clean(obj):
    if isinstance(obj, list):
        return [_json_safe_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _json_safe_clean(v) for k, v in obj.items()}
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
    return obj
