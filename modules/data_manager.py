# modules/data_manager.py
# Sovereign AI - Production Data Manager
# Fully upgraded Data Pipeline: Abstract DataProvider, SQLite Cache, Tenacity Retries, Data Quality filters.

import asyncio
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from typing import Dict, List, Optional, Any
import logging
import sqlite3
import pickle
import time
from abc import ABC, abstractmethod
from datetime import datetime, date

import pandas_market_calendars as mcal
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

_FUNDAMENTAL_KEYS = (
    "marketCap",
    "trailingPE",
    "returnOnEquity",
    "debtToEquity",
    "revenueGrowth",
    "earningsGrowth",
    "sector",
    "industry",
)

_TRANSIENT_ERROR_HINTS = (
    "timeout",
    "timed out",
    "429",
    "rate limit",
    "too many requests",
    "temporarily unavailable",
    "connection reset",
    "ssl",
    "name resolution",
)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _normalize_info(
    primary_info: Optional[Dict[str, Any]],
    *,
    fallback_info: Optional[Dict[str, Any]] = None,
    alias_map: Optional[Dict[str, tuple]] = None,
) -> Dict[str, Any]:
    """Build canonical info dict using provider payload + yfinance fallback."""
    normalized: Dict[str, Any] = {}
    if isinstance(fallback_info, dict):
        for key, value in fallback_info.items():
            if _has_value(value):
                normalized[key] = value
    if isinstance(primary_info, dict):
        for key, value in primary_info.items():
            if _has_value(value):
                normalized[key] = value
    if alias_map and isinstance(primary_info, dict):
        for target, aliases in alias_map.items():
            if _has_value(normalized.get(target)):
                continue
            for alias in aliases:
                candidate = primary_info.get(alias)
                if _has_value(candidate):
                    normalized[target] = candidate
                    break
    return normalized


def _is_missing_or_zero(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"", "none", "nan", "na", "null", "0", "0.0"}
    try:
        num = float(value)
        return num == 0.0
    except Exception:
        return False


def _fundamental_coverage(info: Any) -> int:
    if not isinstance(info, dict):
        return 0
    covered = 0
    for key in _FUNDAMENTAL_KEYS:
        value = info.get(key)
        if key in {"marketCap", "trailingPE"}:
            if _is_missing_or_zero(value):
                continue
        elif not _has_value(value):
            continue
        covered += 1
    return covered


def _is_payload_skeletal(payload: Any, *, min_coverage: int = 2) -> bool:
    if not isinstance(payload, dict):
        return True
    coverage = _fundamental_coverage(payload.get("info", {}))
    return coverage < int(min_coverage)


async def _run_executor_safe(loop, executor, fn, default):
    try:
        return await loop.run_in_executor(executor, fn)
    except Exception as e:
        logger.debug(f"Executor Error in DataManager: {e}")
        return default


_PNSEA_INFO_ALIASES = {
    "marketCap": ("marketCap", "marketCapTotal", "marketCapitalization"),
    "trailingPE": ("trailingPE", "pe", "pE"),
    "returnOnEquity": ("returnOnEquity", "roe"),
    "debtToEquity": ("debtToEquity", "debtEquity"),
    "revenueGrowth": ("revenueGrowth", "salesGrowth"),
    "earningsGrowth": ("earningsGrowth", "profitGrowth"),
    "bookValue": ("bookValue",),
    "trailingEps": ("trailingEps", "eps"),
    "fiftyTwoWeekHigh": ("fiftyTwoWeekHigh", "weekHigh52"),
    "fiftyTwoWeekLow": ("fiftyTwoWeekLow", "weekLow52"),
    "sector": ("sector", "sectorName"),
    "industry": ("industry", "industryName"),
}

_NSEPYTHON_INFO_ALIASES = {
    "marketCap": ("marketCap", "marketCapitalization"),
    "trailingPE": ("trailingPE", "pe", "peRatio"),
    "returnOnEquity": ("returnOnEquity", "roe"),
    "debtToEquity": ("debtToEquity", "debtEquity", "deRatio"),
    "revenueGrowth": ("revenueGrowth", "salesGrowth"),
    "earningsGrowth": ("earningsGrowth", "profitGrowth", "epsGrowth"),
    "bookValue": ("bookValue",),
    "trailingEps": ("trailingEps", "eps"),
    "fiftyTwoWeekHigh": ("fiftyTwoWeekHigh", "high52Week"),
    "fiftyTwoWeekLow": ("fiftyTwoWeekLow", "low52Week"),
    "sector": ("sector",),
    "industry": ("industry",),
}

