# worker/tasks.py
"""
Sovereign AI Trading Engine v4.0 — Celery Task Definitions
Distributed tasks for stock screening, ML inference, LLM thesis generation,
backtesting, and database maintenance.

All tasks are designed to be idempotent and fault-tolerant.
"""
import os
import sys
import time
import traceback
from datetime import datetime

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from worker.celery_app import app
from worker.redis_cache import cache


# ============================================================
# SCREENING TASKS
# ============================================================

@app.task(bind=True, name="worker.tasks.scan_single_stock", max_retries=3, rate_limit="20/m")
def scan_single_stock(self, symbol: str, regime: str = "SIDEWAYS"):
    """
    Scan a single stock through the full scoring pipeline.
    This is the atomic unit of work for distributed screening.
    
    Args:
        symbol: NSE ticker (e.g., "RELIANCE.NS")
        regime: Market regime for weight adjustments (BULL/BEAR/SIDEWAYS)
    
    Returns:
        dict with symbol, score, and metadata
    """
    try:
        # Check cache first
        cached = cache.get_stock_score(symbol)
        if cached:
            return {"symbol": symbol, "cached": True, **cached}

        # Import the screener's scoring function
        from modules.data_manager import DataManager
        dm = DataManager()
        
        stock_data = dm.get_stock_data(symbol)
        if stock_data is None:
            return {"symbol": symbol, "error": "No data available", "score": 0}

        # Run through scoring pipeline
        result = {
            "symbol": symbol,
            "score": stock_data.get("score", 0),
            "price": stock_data.get("price"),
            "sector": stock_data.get("sector"),
            "pe_ratio": stock_data.get("pe_ratio"),
            "roe": stock_data.get("roe"),
            "scanned_at": datetime.now().isoformat(),
            "regime": regime,
        }

        # Cache the result
        cache.cache_stock_score(symbol, result)
        return result

    except Exception as exc:
        print(f"Task scan_single_stock failed for {symbol}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@app.task(bind=True, name="worker.tasks.run_full_scan", time_limit=3600)
def run_full_scan(self):
    """
    Orchestrate a full-universe market scan by fanning out individual
    stock scans across the Celery worker pool.
    
    This is the master task that:
    1. Loads the ticker universe
    2. Detects the current market regime
    3. Fans out scan_single_stock tasks to workers
    4. Collects results and persists to database
    """
    from celery import group
    
    try:
        # Load ticker universe
        from ticker_list import STOCK_LIST
        symbols = STOCK_LIST if isinstance(STOCK_LIST, list) else list(STOCK_LIST)

        # Detect current market regime
        regime = "SIDEWAYS"
        cached_regime = cache.get_regime()
        if cached_regime:
            regime = cached_regime.get("regime", "SIDEWAYS")
        
        print(f"🚀 Full scan initiated: {len(symbols)} symbols | Regime: {regime}")

        # Fan out to workers
        job = group(
            scan_single_stock.s(symbol, regime) for symbol in symbols
        )
        result = job.apply_async()

        # Wait for all tasks (with timeout)
        results = result.get(timeout=2400, propagate=False)

        # Filter successful results
        successful = [r for r in results if isinstance(r, dict) and "error" not in r]
        failed = len(results) - len(successful)

        print(f"✅ Scan complete: {len(successful)} success / {failed} failed")

        # Persist results to database
        if successful:
            import pandas as pd
            from database import save_multibaggers
            df = pd.DataFrame(successful)
            save_multibaggers(df)

        return {
            "total": len(symbols),
            "success": len(successful),
            "failed": failed,
            "regime": regime,
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as exc:
        print(f"Full scan failed: {exc}")
        traceback.print_exc()
        return {"error": str(exc)}


# ============================================================
# ML INFERENCE TASKS
# ============================================================

@app.task(name="worker.tasks.retrain_xgboost", time_limit=1800)
def retrain_xgboost():
    """
    Retrain the XGBoost meta-model on the latest PIT-sanitized data.
    This task is compute-intensive and should run on the 'compute' queue.
    """
    try:
        from modules.hybrid_scoring import train_hybrid_model
        result = train_hybrid_model()
        return {
            "status": "success",
            "retrained_at": datetime.now().isoformat(),
            "result": str(result),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.generate_thesis", rate_limit="5/m")
def generate_thesis(stock_data: dict):
    """
    Generate an LLM investment thesis for a stock.
    Rate-limited to respect Ollama resource constraints.
    """
    try:
        from modules.llm_engine import generate_thesis as _gen
        thesis = _gen(stock_data)
        return {
            "symbol": stock_data.get("symbol", "UNKNOWN"),
            "thesis": thesis,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"symbol": stock_data.get("symbol", "UNKNOWN"), "error": str(e)}


# ============================================================
# BACKTEST TASKS
# ============================================================

@app.task(name="worker.tasks.run_backtest_refresh", time_limit=3600)
def run_backtest_refresh():
    """
    Refresh backtest metrics for the current universe.
    Runs on the 'compute' queue (weekly via beat schedule).
    """
    try:
        from backtest_engine import run_backtest
        result = run_backtest()
        return {
            "status": "success",
            "refreshed_at": datetime.now().isoformat(),
            "result": str(result),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# MAINTENANCE TASKS
# ============================================================

@app.task(name="worker.tasks.prune_pit_data")
def prune_pit_data():
    """
    Prune old PIT fundamental snapshots beyond the retention window.
    Runs daily at 2 AM via beat schedule.
    """
    try:
        from database import prune_fundamentals_pit_retention
        deleted = prune_fundamentals_pit_retention()
        return {
            "status": "success",
            "rows_pruned": deleted,
            "pruned_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.refresh_regime_cache")
def refresh_regime_cache():
    """
    Refresh the market regime detection and update the Redis cache.
    """
    try:
        from modules.market_data import get_market_regime
        regime_data = get_market_regime()
        cache.cache_regime(regime_data)
        return {
            "status": "success",
            "regime": regime_data.get("regime"),
            "cached_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# STRESS TEST TASKS
# ============================================================

@app.task(name="worker.tasks.run_stress_test")
def run_stress_test(portfolio: dict):
    """
    Execute portfolio stress testing across all historical scenarios.
    """
    try:
        from modules.stress_tester import run_all_scenarios
        reports = run_all_scenarios(portfolio)
        return {
            "status": "success",
            "scenario_count": len(reports),
            "worst_case_loss_pct": reports[0].portfolio_loss_pct if reports else None,
            "tested_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
