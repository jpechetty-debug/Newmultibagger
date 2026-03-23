import sqlite3

import numpy as np
import pandas as pd
import yfinance as yf


def _extract_close_frame(data: pd.DataFrame, tickers: list) -> pd.DataFrame:
    """Normalize yfinance output to a Close-price frame with ticker columns."""
    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(data.columns.get_level_values(0))
        level1 = set(data.columns.get_level_values(1))
        if "Close" in level0:
            close = data["Close"]
            return close if isinstance(close, pd.DataFrame) else close.to_frame()
        if "Close" in level1:
            close = data.xs("Close", axis=1, level=1, drop_level=True)
            return close if isinstance(close, pd.DataFrame) else close.to_frame()
        return pd.DataFrame()

    if "Close" in data.columns:
        if len(tickers) == 1:
            return pd.DataFrame({tickers[0]: pd.to_numeric(data["Close"], errors="coerce")})
        close = pd.to_numeric(data["Close"], errors="coerce")
        return close.to_frame(name=tickers[0] if tickers else "Close")

    return pd.DataFrame()


def _safe_return_pct(series: pd.Series) -> float:
    prices = pd.to_numeric(series, errors="coerce").dropna()
    if len(prices) < 120:
        return 0.0
    start = float(prices.iloc[0])
    end = float(prices.iloc[-1])
    if start <= 0:
        return 0.0
    return ((end - start) / start) * 100.0


def run_attribution():
    print("Initiating Alpha Source Attribution (Phase 49)...")

    try:
        conn = sqlite3.connect("stocks.db")
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")
        return

    if df.empty:
        print("Universe is empty; skipping attribution.")
        return

    print(f"Universe Size: {len(df)} stocks")

    numeric_cols = ["pe_ratio", "roe", "sales_cagr_5y", "rs_rating", "atr", "f_score", "price"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    factors = {
        "Value (Low PE)": {
            "col": "pe_ratio",
            "ascending": True,
            "filter": (df["pe_ratio"] > 0) if "pe_ratio" in df.columns else pd.Series(False, index=df.index),
        },
        "Momentum (High RS)": {
            "col": "rs_rating",
            "ascending": False,
            "filter": (df["rs_rating"] > 0) if "rs_rating" in df.columns else pd.Series(False, index=df.index),
        },
        "Quality (High ROE)": {
            "col": "roe",
            "ascending": False,
            "filter": (df["roe"] > 0) if "roe" in df.columns else pd.Series(False, index=df.index),
        },
        "Growth (High Sales)": {
            "col": "sales_cagr_5y",
            "ascending": False,
            "filter": (df["sales_cagr_5y"] > 0) if "sales_cagr_5y" in df.columns else pd.Series(False, index=df.index),
        },
        "Low Volatility (Low ATR)": {
            "col": "atr",
            "ascending": True,
            "filter": (df["atr"] > 0) if "atr" in df.columns else pd.Series(False, index=df.index),
        },
    }

    if "atr" in df.columns and "price" in df.columns:
        vol = (df["atr"] / df["price"].replace(0, np.nan)) * 100.0
        df["volatility_pct"] = pd.to_numeric(vol, errors="coerce").fillna(0.0)
        factors["Low Volatility"] = {
            "col": "volatility_pct",
            "ascending": True,
            "filter": df["volatility_pct"] > 0,
        }
        factors.pop("Low Volatility (Low ATR)", None)

    if "symbol" not in df.columns:
        print("Missing symbol column in multibaggers table.")
        return

    results = []
    for name, criteria in factors.items():
        col = criteria["col"]
        if col not in df.columns:
            continue

        print(f"\nTesting Factor: {name}")
        subset = df[criteria["filter"]].copy()
        subset = subset.sort_values(by=col, ascending=criteria["ascending"])
        portfolio = subset.head(20)

        if portfolio.empty:
            print(f"No stocks found for {name}")
            continue

        tickers_list = [str(t).strip().upper() for t in portfolio["symbol"].tolist() if str(t).strip()]
        if not tickers_list:
            print(f"No valid symbols for {name}")
            continue

        print(f"Fetching returns for {len(tickers_list)} stocks...")
        try:
            data = yf.download(
                tickers_list,
                period="1y",
                progress=False,
                auto_adjust=False,
                threads=True,
            )
            close_df = _extract_close_frame(data, tickers_list)
            if close_df.empty:
                print("No close-price data returned for factor portfolio.")
                continue

            current_returns = []
            for ticker in tickers_list:
                if ticker in close_df.columns:
                    current_returns.append(_safe_return_pct(close_df[ticker]))
                else:
                    current_returns.append(0.0)

            if not current_returns:
                continue

            avg_return = float(np.mean(current_returns))
            win_rate = (len([r for r in current_returns if r > 0]) / len(current_returns)) * 100.0
            print(f"Return: {avg_return:.2f}% | Win Rate: {win_rate:.1f}%")

            results.append(
                {
                    "Factor": name,
                    "Return_1Y": avg_return,
                    "Win_Rate": win_rate,
                    "Top_Pick": tickers_list[0],
                }
            )
        except Exception as e:
            print(f"Error fetching data: {e}")

    if not results:
        print("No attribution portfolios produced valid results.")
        return

    results_df = pd.DataFrame(results).sort_values(by="Return_1Y", ascending=False)
    print("\n" + "=" * 50)
    print("ALPHA ATTRIBUTION LEADERBOARD (1-Year)")
    print("=" * 50)
    print(results_df.to_string(index=False))

    winner = results_df.iloc[0]
    with open("alpha_report.md", "w", encoding="utf-8") as f:
        f.write("# Phase 49: Alpha Attribution Report\n\n")
        f.write("## Which Factor is Winning? (1-Year Lookback)\n")
        f.write(
            f"Dominant Regime: {winner['Factor']} ({winner['Return_1Y']:.2f}% Return)\n\n"
        )
        f.write(results_df.to_markdown(index=False))
        f.write("\n\n### Analysis\n")
        f.write(
            f"- {winner['Factor']} is the current leader for trailing 1-year performance.\n"
        )
        f.write("- Track rotations by comparing Value vs Momentum vs Quality each full scan.\n")

    print("\nReport saved to alpha_report.md")


if __name__ == "__main__":
    run_attribution()
