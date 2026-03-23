"""
Price vs Fundamentals Analysis Module.
Computes historical valuation divergence between market price and key fundamentals.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from modules.retry_utils import run_with_exponential_backoff
from modules.data_manager import data_manager


def _safe_float(value) -> Optional[float]:
    """Return finite float or None."""
    try:
        if value is None:
            return None
        if pd.isna(value):
            return None
        parsed = float(value)
        if not np.isfinite(parsed):
            return None
        return parsed
    except Exception:
        return None


def _extract_row_value(frame: pd.DataFrame, labels: List[str], col) -> Optional[float]:
    """Get the first matching row value from a statement frame."""
    if frame is None or frame.empty:
        return None

    for label in labels:
        if label in frame.index:
            return _safe_float(frame.loc[label, col])

    return None


def calculate_cagr(start: Optional[float], end: Optional[float], years: int) -> float:
    """Calculate CAGR in percent, guarding against invalid inputs."""
    if years <= 0:
        return 0.0
    if start is None or end is None:
        return 0.0
    if start <= 0 or end <= 0:
        return 0.0

    return float((((end / start) ** (1 / years)) - 1) * 100)


async def process_fiscal_year_data(
    fy_date,
    financials: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    price_history: pd.DataFrame,
    info: Dict,
) -> Optional[Dict]:
    """Build one fiscal-year point aligned to closest available market price."""
    try:
        if price_history.empty or "Close" not in price_history.columns:
            return None

        closes = price_history["Close"].dropna()
        if closes.empty:
            return None

        price_dates = pd.DatetimeIndex(closes.index).tz_localize(None)
        target_date = pd.Timestamp(fy_date).tz_localize(None)

        nearest_idx = np.argmin(np.abs(price_dates - target_date))
        nearest_date = price_dates[nearest_idx]

        # Skip if we cannot align market price close enough to fiscal close.
        if abs((nearest_date - target_date).days) > 60:
            return None

        price = _safe_float(closes.iloc[nearest_idx])
        if price is None or price <= 0:
            return None

        revenue = _extract_row_value(financials, ["Total Revenue", "Operating Revenue", "Revenue", "Interest Income", "Net Interest Income"], fy_date)
        net_income = _extract_row_value(financials, ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"], fy_date)
        equity = _extract_row_value(balance_sheet, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"], fy_date)
        shares = _extract_row_value(balance_sheet, ["Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"], fy_date)

        if shares is None or shares <= 0:
            shares = _safe_float(info.get("sharesOutstanding"))

        if shares is None or shares <= 0:
            return None

        eps = (net_income / shares) if net_income is not None else None
        sales_per_share = (revenue / shares) if revenue is not None else None
        book_value_per_share = (equity / shares) if equity is not None else None

        pe = (price / eps) if eps is not None and eps > 0 else None
        ps = (price / sales_per_share) if sales_per_share is not None and sales_per_share > 0 else None
        pb = (price / book_value_per_share) if book_value_per_share is not None and book_value_per_share > 0 else None

        return {
            "date": target_date.strftime("%Y-%m-%d"),
            "fiscal_year": f"FY{str(target_date.year)[2:]}",
            "price": round(price, 2),
            "eps": round(eps, 2) if eps is not None else 0.0,
            "sales_per_share": round(sales_per_share, 2) if sales_per_share is not None else 0.0,
            "book_value": round(book_value_per_share, 2) if book_value_per_share is not None else 0.0,
            "pe": round(pe, 2) if pe is not None and pe > 0 else None,
            "ps": round(ps, 2) if ps is not None and ps > 0 else None,
            "pb": round(pb, 2) if pb is not None and pb > 0 else None,
        }
    except Exception:
        return None


def calculate_divergence_analysis(data_points: List[Dict]) -> Dict:
    """Compare price growth with fundamental growth to detect valuation drift."""
    if len(data_points) < 2:
        return {"error": "Insufficient data for divergence analysis"}

    years = len(data_points) - 1

    price_cagr = calculate_cagr(data_points[0].get("price"), data_points[-1].get("price"), years)
    eps_cagr = calculate_cagr(data_points[0].get("eps"), data_points[-1].get("eps"), years)
    sales_cagr = calculate_cagr(data_points[0].get("sales_per_share"), data_points[-1].get("sales_per_share"), years)
    book_value_cagr = calculate_cagr(data_points[0].get("book_value"), data_points[-1].get("book_value"), years)

    divergence_score = price_cagr - eps_cagr

    if abs(divergence_score) < 5:
        alert_level = "NONE"
        analysis = "Price growth is broadly aligned with earnings growth."
    elif abs(divergence_score) < 15:
        alert_level = "MODERATE"
        analysis = (
            f"Price growth is {abs(divergence_score):.1f}% faster than EPS growth."
            if divergence_score > 0
            else f"EPS growth is {abs(divergence_score):.1f}% faster than price growth."
        )
    elif abs(divergence_score) < 25:
        alert_level = "HIGH"
        analysis = (
            f"Price growth materially outpaced EPS by {abs(divergence_score):.1f}%."
            if divergence_score > 0
            else f"EPS growth materially outpaced price by {abs(divergence_score):.1f}%."
        )
    else:
        alert_level = "CRITICAL"
        analysis = (
            f"Price growth strongly outpaced EPS by {abs(divergence_score):.1f}%."
            if divergence_score > 0
            else f"EPS growth strongly outpaced price by {abs(divergence_score):.1f}%."
        )

    pe_start = data_points[0].get("pe")
    pe_end = data_points[-1].get("pe")

    if pe_start and pe_end and pe_start > 0:
        pe_change = ((pe_end - pe_start) / pe_start) * 100
        if pe_change > 20:
            valuation_trend = "EXPANDING"
        elif pe_change < -20:
            valuation_trend = "CONTRACTING"
        else:
            valuation_trend = "STABLE"
    else:
        valuation_trend = "UNKNOWN"

    return {
        "price_cagr": _safe_float(price_cagr),
        "eps_cagr": _safe_float(eps_cagr),
        "sales_cagr": _safe_float(sales_cagr),
        "book_value_cagr": _safe_float(book_value_cagr),
        "divergence_score": _safe_float(divergence_score),
        "alert_level": alert_level,
        "valuation_trend": valuation_trend,
        "analysis": analysis,
        "period": f"{years} years",
    }


def _trend_label(values: List[float]) -> str:
    if len(values) < 2:
        return "STABLE"
    if values[0] == 0:
        return "STABLE"

    change = ((values[-1] - values[0]) / abs(values[0])) * 100
    if change > 10:
        return "RISING"
    if change < -10:
        return "FALLING"
    return "STABLE"


def analyze_ratio_trends(data_points: List[Dict]) -> Dict:
    """Analyze PE/PS/PB trend behavior over fiscal snapshots."""
    pe_values = [p["pe"] for p in data_points if p.get("pe") is not None]
    ps_values = [p["ps"] for p in data_points if p.get("ps") is not None]
    pb_values = [p["pb"] for p in data_points if p.get("pb") is not None]

    result: Dict[str, float] = {}

    if len(pe_values) >= 2:
        current_pe = pe_values[-1]
        percentile = (sum(1 for v in pe_values if v <= current_pe) / len(pe_values)) * 100

        result.update({
            "pe_trend": _trend_label(pe_values),
            "avg_pe": round(float(np.mean(pe_values)), 1),
            "current_pe": round(current_pe, 1),
            "pe_percentile": round(percentile, 0),
            "pe_min": round(min(pe_values), 1),
            "pe_max": round(max(pe_values), 1),
        })

    if len(ps_values) >= 2:
        result.update({
            "ps_trend": _trend_label(ps_values),
            "avg_ps": round(float(np.mean(ps_values)), 2),
            "current_ps": round(ps_values[-1], 2),
        })

    if len(pb_values) >= 2:
        result.update({
            "pb_trend": _trend_label(pb_values),
            "avg_pb": round(float(np.mean(pb_values)), 2),
            "current_pb": round(pb_values[-1], 2),
        })

    return result


async def get_price_vs_fundamentals(symbol: str, years: int = 5) -> Dict:
    """Return historical price vs fundamentals analysis for the symbol."""
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"

    try:
        async def _load_symbol_payload():
            # Use data_manager to fetch fundamentals
            # It returns a dict with info, financials, balance_sheet, history(if we add it there)
            # Currently fetch_fundamentals returns info/financials/balance_sheet
            # and fetch_history returns history df.
            
            # Run in thread pool to avoid blocking async loop since data_manager might be sync
            loop = asyncio.get_running_loop()
            
            fundamentals_task = loop.run_in_executor(None, data_manager.fetch_fundamentals, symbol)
            history_task = loop.run_in_executor(
                None, 
                lambda: data_manager.fetch_history(symbol, period=f"{max(years + 1, 3)}y")
            )
            
            fundamentals, history = await asyncio.gather(fundamentals_task, history_task)
            return fundamentals, history

        # No need for retry_utils here if data_manager handles retries internally?
        # But data_manager calls might fail, so we can keep retry logic at high level too.
        # However, data_manager returns empty/partial on failure rather than raising exception usually?
        # Let's check data_manager implementation. It catches exceptions and returns empty dicts/dfs.
        # So retry wrapper might be redundant if exceptions are swallowed.
        # But let's keep it for now in case of transient network issues not caught inside.
        
        fundamentals, history = await run_with_exponential_backoff(
            _load_symbol_payload,
            context=f"Data Manager fetch for {symbol}",
        )
        
        info = fundamentals.get("info", {})
        financials = fundamentals.get("financials", pd.DataFrame())
        balance_sheet = fundamentals.get("balance_sheet", pd.DataFrame())

        company_name = info.get("longName", symbol.replace(".NS", ""))

        if financials is None or financials.empty or history is None or history.empty:
            return {
                "symbol": symbol,
                "company_name": company_name,
                "data": [],
                "divergence": {},
                "ratios_trend": {},
                "error": "Insufficient data available",
                "timestamp": datetime.now().isoformat(),
            }

        fiscal_dates = list(financials.columns)[:years]
        points: List[Dict] = []

        for fy_date in fiscal_dates:
            point = await process_fiscal_year_data(
                fy_date, financials, balance_sheet, history, info
            )
            if point:
                points.append(point)

        points = sorted(points, key=lambda x: x["date"])

        if len(points) < 2:
            return {
                "symbol": symbol,
                "company_name": company_name,
                "data": points,
                "divergence": {"error": "Insufficient aligned annual points"},
                "ratios_trend": {},
                "timestamp": datetime.now().isoformat(),
            }

        divergence = calculate_divergence_analysis(points)
        ratios_trend = analyze_ratio_trends(points)

        return {
            "symbol": symbol,
            "company_name": company_name,
            "data": points,
            "divergence": divergence,
            "ratios_trend": ratios_trend,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {
            "symbol": symbol,
            "data": [],
            "divergence": {},
            "ratios_trend": {},
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
