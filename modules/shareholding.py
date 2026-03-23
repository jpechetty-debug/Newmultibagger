import asyncio

import numpy as np
import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff


async def get_shareholding_pattern(symbol):
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"

        ticker = yf.Ticker(symbol)

        holders = await run_with_exponential_backoff(
            lambda: asyncio.to_thread(lambda: ticker.major_holders),
            context=f"yfinance shareholding for {symbol}",
        )

        holding_data = {"promoters": 0.0, "institutions": 0.0, "public": 100.0}

        if holders is not None and not holders.empty:
            idx = [str(i).lower() for i in holders.index]
            value_col = holders.columns[0]

            for i, label in enumerate(idx):
                value = holders.iloc[i][value_col]
                if isinstance(value, str):
                    value = float(value.replace("%", ""))
                elif value < 1.1:
                    value = value * 100

                if "insider" in label or "promoter" in label:
                    holding_data["promoters"] = float(value)
                elif "institutionspercent" in label:
                    holding_data["institutions"] = float(value)

        if holding_data["institutions"] == 0:
            try:
                inst = await run_with_exponential_backoff(
                    lambda: asyncio.to_thread(lambda: ticker.institutional_holders),
                    context=f"yfinance institutional holders for {symbol}",
                )
                if inst is not None and not inst.empty and "Pct" in inst.columns:
                    holding_data["institutions"] = float(inst["Pct"].sum() * 100)
            except Exception:
                pass

        total_known = holding_data["promoters"] + holding_data["institutions"]
        if total_known > 100:
            factor = 100 / total_known
            holding_data["promoters"] *= factor
            holding_data["institutions"] *= factor
            holding_data["public"] = 0.0
        else:
            holding_data["public"] = 100 - total_known

        def sanitize_val(value):
            try:
                parsed = float(value)
                if not np.isfinite(parsed):
                    return 0.0
                return parsed
            except Exception:
                return 0.0

        return {
            "symbol": symbol,
            "pattern": {k: round(sanitize_val(v), 2) for k, v in holding_data.items()},
        }
    except Exception as exc:
        return {"error": str(exc)}
