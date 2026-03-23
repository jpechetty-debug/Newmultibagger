"""
Backfill ML Predictions and Backtest Metrics for all stocks in the database.

This script reads existing fundamentals from the multibaggers table,
runs the XGBoost ML model to generate predictions, then batch-runs
VectorBT backtests, and updates the database in-place.
"""
import sqlite3
import pandas as pd
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_NAME = "stocks.db"
WRITE_RETRIES = 10
RETRY_BASE_SECONDS = 0.1


def _get_conn():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _write_with_retry(write_fn, label="write"):
    for attempt in range(WRITE_RETRIES):
        try:
            return write_fn()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < WRITE_RETRIES - 1:
                wait = RETRY_BASE_SECONDS * (2 ** attempt)
                print(f"  ⏳ DB locked during {label}, retrying in {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise


def backfill_ml_predictions():
    """Backfill ml_predicted_return and shap_breakdown for all stocks using existing fundamentals."""
    print("=" * 60)
    print("  BACKFILL: ML Predictions (XGBoost + SHAP)")
    print("=" * 60)

    conn = _get_conn()
    df = pd.read_sql(
        "SELECT symbol, score, sales_cagr_5y, avg_roe_5y, pe_ratio, "
        "debt_equity, cfo_pat_ratio, market_cap_cr, ml_predicted_return "
        "FROM multibaggers",
        conn,
    )
    conn.close()

    # Filter to stocks missing ML prediction
    missing = df[df["ml_predicted_return"].isna()]
    print(f"Total stocks: {len(df)}, Missing ML prediction: {len(missing)}")

    if missing.empty:
        print("✅ All stocks already have ML predictions.")
        return

    try:
        from modules.hybrid_scoring import predict_and_explain
    except ImportError as e:
        print(f"❌ Cannot import hybrid_scoring: {e}")
        return

    updates = []
    for idx, row in missing.iterrows():
        factors = {
            "score": row.get("score", 0) or 0,
            "sales_cagr_5y": row.get("sales_cagr_5y", 0) or 0,
            "avg_roe_5y": row.get("avg_roe_5y", 0) or 0,
            "pe_ratio": row.get("pe_ratio", 0) or 0,
            "debt_equity": row.get("debt_equity", 0) or 0,
            "cfo_pat_ratio": row.get("cfo_pat_ratio", 0) or 0,
            "market_cap_cr": row.get("market_cap_cr", 0) or 0,
        }
        result = predict_and_explain(factors)
        ml_pred = result.get("ml_prediction")
        shap_json = json.dumps(result.get("shap_values", {}))
        updates.append((ml_pred, shap_json, row["symbol"]))

    # Batch update with retry
    def _do_ml_write():
        conn = _get_conn()
        conn.executemany(
            "UPDATE multibaggers SET ml_predicted_return = ?, shap_breakdown = ? WHERE symbol = ?",
            updates,
        )
        conn.commit()
        conn.close()

    _write_with_retry(_do_ml_write, "ML predictions")
    filled = sum(1 for u in updates if u[0] is not None)
    print(f"✅ Updated {filled}/{len(updates)} stocks with ML predictions.")


def backfill_backtest_metrics():
    """Backfill backtest_cagr, backtest_win_rate, backtest_max_dd, backtest_sharpe for all stocks."""
    print("\n" + "=" * 60)
    print("  BACKFILL: VectorBT Backtest Metrics (5Y)")
    print("=" * 60)

    conn = _get_conn()
    df = pd.read_sql(
        "SELECT symbol, backtest_cagr FROM multibaggers",
        conn,
    )
    conn.close()

    # Filter to stocks missing backtest data (NULL or 0)
    missing = df[(df["backtest_cagr"].isna()) | (df["backtest_cagr"] == 0)]
    print(f"Total stocks: {len(df)}, Missing backtest: {len(missing)}")

    if missing.empty:
        print("✅ All stocks already have backtest metrics.")
        return

    symbols = missing["symbol"].tolist()

    try:
        from backtest.engine import VectorBTEngine
    except ImportError as e:
        print(f"❌ Cannot import VectorBTEngine: {e}")
        return

    # Process in batches of 50 to avoid yfinance rate limits
    BATCH_SIZE = 50
    bt_engine = VectorBTEngine(period="5y")
    total_filled = 0
    total_processed = 0

    for batch_start in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[batch_start : batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(symbols) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"\n📊 Batch {batch_num}/{total_batches}: Processing {len(batch)} stocks...")

        try:
            batch_results = bt_engine.run_batch_momentum_backtest(batch)
        except Exception as e:
            print(f"  ⚠️ Batch {batch_num} failed: {e}")
            batch_results = {}

        updates = []
        for sym in batch:
            sym_ns = sym if sym.endswith(".NS") or sym.endswith(".BO") else sym + ".NS"
            bt = batch_results.get(sym_ns, batch_results.get(sym, {}))
            cagr = bt.get("cagr", 0.0)
            updates.append((
                cagr,
                bt.get("win_rate", 0.0),
                bt.get("max_drawdown", 0.0),
                bt.get("sharpe_ratio", 0.0),
                sym,
            ))
            if cagr != 0.0:
                total_filled += 1
            total_processed += 1

        # Write batch to DB with retry
        def _do_bt_write():
            conn = _get_conn()
            conn.executemany(
                "UPDATE multibaggers SET backtest_cagr = ?, backtest_win_rate = ?, "
                "backtest_max_dd = ?, backtest_sharpe = ? WHERE symbol = ?",
                updates,
            )
            conn.commit()
            conn.close()

        _write_with_retry(_do_bt_write, f"backtest batch {batch_num}")
        print(f"  ✅ Batch {batch_num} done. Running total: {total_filled}/{total_processed} filled.")

    print(f"\n✅ Backtest backfill complete: {total_filled}/{total_processed} stocks with valid data.")


if __name__ == "__main__":
    backfill_ml_predictions()
    backfill_backtest_metrics()
    print("\n🎉 Backfill complete! Restart the web UI to see updated values.")
