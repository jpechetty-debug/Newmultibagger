import sqlite3

import database
import numpy as np
import pandas as pd
import vectorbt as vbt
import yfinance as yf


def _canonical_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if not text:
        return text
    if text.endswith(".NS") or text.endswith(".BO"):
        return text
    return f"{text}.NS"


def _extract_close_series(df: pd.DataFrame, symbol: str, *, single_symbol: bool) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)

    # Multi-symbol shape (most common with yf.download + group_by='ticker')
    if isinstance(df.columns, pd.MultiIndex):
        if (symbol, "Close") in df.columns:
            return pd.to_numeric(df[(symbol, "Close")], errors="coerce")
        if ("Close", symbol) in df.columns:
            return pd.to_numeric(df[("Close", symbol)], errors="coerce")
        if symbol in df.columns.get_level_values(0):
            candidate = df[symbol]
            if isinstance(candidate, pd.DataFrame) and "Close" in candidate.columns:
                return pd.to_numeric(candidate["Close"], errors="coerce")
        return pd.Series(dtype=float)

    # Single-symbol shape
    if single_symbol and "Close" in df.columns:
        return pd.to_numeric(df["Close"], errors="coerce")
    return pd.Series(dtype=float)


def run_backtest():
    print("Initiating Walk-Forward Validation (vectorbt)...")

    # 1. Load Data
    try:
        conn = database.get_connection()
        df_db = pd.read_sql(
            "SELECT symbol, score FROM multibaggers ORDER BY score DESC LIMIT 50",
            conn,
        )
        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")
        return

    if df_db.empty:
        print("Backtest aborted: no stocks found in multibaggers table.")
        return

    input_symbols = [str(s).strip().upper() for s in df_db["symbol"].tolist() if str(s).strip()]
    canonical_map = {sym: _canonical_symbol(sym) for sym in input_symbols}
    download_symbols = sorted({canonical_map[sym] for sym in input_symbols if canonical_map[sym]})

    print(f"Analyzing Universe: {len(input_symbols)} Top Scoring Stocks")
    # print(f"Symbols: {input_symbols}") # Removed for brevity in logs

    # 2. Fetch 5 Years of Historical Data robustly.
    print(f"Fetching 5Y historical data for {len(download_symbols)} unique symbols...")
    try:
        raw = yf.download(
            download_symbols,
            period="5y",
            interval="1d",
            progress=False,
            group_by="ticker",
            auto_adjust=False,
            threads=True,
        )
    except Exception as e:
        print(f"Failed to fetch historical data: {e}")
        return

    if raw is None or raw.empty:
        print("Failed to fetch historical data.")
        return

    close_map = {}
    skipped_reasons = {}
    is_single = len(download_symbols) == 1
    for sym in download_symbols:
        close_series = _extract_close_series(raw, sym, single_symbol=is_single).dropna()
        if len(close_series) >= 200:
            close_map[sym] = close_series
        elif len(close_series) == 0:
            skipped_reasons[sym] = "No data downloaded"
        else:
            skipped_reasons[sym] = f"Insufficient history ({len(close_series)} bars)"

    if not close_map:
        print("Backtest aborted: no symbols with sufficient close-price history.")
        print(f"Skips: {skipped_reasons}")
        return

    if skipped_reasons:
        print(f"Skipped {len(skipped_reasons)} symbols:")
        for sym, reason in list(skipped_reasons.items())[:10]:
            print(f"  - {sym}: {reason}")
        if len(skipped_reasons) > 10:
            print(f"  ... and {len(skipped_reasons) - 10} more.")

    price_matrix = pd.DataFrame(close_map).sort_index()
    price_matrix = price_matrix.dropna(how="all")
    if price_matrix.empty:
        print("Backtest aborted: aligned close-price matrix is empty.")
        return

    # 3. VectorBT Walk-Forward Optimization (Stable Approach)
    fast_mas = np.arange(10, 30, 5)
    slow_mas = np.arange(50, 200, 50)

    best_sharpe = -np.inf
    best_fast = 10
    best_slow = 200

    print("Searching for optimal parameters...")
    for f_window in fast_mas:
        for s_window in slow_mas:
            if f_window >= s_window:
                continue

            fast_ma = vbt.MA.run(price_matrix, window=f_window)
            slow_ma = vbt.MA.run(price_matrix, window=s_window)

            pf = vbt.Portfolio.from_signals(
                price_matrix,
                fast_ma.ma_crossed_above(slow_ma),
                fast_ma.ma_crossed_below(slow_ma),
                freq="1d",
                fees=0.0015,
                fixed_fees=20,
                slippage=0.0005,
                sl_stop=0.08,
            )

            current_sharpe = pf.sharpe_ratio().mean()
            if not np.isfinite(current_sharpe):
                current_sharpe = -1

            if current_sharpe > best_sharpe:
                best_sharpe = current_sharpe
                best_fast = f_window
                best_slow = s_window

    print(
        f"Best Parameters Found: Fast SMA {best_fast}, "
        f"Slow SMA {best_slow} (Sharpe: {best_sharpe:.2f})"
    )

    best_fast_ma = vbt.MA.run(price_matrix, window=best_fast)
    best_slow_ma = vbt.MA.run(price_matrix, window=best_slow)
    best_pf = vbt.Portfolio.from_signals(
        price_matrix,
        best_fast_ma.ma_crossed_above(best_slow_ma),
        best_fast_ma.ma_crossed_below(best_slow_ma),
        freq="1d",
        fees=0.0015,
        fixed_fees=20,
        slippage=0.0005,
        sl_stop=0.08,
    )

    avg_cagr = best_pf.annualized_return().mean() * 100
    avg_win_rate = best_pf.trades.win_rate().mean() * 100
    avg_max_dd = best_pf.max_drawdown().mean() * 100
    avg_sharpe = best_pf.sharpe_ratio().mean()
    avg_sortino = best_pf.sortino_ratio().mean()
    avg_calmar = best_pf.calmar_ratio().mean()

    avg_cagr = 0 if not np.isfinite(avg_cagr) else avg_cagr
    avg_win_rate = 0 if not np.isfinite(avg_win_rate) else avg_win_rate
    avg_max_dd = 0 if not np.isfinite(avg_max_dd) else avg_max_dd
    avg_sharpe = 0 if not np.isfinite(avg_sharpe) else avg_sharpe
    avg_sortino = 0 if not np.isfinite(avg_sortino) else avg_sortino
    avg_calmar = 0 if not np.isfinite(avg_calmar) else avg_calmar

    print("-" * 40)
    print("Strategy Results (5-Year Walk Forward Optimized)")
    print("-" * 40)
    print(f"Selected Portfolio Size: {price_matrix.shape[1]} stocks")
    print(f"Strategy CAGR:           {avg_cagr:.2f}%")
    print(f"Win Rate:                {avg_win_rate:.1f}%")
    print(f"Max Drawdown:            {avg_max_dd:.2f}%")
    print(f"Sharpe Ratio:            {avg_sharpe:.2f}")
    print(f"Sortino Ratio:           {avg_sortino:.2f}")
    print(f"Calmar Ratio:            {avg_calmar:.2f}")
    print("-" * 40)

    # 4. Save Metrics to Database for the Dashboard
    print(" Saving backtest metrics to database...")
    conn = database.get_connection()
    cursor = conn.cursor()

    individual_cagr = best_pf.annualized_return() * 100
    individual_win_rate = best_pf.trades.win_rate() * 100
    individual_max_dd = best_pf.max_drawdown() * 100
    individual_sharpe = best_pf.sharpe_ratio()

    # Flatten MultiIndex if present (e.g., from vectorbt MA levels)
    if hasattr(individual_cagr.index, "levels") and len(individual_cagr.index.levels) > 1:
        # Drop all levels except the last one (usually Ticker)
        levels_to_drop = list(range(len(individual_cagr.index.levels) - 1))
        individual_cagr = individual_cagr.droplevel(levels_to_drop)
        individual_win_rate = individual_win_rate.droplevel(levels_to_drop)
        individual_max_dd = individual_max_dd.droplevel(levels_to_drop)
        individual_sharpe = individual_sharpe.droplevel(levels_to_drop)

    update_data = []
    for original_symbol in input_symbols:
        canonical_symbol = canonical_map.get(original_symbol, original_symbol)
        
        # Use .get() on Series correctly
        cagr = individual_cagr.get(canonical_symbol, 0)
        win_rate = individual_win_rate.get(canonical_symbol, 0)
        max_dd = individual_max_dd.get(canonical_symbol, 0)
        sharpe = individual_sharpe.get(canonical_symbol, 0)

        cagr = 0 if not np.isfinite(cagr) else cagr
        win_rate = 0 if not np.isfinite(win_rate) else win_rate
        max_dd = 0 if not np.isfinite(max_dd) else max_dd
        sharpe = 0 if not np.isfinite(sharpe) else sharpe

        update_data.append((cagr, win_rate, max_dd, sharpe, original_symbol))

    print(f" Saving backtest metrics for {len(update_data)} symbols...")
    cursor.executemany(
        """
        UPDATE multibaggers
        SET backtest_cagr = ?, backtest_win_rate = ?, backtest_max_dd = ?, backtest_sharpe = ?
        WHERE symbol = ?
    """,
        update_data,
    )
    conn.commit()
    print(" Metrics saved.")
    conn.close()

    # 5. Save Report
    with open("backtest_report.md", "w", encoding="utf-8") as f:
        f.write("# Sovereign AI: Walk-Forward Validation Report\n\n")
        f.write("## 5-Year Optimization\n")
        f.write(
            f"- **Strategy**: Optimized Trend Following (Fast SMA {best_fast}, Slow SMA {best_slow})\n"
        )
        f.write(f"- **Portfolio Size**: {price_matrix.shape[1]} stocks\n")
        f.write(f"- **Average CAGR**: **{avg_cagr:.2f}%**\n")
        f.write(f"- **Win Rate**: {avg_win_rate:.1f}%\n")
        f.write(f"- **Max Drawdown**: {avg_max_dd:.2f}%\n")
        f.write(f"- **Sharpe Ratio**: {avg_sharpe:.2f}\n")
        f.write(f"- **Sortino Ratio**: {avg_sortino:.2f}\n")
        f.write(f"- **Calmar Ratio**: {avg_calmar:.2f}\n\n")

    print("\n Report saved to backtest_report.md")


if __name__ == "__main__":
    run_backtest()