# --- Dynamic Market Calendar ---
def get_valid_trading_days(start_date, end_date):
    nse = mcal.get_calendar('NSE')
    schedule = nse.schedule(start_date=start_date, end_date=end_date)
    return schedule.index.date

# --- Persistent Caching (Pickle + SQLite) ---
class PersistentCache:
    def __init__(self, db_path="data_cache.db", ttl_seconds=86400):
        self.db_path = db_path
        self.ttl = ttl_seconds
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS cache
                            (key TEXT PRIMARY KEY, value BLOB, timestamp REAL)''')
            conn.commit()

    def get(self, key: str) -> Optional[Any]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value, timestamp FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    val, ts = row
                    if time.time() - ts < self.ttl:
                        return pickle.loads(val)
                    else:
                        cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
            return None
        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
            return None

    def set(self, key: str, value: Any):
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
                             (key, pickle.dumps(value), time.time()))
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache write error for {key}: {e}")

# --- Abstract Data Provider ---
class DataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def fetch_fundamentals(self, symbol: str) -> Dict:
        pass

# --- Concrete Providers ---
class PNSEAProvider(DataProvider):
    @property
    def name(self): return "pnsea"
    
    def __init__(self, executor):
        self.executor = executor
        try:
            from pnsea import NSE
            self.nse = NSE()
            self.available = True
        except ImportError:
            self.available = False

    async def fetch_fundamentals(self, symbol: str) -> Dict:
        if not self.available:
            raise ImportError("PNSEA not available")
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(self.executor, lambda: self.nse.equity.info(symbol.replace(".NS", "")))
        pledged = await _run_executor_safe(
            loop,
            self.executor,
            lambda: self.nse.insider.getPledgedData(symbol.replace(".NS", "")),
            {},
        )

        yf_t = yf.Ticker(symbol)
        fin = await _run_executor_safe(loop, self.executor, lambda: yf_t.financials, pd.DataFrame())
        bs = await _run_executor_safe(loop, self.executor, lambda: yf_t.balance_sheet, pd.DataFrame())
        cf = await _run_executor_safe(loop, self.executor, lambda: yf_t.cash_flow, pd.DataFrame())
        info = _normalize_info(raw.get("info", {}), alias_map=_PNSEA_INFO_ALIASES)

        cfo_pat = 0.0
        try:
            cfo_pat = raw.get("info", {}).get("cashFlowFromOperations", 0) / max(raw.get("info", {}).get("netProfit", 1), 1)
        except (ZeroDivisionError, TypeError, ValueError) as _cfo_err:
            logger.warning("[%s] CFO/PAT ratio calculation failed: %s", symbol, _cfo_err)

        return {
            "symbol": symbol,
            "source": self.name,
            "price": raw.get("priceInfo", {}).get("lastPrice"),
            "roe": raw.get("info", {}).get("roe"),
            "sales_growth": raw.get("info", {}).get("salesGrowth"),
            "cfo_pat": cfo_pat,
            "pledge_percent": pledged.get("pledgedPercentage", 0) if isinstance(pledged, dict) else 0,
            "promoter_holding": raw.get("info", {}).get("promoterHolding"),
            "fii_dii": {
                "fii": raw.get("info", {}).get("fiiHolding"),
                "dii": raw.get("info", {}).get("diiHolding")
            },
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf
        }

class NSEPythonProvider(DataProvider):
    @property
    def name(self): return "nsepython"
    
    def __init__(self, executor):
        self.executor = executor
        try:
            from nsepython import get_quote, get_fundamentals, get_bulk_deals, get_pledged_shares, get_shareholding
            self.api_quote = get_quote
            self.api_fundamentals = get_fundamentals
            self.api_bulk = get_bulk_deals
            self.api_pledged = get_pledged_shares
            self.api_share = get_shareholding
            self.available = True
        except ImportError:
            self.available = False

    async def fetch_fundamentals(self, symbol: str) -> Dict:
        if not self.available:
            raise ImportError("nsepython not available")
        loop = asyncio.get_running_loop()
        sym = symbol.replace(".NS", "")
        
        quote = await loop.run_in_executor(self.executor, self.api_quote, sym)
        fundamentals = await loop.run_in_executor(self.executor, self.api_fundamentals, sym)
        pledged = await _run_executor_safe(loop, self.executor, lambda: self.api_pledged(sym), {})
        bulk = await _run_executor_safe(loop, self.executor, lambda: self.api_bulk(sym), [])
        shareholding = await _run_executor_safe(loop, self.executor, lambda: self.api_share(sym), {})

        yf_t = yf.Ticker(symbol)
        fin = await _run_executor_safe(loop, self.executor, lambda: yf_t.financials, pd.DataFrame())
        bs = await _run_executor_safe(loop, self.executor, lambda: yf_t.balance_sheet, pd.DataFrame())
        cf = await _run_executor_safe(loop, self.executor, lambda: yf_t.cash_flow, pd.DataFrame())
        info = _normalize_info(fundamentals, alias_map=_NSEPYTHON_INFO_ALIASES)

        return {
            "symbol": symbol,
            "source": self.name,
            "price": quote.get("priceInfo", {}).get("lastPrice"),
            "roe": fundamentals.get("roe"),
            "sales_growth": fundamentals.get("salesGrowth"),
            "cfo_pat": fundamentals.get("cfoPatRatio", 0),
            "pledge_percent": pledged.get("pledgePercent", 0),
            "promoter_holding": shareholding.get("promoter", 0),
            "fii_dii": shareholding.get("institutional", {}),
            "bulk_deals": bulk,
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf
        }

class YFinanceProvider(DataProvider):
    @property
    def name(self): return "yfinance"

    def __init__(self, executor):
        self.executor = executor
        self.available = True

    async def fetch_fundamentals(self, symbol: str) -> Dict:
        loop = asyncio.get_running_loop()
        ticker = yf.Ticker(symbol)
        info = await _run_executor_safe(loop, self.executor, lambda: ticker.info, {})
        if not isinstance(info, dict):
            info = {}
        if _is_payload_skeletal({"info": info}, min_coverage=1):
            fast = await _run_executor_safe(loop, self.executor, lambda: dict(getattr(ticker, "fast_info", {}) or {}), {})
            if isinstance(fast, dict) and fast:
                if not _has_value(info.get("currentPrice")) and _has_value(fast.get("lastPrice")):
                    info["currentPrice"] = fast.get("lastPrice")
                if not _has_value(info.get("marketCap")) and _has_value(fast.get("marketCap")):
                    info["marketCap"] = fast.get("marketCap")
                if not _has_value(info.get("fiftyTwoWeekHigh")) and _has_value(fast.get("yearHigh")):
                    info["fiftyTwoWeekHigh"] = fast.get("yearHigh")
                if not _has_value(info.get("fiftyTwoWeekLow")) and _has_value(fast.get("yearLow")):
                    info["fiftyTwoWeekLow"] = fast.get("yearLow")
        fin = await _run_executor_safe(loop, self.executor, lambda: ticker.financials, pd.DataFrame())
        bs = await _run_executor_safe(loop, self.executor, lambda: ticker.balance_sheet, pd.DataFrame())
        cf = await _run_executor_safe(loop, self.executor, lambda: ticker.cash_flow, pd.DataFrame())
        
        return {
            "symbol": symbol,
            "source": self.name,
            "price": info.get("currentPrice"),
            "roe": info.get("returnOnEquity"),
            "sales_growth": info.get("revenueGrowth"),
            "pledge_percent": 0,
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf
        }

# --- Main Data Manager ---
class DataManager:
    def __init__(self, max_concurrency: int = 15):
        self.max_concurrency = int(max_concurrency)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self.provider_timeout_seconds = 16
        self.yfinance_timeout_seconds = 22
        self.history_timeout_seconds = 18
        self.provider_fail_streak = {}
        self.provider_cooldown_until = {}
        
        # Priority Fallback List
        self.providers = [
            PNSEAProvider(self.executor),
            NSEPythonProvider(self.executor),
            YFinanceProvider(self.executor)
        ]
        
        # Persistent Cache (TTL: 24h for fundamentals, 1h for fast data)
        self.cache = PersistentCache()
        
        current_year = datetime.now().year
        self.valid_trading_days = get_valid_trading_days(f'{current_year-10}-01-01', f'{current_year+2}-12-31')

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _is_transient_error(self, exc: Exception) -> bool:
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return True
        text = str(exc).lower()
        return any(hint in text for hint in _TRANSIENT_ERROR_HINTS)

    def _record_provider_success(self, provider_name: str):
        self.provider_fail_streak[provider_name] = 0
        self.provider_cooldown_until.pop(provider_name, None)

    def _record_provider_failure(self, provider_name: str, *, transient: bool):
        streak = int(self.provider_fail_streak.get(provider_name, 0)) + 1
        self.provider_fail_streak[provider_name] = streak
        if transient and streak >= 4:
            cooldown = min(30, streak * 2)
            self.provider_cooldown_until[provider_name] = time.time() + cooldown

    async def _adaptive_pause(self, provider_name: str):
        streak = int(self.provider_fail_streak.get(provider_name, 0))
        if streak <= 1:
            return
        pause_seconds = min(2.5, 0.2 * streak)
        await asyncio.sleep(pause_seconds)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asyncio.TimeoutError, TimeoutError)),
    )
    async def async_fetch_fundamentals(self, symbol: str) -> Dict:
        """Main entry point - returns normalized dict with 12-point checklist data"""
        async with self.semaphore:
            cache_key = f"fund_{symbol}"
            cached = self.cache.get(cache_key)
            if cached:
                return cached

            incomplete_payload = None

            # Try providers in priority order
            for provider in self.providers:
                if not getattr(provider, 'available', True):
                    continue
                provider_name = provider.name
                if self.provider_cooldown_until.get(provider_name, 0) > time.time():
                    continue
                try:
                    timeout_s = self.yfinance_timeout_seconds if provider_name == "yfinance" else self.provider_timeout_seconds
                    data = await asyncio.wait_for(provider.fetch_fundamentals(symbol), timeout=timeout_s)
                    if data and "error" not in data:
                        if _is_payload_skeletal(data):
                            incomplete_payload = data
                            if provider_name != "yfinance":
                                self._record_provider_failure(provider_name, transient=False)
                                continue
                        self.cache.set(cache_key, data)
                        self._record_provider_success(provider_name)
                        return data
                except Exception as e:
                    transient = self._is_transient_error(e)
                    self._record_provider_failure(provider_name, transient=transient)
                    if transient:
                        await self._adaptive_pause(provider_name)
                    logger.warning(f"Provider {provider.name} failed for {symbol}: {e}")
                    continue

            if incomplete_payload:
                return incomplete_payload
            return {"symbol": symbol, "error": "All providers failed", "source": "fallback_failed"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Fetch historical price data with quality checks"""
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            ticker = yf.Ticker(symbol)
            df = pd.DataFrame()
            for attempt in range(2):
                try:
                    df = await asyncio.wait_for(
                        loop.run_in_executor(self.executor, lambda: ticker.history(period=period)),
                        timeout=self.history_timeout_seconds,
                    )
                except Exception as exc:
                    if attempt == 0 and self._is_transient_error(exc):
                        await asyncio.sleep(0.6)
                        continue
                    raise
                if df.empty or 'Close' not in df.columns:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    return pd.DataFrame()
                break
            
            if df.empty or 'Close' not in df.columns:
                return pd.DataFrame()
                
            # --- Data Quality Checks ---
            # 1. Price Continuity (Remove extreme spikes > 50% in one day unless penny stock)
            pct_change = df['Close'].pct_change().abs()
            glitch_mask = (df['Close'] > 10) & (pct_change > 0.5)
            if glitch_mask.any():
                logger.warning(f"[{symbol}] Data glitch detected: price jump > 50%. Ignoring anomalies.")
                df = df[~glitch_mask]
                
            # 2. Volume Sanity check
            if 'Volume' in df.columns:
                df.loc[df['Volume'] < 0, 'Volume'] = 0
            
            # --- MARKET CLOSED FIX (Dynamic) ---
            today = datetime.now().date()
            is_valid_trading_day = today in self.valid_trading_days
            is_holiday_or_weekend = not is_valid_trading_day
            
            df = df.dropna(subset=['Close'])
            if len(df) >= 2 and 'Volume' in df.columns and (pd.isna(df['Volume'].iloc[-1]) or df['Volume'].iloc[-1] == 0 or is_holiday_or_weekend):
                df = df.iloc[:-1]
                
            return df

    async def fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        """Fetch quarterly financial results"""
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            ticker = yf.Ticker(symbol)
            qf = await loop.run_in_executor(self.executor, lambda: ticker.quarterly_financials)
            if qf.empty: return []
            
            results = []
            for col in qf.columns:
                results.append({
                    "date": col.strftime('%Y-%m-%d') if hasattr(col, 'strftime') else str(col),
                    "revenue": qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else 0,
                    "profit": qf.loc["Net Income", col] if "Net Income" in qf.index else 0
                })
            return results

    async def fetch_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        tasks = [self.async_fetch_fundamentals(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {sym: res for sym, res in zip(symbols, results) if not isinstance(res, Exception)}

    async def close(self):
        self.executor.shutdown(wait=True)

# For backward compatibility singleton
data_manager = DataManager()
