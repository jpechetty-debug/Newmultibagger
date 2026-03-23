import json
import sqlite3

import numpy as np
import pandas as pd
import yfinance as yf


def _fetch_recent_volume_and_price(symbol: str) -> tuple:
    try:
        hist = yf.Ticker(symbol).history(period="20d")
        if hist is not None and not hist.empty and "Volume" in hist.columns and "Close" in hist.columns:
            avg_vol = float(pd.to_numeric(hist["Volume"], errors="coerce").dropna().mean())
            last_price_series = pd.to_numeric(hist["Close"], errors="coerce").dropna()
            last_price = float(last_price_series.iloc[-1]) if not last_price_series.empty else 0.0
            if not np.isfinite(avg_vol) or avg_vol <= 0:
                avg_vol = 100000.0
            if not np.isfinite(last_price) or last_price <= 0:
                last_price = 0.0
            return avg_vol, last_price
    except Exception:
        pass
    return 100000.0, 0.0


def run_liquidity_check():
    print("Initiating Capital Deployment Simulator (Phase 52)...")

    try:
        conn = sqlite3.connect("stocks.db")
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")
        return

    if df.empty:
        print("Portfolio empty.")
        return

    if "rs_rating" in df.columns:
        df["rs_rating"] = pd.to_numeric(df["rs_rating"], errors="coerce").fillna(0.0)
    else:
        df["rs_rating"] = 0.0

    if "symbol" not in df.columns:
        print("Missing symbol column in multibaggers table.")
        return

    portfolio = df.sort_values(by="rs_rating", ascending=False).head(20).copy()
    if portfolio.empty:
        print("Portfolio empty after ranking filter.")
        return

    print(f"Portfolio Size: {len(portfolio)} stocks")
    print("Fetching Volume and VIX Data...")

    try:
        vix_data = yf.Ticker("^INDIAVIX").history(period="5d")
        current_vix = float(pd.to_numeric(vix_data["Close"], errors="coerce").dropna().iloc[-1])
    except Exception:
        current_vix = 20.0
    print(f"Current VIX: {current_vix:.2f}")

    crisis_multiplier = 1.0
    if current_vix > 30:
        crisis_multiplier = 1.5
    elif current_vix > 25:
        crisis_multiplier = 1.25
    print(f"Crisis Multiplier: {crisis_multiplier}x")

    volumes = []
    prices = []
    for sym in portfolio["symbol"]:
        avg_vol, curr_price = _fetch_recent_volume_and_price(str(sym))
        volumes.append(avg_vol)
        prices.append(curr_price)

    portfolio["avg_volume"] = volumes
    portfolio["price"] = prices

    aum_levels = [1_000_000, 10_000_000, 100_000_000]  # 10L, 1Cr, 10Cr
    scenario_results = []

    with open("liquidity_report.md", "w", encoding="utf-8") as f:
        f.write("# Phase 52: Capital Deployment Report (v2.9 Enhanced)\n")
        f.write(
            f"Market Condition: VIX {current_vix:.2f} (Multiplier: {crisis_multiplier}x)\n\n"
        )

        for aum in aum_levels:
            allocation_per_stock = aum / 20.0
            print(
                f"\nStress Testing AUM: INR {aum:,.0f} "
                f"(INR {allocation_per_stock:,.0f} per stock)"
            )
            f.write(f"## AUM Scenario: INR {aum:,.0f}\n")

            risk_flags = 0
            max_impact_cost = 0.0
            bottleneck_stock = ""
            rows = []

            for _, row in portfolio.iterrows():
                price = float(row["price"]) if pd.notna(row["price"]) else 0.0
                avg_volume = float(row["avg_volume"]) if pd.notna(row["avg_volume"]) else 0.0
                daily_value = avg_volume * price

                if daily_value > 0:
                    impact_cost = (
                        0.01
                        * np.sqrt(allocation_per_stock / daily_value)
                        * crisis_multiplier
                        * 100.0
                    )
                else:
                    impact_cost = 0.0

                status = "OK"
                if impact_cost > 1.0:
                    status = "HIGH_IMPACT"
                    risk_flags += 1
                elif impact_cost > 0.5:
                    status = "SLIPPAGE"

                rows.append(
                    {
                        "Symbol": row["symbol"],
                        "Price": round(price, 2),
                        "Avg_Vol_20d": int(avg_volume),
                        "Impact_Cost_%": round(float(impact_cost), 2),
                        "Status": status,
                    }
                )

                if impact_cost > max_impact_cost:
                    max_impact_cost = float(impact_cost)
                    bottleneck_stock = str(row["symbol"])

            df_res = pd.DataFrame(rows)
            f.write(df_res.to_markdown(index=False))
            f.write("\n\n")

            print(f"Liquidity Warnings: {risk_flags} stocks > 1% impact")
            print(f"Max Impact Cost: {max_impact_cost:.2f}% ({bottleneck_stock})")

            if risk_flags > 5:
                verdict = "NON_SCALABLE"
            elif risk_flags > 0:
                verdict = "CAUTION"
            else:
                verdict = "SCALABLE"

            print(f"Verdict: {verdict}")
            f.write(f"Verdict: {verdict}\n\n")

            scenario_results.append(
                {
                    "aum": int(aum),
                    "risk_flags": int(risk_flags),
                    "max_impact_cost": round(float(max_impact_cost), 4),
                    "bottleneck_stock": bottleneck_stock,
                    "verdict": verdict,
                }
            )

    if not scenario_results:
        print("No scenarios were evaluated.")
        return

    max_flags = max(s["risk_flags"] for s in scenario_results)
    overall_verdict = "SCALABLE" if max_flags == 0 else "CAUTION" if max_flags <= 5 else "NON_SCALABLE"

    json_output = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "vix": round(float(current_vix), 4),
        "crisis_multiplier": float(crisis_multiplier),
        "verdict": overall_verdict,
        "scenarios": scenario_results,
    }
    with open("liquidity.json", "w", encoding="utf-8") as f:
        json.dump(json_output, f, indent=4)

    print("\nReport saved to liquidity_report.md and liquidity.json")


if __name__ == "__main__":
    run_liquidity_check()
