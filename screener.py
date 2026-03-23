
import yfinance as yf  # Kept for Nifty benchmark index only (^NSEI)
import pandas as pd
import numpy as np
import time
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict
from ticker_list import TICKERS
from modules.logger import ScanLogger
import database
from research.conviction_engine import calculate_conviction_score
from modules.fundamentals import (
    calculate_piotroski_f_score, 
    check_earnings_inflection,
    calculate_current_roe,
    calculate_recent_sales_growth,
    calculate_roce,
    calculate_median_pat_growth
)
from modules.estimates import get_estimate_data
from modules.data_manager import DataManager, data_manager
from backtest.engine import VectorBTEngine
import asyncio
from datetime import datetime, date, timedelta
from modules.sector_mapping import get_refined_sector

from modules.scoring import normalize_metric, calculate_sector_medians, calculate_institutional_score
from modules.technicals import calculate_rsi, calculate_macd, calculate_bollinger_bands, calculate_atr, calculate_momentum_features
from modules.models import StockDataPayload
from modules.ml_ranker import LightGBMRanker


@dataclass
class TickerShim:
    """
    Lightweight shim that wraps DataSourceManager output to look like a yfinance Ticker.
    Allows fundamentals.py functions (calculate_piotroski_f_score, etc.) to work
    without modification while benefiting from the fallback chain.
    """
    financials: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    quarterly_financials: pd.DataFrame = field(default_factory=pd.DataFrame)

# --- Utils ---

# --- V3.1: Data Quality Gate ---
_DATA_QUALITY_FIELDS = [
    'PE_Ratio', 'PEG_Ratio', 'ROE%', 'Avg_ROE_5Y%', 'Debt_Equity',
    'EPS_Growth%', 'Sales_Growth_5Y%', 'CFO_PAT_Ratio', 'F_Score', 'Market_Cap_Cr'
]
_DATA_QUALITY_WEIGHTS = {
    "PE_Ratio": 12,
    "PEG_Ratio": 6,
    "ROE%": 12,
    "Avg_ROE_5Y%": 10,
    "Debt_Equity": 8,
    "EPS_Growth%": 10,
    "Sales_Growth_5Y%": 12,
    "CFO_PAT_Ratio": 12,
    "F_Score": 8,
    "Market_Cap_Cr": 10,
}
_SOURCE_CONFIDENCE = {
    "pnsea": 1.00,
    "nsepython": 0.90,
    "yfinance": 0.75,
    "fallback_failed": 0.30,
    "unknown": 0.55,
}
_FETCH_CORE_FIELDS = [
    "Market_Cap_Cr",
    "PE_Ratio",
    "ROE%",
    "Debt_Equity",
    "Sales_Growth_TTM%",
    "CFO_PAT_Ratio",
]
_FETCH_CORE_FLAG_FIELDS = [
    "Market_Cap_Cr",
    "PE_Ratio",
    "ROE%",
    "F_Score",
    "Debt_Equity",
    "Sales_Growth_5Y%",
    "EPS_Growth%",
    "CFO_PAT_Ratio",
]
_INFO_BACKFILL_KEYS = [
    "marketCap",
    "trailingPE",
    "returnOnEquity",
    "debtToEquity",
    "earningsGrowth",
    "revenueGrowth",
    "bookValue",
    "trailingEps",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "sector",
    "industry",
]


def _is_missing_info_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _needs_info_backfill(info):
    if not isinstance(info, dict) or not info:
        return True
    if _is_missing_info_value(info.get("marketCap")):
        return True
    missing = sum(1 for key in _INFO_BACKFILL_KEYS if _is_missing_info_value(info.get(key)))
    return missing >= 5


def _merge_info(primary_info, fallback_info):
    merged = {}
    if isinstance(fallback_info, dict):
        for key, value in fallback_info.items():
            if not _is_missing_info_value(value):
                merged[key] = value
    if isinstance(primary_info, dict):
        for key, value in primary_info.items():
            if not _is_missing_info_value(value):
                merged[key] = value
    if _is_missing_info_value(merged.get("sector")) and not _is_missing_info_value(merged.get("industry")):
        merged["sector"] = merged.get("industry")
    return merged


def _is_finite_number(value):
    if value is None:
        return False
    if isinstance(value, (int, float, np.floating)):
        return np.isfinite(value)
    try:
        parsed = float(value)
        return np.isfinite(parsed)
    except Exception:
        return False


def _is_present_metric(value):
    if not _is_finite_number(value):
        return False
    return float(value) != 0.0


def _freshness_score(price_age_days):
    if price_age_days is None:
        return 20.0
    if price_age_days <= 1:
        return 100.0
    if price_age_days <= 3:
        return 85.0
    if price_age_days <= 7:
        return 65.0
    if price_age_days <= 14:
        return 45.0
    return 20.0

def calculate_data_quality(data, *, zero_valuation_cap=20.0):
    """Weighted data quality score (0-100): completeness + source confidence + freshness."""
    flags = data.get("_dq_flags")
    if not isinstance(flags, dict):
        flags = {field: _is_present_metric(data.get(field)) for field in _DATA_QUALITY_FIELDS}

    total_weight = float(sum(_DATA_QUALITY_WEIGHTS.values()) or 100.0)
    completeness_points = 0.0
    for field in _DATA_QUALITY_FIELDS:
        if bool(flags.get(field, False)):
            completeness_points += float(_DATA_QUALITY_WEIGHTS.get(field, 0))
    completeness_score = (completeness_points / total_weight) * 100.0

    source = str(data.get("Data_Source", "unknown")).strip().lower()
    source_score = float(_SOURCE_CONFIDENCE.get(source, _SOURCE_CONFIDENCE["unknown"])) * 100.0

    price_age_days = data.get("Price_Age_Days")
    try:
        price_age_days = int(price_age_days) if price_age_days is not None else None
    except Exception:
        price_age_days = None
    freshness = _freshness_score(price_age_days)

    final = (0.70 * completeness_score) + (0.20 * source_score) + (0.10 * freshness)
    valuation_missing = not _is_present_metric(data.get("Market_Cap_Cr")) and not _is_present_metric(data.get("PE_Ratio"))
    if valuation_missing:
        final = min(final, float(zero_valuation_cap))
    data["_dq_breakdown"] = {
        "completeness_score": round(completeness_score, 1),
        "source_score": round(source_score, 1),
        "freshness_score": round(freshness, 1),
        "zero_valuation_block": bool(valuation_missing),
    }
    data["_dq_blocked"] = bool(valuation_missing)
    return round(max(0.0, min(100.0, final)), 1)


def validate_fetch_payload(
    data,
    *,
    min_history_bars,
    min_core_fields,
    min_core_fields_by_source=None,
    sparse_sources=None,
    sparse_source_min_core=1,
    hard_block_zero_valuation=True,
    short_history_policy=None,
):
    """Hard fetch-validity gate before counting scan success and before DB write."""
    reasons = []
    soft_flags = []
    source = str(data.get("Data_Source", "unknown")).strip().lower()
    sparse_sources = {str(s).strip().lower() for s in (sparse_sources or []) if s}
    source_thresholds = {}
    for k, v in (min_core_fields_by_source or {}).items():
        if k is None:
            continue
        key = str(k).strip().lower()
        try:
            source_thresholds[key] = int(v)
        except Exception:
            continue
    required_core_fields = int(source_thresholds.get(source, min_core_fields))
    required_history_bars = int(min_history_bars)
    short_history_eligible = False

    policy = short_history_policy or {}
    short_history_enabled = bool(policy.get("enabled", False))
    short_history_soft_flag = str(policy.get("soft_flag", "short_history_ipo")).strip() or "short_history_ipo"
    try:
        short_history_min_bars = int(policy.get("min_bars", min_history_bars))
    except Exception:
        short_history_min_bars = int(min_history_bars)
    try:
        short_history_min_core_fields = int(policy.get("min_core_fields", required_core_fields))
    except Exception:
        short_history_min_core_fields = int(required_core_fields)
    try:
        max_price_age_days = policy.get("max_price_age_days", None)
        short_history_max_price_age_days = int(max_price_age_days) if max_price_age_days is not None else None
    except Exception:
        short_history_max_price_age_days = None

    price = data.get("Price")
    if not _is_finite_number(price) or float(price) <= 0:
        reasons.append("invalid_price")

    history_bars = int(data.get("History_Bars_1Y", 0) or 0)
    price_age_days = data.get("Price_Age_Days")
    try:
        price_age_days = int(price_age_days) if price_age_days is not None else None
    except Exception:
        price_age_days = None

    core_present = 0
    flags = data.get("_dq_flags")
    if isinstance(flags, dict):
        core_present = sum(1 for key in _FETCH_CORE_FLAG_FIELDS if bool(flags.get(key, False)))
    else:
        for field in _FETCH_CORE_FIELDS:
            if _is_present_metric(data.get(field)):
                core_present += 1
        sector = str(data.get("Sector", "") or "").strip()
        if sector and sector.lower() != "unknown":
            core_present += 1

    if core_present < required_core_fields:
        if source in sparse_sources and core_present >= int(sparse_source_min_core):
            soft_flags.append("incomplete_fundamentals")
        else:
            reasons.append("missing_core_fields")

    if history_bars < int(min_history_bars):
        required_short_core = max(required_core_fields, short_history_min_core_fields)
        fresh_enough = (
            short_history_max_price_age_days is None
            or price_age_days is None
            or price_age_days <= short_history_max_price_age_days
        )
        if (
            short_history_enabled
            and history_bars >= short_history_min_bars
            and core_present >= required_short_core
            and fresh_enough
        ):
            short_history_eligible = True
            required_history_bars = short_history_min_bars
            if short_history_soft_flag not in soft_flags:
                soft_flags.append(short_history_soft_flag)
        else:
            reasons.append("short_history")

    if source == "fallback_failed" and core_present == 0:
        reasons.append("no_fundamentals")
    if hard_block_zero_valuation:
        has_mcap = _is_present_metric(data.get("Market_Cap_Cr"))
        has_pe = _is_present_metric(data.get("PE_Ratio"))
        if not has_mcap and not has_pe:
            reasons.append("zero_valuation_fields")

    return {
        "is_valid": len(reasons) == 0,
        "core_fields_present": core_present,
        "required_core_fields": required_core_fields,
        "required_history_bars": required_history_bars,
        "short_history_eligible": short_history_eligible,
        "reasons": reasons,
        "soft_flags": soft_flags,
        "primary_reason": reasons[0] if reasons else None,
    }


def _safe_parse_iso_date(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(str(text)[:10]).date()
    except Exception:
        return None


def load_universe_flags(path_str):
    path = Path(path_str)
    if not path.exists():
        return {"version": 1, "updated_at": None, "symbols": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at": None, "symbols": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "updated_at": None, "symbols": {}}
    payload.setdefault("version", 1)
    payload.setdefault("updated_at", None)
    if not isinstance(payload.get("symbols"), dict):
        payload["symbols"] = {}
    return payload


def save_universe_flags(path_str, payload):
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def refresh_and_get_blocked_symbols(payload, as_of):
    symbols = payload.setdefault("symbols", {})
    blocked = set()
    today_iso = as_of.isoformat()
    for sym, rec in symbols.items():
        if not isinstance(rec, dict):
            continue
        status = str(rec.get("status", "active")).lower()
        if status != "inactive":
            continue
        expires_on = _safe_parse_iso_date(rec.get("expires_on"))
        if expires_on is not None and expires_on < as_of:
            rec["status"] = "active"
            rec["reactivated_on"] = today_iso
            rec["consecutive_failures"] = 0
            continue
        blocked.add(sym.upper())
    return blocked


def update_universe_flags(
    payload,
    failed_reason_by_symbol,
    successful_symbols,
    as_of,
    *,
    failure_threshold,
    cooldown_days,
    min_success_ratio,
    max_new_inactive,
    whitelist,
    reason_thresholds=None,
):
    symbols = payload.setdefault("symbols", {})
    day_iso = as_of.isoformat()
    reason_map = {}
    for sym, reason in (failed_reason_by_symbol or {}).items():
        if not sym:
            continue
        key = str(sym).upper()
        reason_map[key] = str(reason or "fetch_failed")
    failed = set(reason_map.keys())
    successful = {str(s).upper() for s in successful_symbols if s}
    wl = {str(s).upper() for s in whitelist if s}
    reason_thresholds = reason_thresholds or {}

    attempted = len(failed | successful)
    success_ratio = (len(successful) / attempted) if attempted else 0.0

    for sym in successful:
        rec = symbols.setdefault(sym, {})
        rec["last_success_date"] = day_iso
        rec["consecutive_failures"] = 0
        if str(rec.get("status", "active")).lower() == "inactive":
            rec["status"] = "active"
            rec["reactivated_on"] = day_iso

    new_inactive = 0
    if attempted and success_ratio >= min_success_ratio:
        for sym in sorted(failed - wl):
            rec = symbols.setdefault(sym, {})
            reason = reason_map.get(sym, "fetch_failed")
            prev = int(rec.get("consecutive_failures", 0) or 0)
            reason_failures = rec.setdefault("reason_failures", {})
            prev_reason_hits = int(reason_failures.get(reason, 0) or 0)
            # Increment at most once per run/day.
            if rec.get("last_failure_date") != day_iso or rec.get("last_failure_reason") != reason:
                rec["consecutive_failures"] = prev + 1
                rec["total_failures"] = int(rec.get("total_failures", 0) or 0) + 1
                reason_failures[reason] = prev_reason_hits + 1
            rec["last_failure_date"] = day_iso
            rec["last_failure_reason"] = reason

            required = int(reason_thresholds.get(reason, failure_threshold))
            if (
                int(reason_failures.get(reason, 0) or 0) >= required
                and str(rec.get("status", "active")).lower() != "inactive"
                and new_inactive < int(max_new_inactive)
            ):
                rec["status"] = "inactive"
                rec["reason"] = reason
                rec["inactive_since"] = day_iso
                rec["expires_on"] = (as_of + timedelta(days=int(cooldown_days))).isoformat()
                new_inactive += 1

    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    blocked = refresh_and_get_blocked_symbols(payload, as_of)
    return {
        "attempted": attempted,
        "successful": len(successful),
        "failed": len(failed),
        "success_ratio": round(success_ratio, 4),
        "new_inactive": new_inactive,
        "blocked_total": len(blocked),
        "guarded_by_outage": attempted > 0 and success_ratio < min_success_ratio,
    }

def validate_score_distribution(results):
    """Validate score distribution and warn about potential inflation."""
    if not results:
        return {}
    scores = [s.get('Score', 0) for s in results if s.get('Score', 0) > 0]
    total = len(scores)
    if total == 0:
        return {}
    
    dist = {
        '90-100': len([s for s in scores if s >= 90]),
        '80-89':  len([s for s in scores if 80 <= s < 90]),
        '70-79':  len([s for s in scores if 70 <= s < 80]),
        '60-69':  len([s for s in scores if 60 <= s < 70]),
        '<60':    len([s for s in scores if s < 60]),
    }
    
    pct_90 = (dist['90-100'] / total) * 100
    pct_80_plus = ((dist['90-100'] + dist['80-89']) / total) * 100
    
    print(f"\n{'='*50}")
    print(f" SCORE DISTRIBUTION (V3.1 Validation)")
    print(f"{'='*50}")
    for bracket, count in dist.items():
        pct = (count / total) * 100
        bar = '' * int(pct / 2)
        print(f"  {bracket:>6}: {count:>4} ({pct:5.1f}%) {bar}")
    print(f"  Total: {total}")
    
    if pct_90 > 10:
        print(f"    WARNING: {pct_90:.1f}% scored 90+ (expect <10%)  possible grade inflation")
    if pct_80_plus > 30:
        print(f"    WARNING: {pct_80_plus:.1f}% scored 80+ (expect <30%)  review scoring weights")
    
    if pct_90 <= 10 and pct_80_plus <= 30:
        print(f"   Distribution looks healthy")
    print(f"{'='*50}")
    
    return dist

# Global Cache for Benchmark
BENCHMARK_6M_RETURN = None

def get_benchmark_return():
    """Fetches Nifty 50 6M Return once per run."""
    global BENCHMARK_6M_RETURN
    if BENCHMARK_6M_RETURN is not None:
        return BENCHMARK_6M_RETURN
    
    try:
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="1y") # Get 1y to be safe
        
        # --- MARKET CLOSED FIX (Dynamic) ---
        today = datetime.now().date()
        from modules.data_manager import data_manager
        is_valid_trading_day = today in data_manager.valid_trading_days
        is_holiday_or_weekend = not is_valid_trading_day
        
        if not hist.empty and 'Close' in hist.columns:
            hist = hist.dropna(subset=['Close'])
            if len(hist) >= 2 and 'Volume' in hist.columns and (pd.isna(hist['Volume'].iloc[-1]) or hist['Volume'].iloc[-1] == 0 or is_holiday_or_weekend):
                hist = hist.iloc[:-1]

        if len(hist) > 126: # Approx 6 months trading days
            price_6m_ago = hist['Close'].iloc[-126]
            price_now = hist['Close'].iloc[-1]
            BENCHMARK_6M_RETURN = ((price_now - price_6m_ago) / price_6m_ago) * 100
            print(f"Benchmark (Nifty) 6M Return: {BENCHMARK_6M_RETURN:.2f}%")
        else:
            BENCHMARK_6M_RETURN = 10.0 # Default fallback
    except:
        BENCHMARK_6M_RETURN = 10.0
    return BENCHMARK_6M_RETURN

async def get_stock_data(ticker_symbol, dm=None, allow_alpha_vantage=True, include_quarterly=True):
    """
    Fetches comprehensive fundamental and technical data for a stock.
    """
    try:
        # Initialize variables
        sales_growth = 0
        roe = 0
        peg_ratio = 100
        debt_equity = 0
        eps_growth = 0
        
        # --- Fetch data via DataManager (PNSEA -> nsepython -> yf fallback) ---
        _dm = dm if dm else data_manager
        raw = await _dm.async_fetch_fundamentals(ticker_symbol)
        if not isinstance(raw, dict):
            return {"Symbol": ticker_symbol, "_fetch_error": "fetch_failed", "Data_Source": "unknown"}
        info = raw.get("info", {}) if isinstance(raw.get("info", {}), dict) else {}
        data_source = str(raw.get("source", "unknown"))

        # Build a TickerShim so fundamentals.py functions keep working unchanged
        ticker = TickerShim(
            financials=raw.get("financials", pd.DataFrame()),
            balance_sheet=raw.get("balance_sheet", pd.DataFrame()),
            cashflow=raw.get("cash_flow", pd.DataFrame()),
        )

        # Quarterly financials: fetch separately (not part of fundamentals bundle)
        info_backfill = {}
        if include_quarterly or _needs_info_backfill(info):
            try:
                import yfinance as _yf
                _t = _yf.Ticker(ticker_symbol)
                if include_quarterly:
                    ticker.quarterly_financials = _t.quarterly_financials
                else:
                    ticker.quarterly_financials = pd.DataFrame()
                if _needs_info_backfill(info):
                    candidate_info = _t.info
                    if isinstance(candidate_info, dict):
                        info_backfill = candidate_info
            except Exception:
                ticker.quarterly_financials = pd.DataFrame()
        else:
            ticker.quarterly_financials = pd.DataFrame()
        info = _merge_info(info, info_backfill)

        # --- Technicals (Price & Moving Averages) ---
        hist = await _dm.fetch_history(ticker_symbol, period="1y")
        if hist.empty:
            return {
                "Symbol": ticker_symbol,
                "_fetch_error": "no_price_history",
                "Data_Source": data_source,
            }

        history_bars = int(len(hist))
        try:
            last_price_ts = pd.to_datetime(hist.index[-1]).to_pydatetime()
            last_price_date = last_price_ts.date()
            price_age_days = max((date.today() - last_price_date).days, 0)
            last_price_date_iso = last_price_date.isoformat()
        except Exception:
            price_age_days = None
            last_price_date_iso = None
        
        current_price = hist['Close'].iloc[-1]
        if not _is_finite_number(current_price) or float(current_price) <= 0:
            return {
                "Symbol": ticker_symbol,
                "_fetch_error": "invalid_price",
                "Data_Source": data_source,
                "History_Bars_1Y": history_bars,
                "Last_Price_Date": last_price_date_iso,
                "Price_Age_Days": price_age_days,
            }
        
        # Relative Strength (RS)
        # Compare 6M Stock Return vs Nifty 6M Return
        rs_rating = 0
        try:
            if len(hist) > 126:
                price_6m_ago = hist['Close'].iloc[-126]
                stock_6m_ret = ((current_price - price_6m_ago) / price_6m_ago) * 100
                nifty_6m_ret = get_benchmark_return()
                
                # RS Ratio
                if nifty_6m_ret != 0 and price_6m_ago != 0:
                    rs_rating = round(stock_6m_ret / nifty_6m_ret, 2)
                else:
                    rs_rating = 1.0 if stock_6m_ret > 0 else 0.0
            else:
                rs_rating = 0
        except:
            rs_rating = 0
        
        dma_200 = hist['Close'].tail(200).mean() if len(hist) >= 200 else hist['Close'].mean()
        dma_50 = hist['Close'].tail(50).mean() if len(hist) >= 50 else hist['Close'].mean()
        
        rsi_series = calculate_rsi(hist['Close'])
        rsi_current = rsi_series.iloc[-1]
        
        # --- Phase 6: Advanced Technicals ---
        # --- Phase 12: Momentum Ranking Features ---
        mom_features = calculate_momentum_features(hist)
        
        # MACD
        macd, signal, macd_hist = calculate_macd(hist['Close'])
        macd_val = macd.iloc[-1]
        signal_val = signal.iloc[-1]
        macd_bullish = macd_val > signal_val
        
        # Bollinger Bands
        bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(hist['Close'])
        bb_up_val = bb_upper.iloc[-1]
        bb_low_val = bb_lower.iloc[-1]
        
        # --- Phase 9: Risk Management ---
        atr_series = calculate_atr(hist['High'], hist['Low'], hist['Close'])
        atr_current = atr_series.iloc[-1]
        stop_loss, max_qty = calculate_risk_params(current_price, atr_current, capital=100000, risk_per_trade=0.02) # 2% risk standard
        
        # Technical Signal
        if macd_bullish and rsi_current > 50:
            tech_signal = "Bullish"
        elif not macd_bullish and rsi_current < 50:
            tech_signal = "Bearish"
        else:
            tech_signal = "Neutral"
        
        # --- Fundamentals ---
        roe = info.get('returnOnEquity', 0)
        roe = 0 if roe is None else roe
        
        sales_growth = info.get('revenueGrowth', 0)
        sales_growth = 0 if sales_growth is None else sales_growth
        
        profit_margin = info.get('profitMargins', 0)
        profit_margin = 0 if profit_margin is None else profit_margin
        
        eps_growth = info.get('earningsGrowth', 0)
        eps_growth = 0 if eps_growth is None else eps_growth

        # --- Phase 68: Robust Fundamental Fallbacks ---
        # If yfinance summary fails (None/0 for NSE), derive from financial statements
        if roe == 0:
            roe_derived = calculate_current_roe(ticker)
            if roe_derived > 0:
                roe = roe_derived / 100.0 # Convert back to decimal to match yf logic

        if sales_growth == 0:
            sales_growth_derived = calculate_recent_sales_growth(ticker)
            if sales_growth_derived > 0:
                sales_growth = sales_growth_derived / 100.0

        debt_equity = info.get('debtToEquity', 0) or 0
        if debt_equity > 10: debt_equity = debt_equity / 100
        
        peg_ratio = info.get('pegRatio')
        if peg_ratio is not None:
             peg_ratio = round(float(peg_ratio), 2)

        promoter_holding = (info.get('heldPercentInsiders', 0) or 0) * 100
        inst_holding = (info.get('heldPercentInstitutions', 0) or 0) * 100
        
        # Pledge Percentage (NSE specific often found in 'pledgedPercent' or similar)
        pledge_pct = info.get('pledgedPercent', 0) or 0
        if pledge_pct > 1: pledge_pct = pledge_pct # already in pct 
        else: pledge_pct = pledge_pct * 100 # convert from decimal
        
        total_smart_money = promoter_holding + inst_holding

        # Cashflow
        free_cashflow = info.get('freeCashflow', 0)
        operating_cashflow = info.get('operatingCashflow', 0)
        
        # 2. Sales Growth & ROE (5-Year) & Earnings Acceleration
        financials = ticker.financials
        revenue_cagr_5y = 0
        avg_roe_5y = 0
        earnings_accel = False
        
        if not financials.empty:
            try:
                revs = financials.loc['Total Revenue'].iloc[::-1]
                if len(revs) >= 4 and revs.iloc[0] != 0:
                    try:
                        cagr_rev = (revs.iloc[-1] / revs.iloc[0]) ** (1/(len(revs)-1)) - 1
                        revenue_cagr_5y = round(cagr_rev * 100, 2)
                    except ZeroDivisionError:
                        revenue_cagr_5y = round(sales_growth * 100, 2)
                else:
                    revenue_cagr_5y = round(sales_growth * 100, 2)
                
                # Avg ROE
                net_income_series = financials.loc['Net Income'].iloc[::-1]
                bs = ticker.balance_sheet
                if not bs.empty and 'Stockholders Equity' in bs.index:
                    equity_series = bs.loc['Stockholders Equity'].iloc[::-1]
                    roes = []
                    common_dates = net_income_series.index.intersection(equity_series.index)
                    for date in common_dates:
                        ni = net_income_series[date]
                        eq = equity_series[date]
                        if eq > 0: roes.append(ni / eq)
                    if roes: avg_roe_5y = round(float(np.median(roes)) * 100, 2)
                else:
                    avg_roe_5y = round(roe * 100, 2)
            except: 
                revenue_cagr_5y = round(sales_growth * 100, 2)
                avg_roe_5y = round(roe * 100, 2)
        
        # --- Multibagger Framework: ROCE & Median PAT Growth ---
        roce = calculate_roce(ticker)
        median_pat_growth_5y = calculate_median_pat_growth(ticker, years=5)
        
        # Earnings Acceleration is now calculated via check_earnings_inflection below

        # 3. CFO / PAT Ratio
        try:
            cfo = info.get('operatingCashflow')
            pat = info.get('netIncomeToCommon') or (info.get('trailingEps',0) * info.get('sharesOutstanding',0))
            if cfo and pat and pat > 0:
                cfo_pat_ratio = round(cfo / pat, 2)
            else:
                cfo_pat_ratio = 0
        except:
            cfo_pat_ratio = 0

        # --- F-Score Metrics (Full 9-Point Piotroski) ---
        f_score_method = "9pt_piotroski"
        try:
            f_score = calculate_piotroski_f_score(ticker)
        except Exception:
            f_score = 0
        
        # Fallback: If 9pt F-Score returns 0 (empty financials), use inline estimate
        if f_score == 0:
            f_score_method = "5pt_inline"
            f_roa = 1 if info.get('returnOnAssets', 0) and info.get('returnOnAssets', 0) > 0 else 0
            f_cfo = 1 if info.get('operatingCashflow', 0) and info.get('operatingCashflow', 0) > 0 else 0
            net_income_f = info.get('netIncomeToCommon', 0)
            op_cash_f = info.get('operatingCashflow', 0)
            f_quality = 1 if (op_cash_f is not None and net_income_f is not None and op_cash_f > net_income_f) else 0
            f_leverage = 1 if debt_equity < 0.4 else 0
            f_margin = 1 if info.get('grossMargins', 0) and info.get('grossMargins', 0) > 0 else 0
            f_score = f_roa + f_cfo + f_quality + f_leverage + f_margin

        # --- Earnings Inflection (Rich 0-5 Score) ---
        try:
            inflection = check_earnings_inflection(ticker)
            earnings_inflection_score = inflection.get('score', 0)
            earnings_accel = inflection.get('status', False)
        except Exception:
            earnings_inflection_score = 0
            earnings_accel = False

        # Sector Refinement
        sector = get_refined_sector(
            ticker_symbol, 
            info.get('longName', ''), 
            info.get('sector', 'Unknown'), 
            info.get('industry', 'Unknown')
        )
        industry = info.get('industry', 'Unknown')

        # --- 8-Point Metrics ---
        trailing_pe = info.get('trailingPE')
        if trailing_pe is not None:
            trailing_pe = round(float(trailing_pe), 2)
        market_cap_crore = info.get('marketCap', 0) / 10000000
        
        # 52W Range Extraction
        high_52w = info.get('fiftyTwoWeekHigh', current_price) or current_price
        low_52w = info.get('fiftyTwoWeekLow', current_price) or current_price
        
        down_from_high_pct = 0
        if high_52w > 0:
            down_from_high_pct = round(((high_52w - current_price) / high_52w) * 100, 2)
            
        # --- Phase 2: Valuation Rigidity Fixes & Cyclical EPS Normalization ---
        book_value = info.get('bookValue', 0)
        eps_ttm = info.get('trailingEps', 0)
        graham_num = 0
        value_gap = 0
        
        if book_value and book_value > 0:
            try:
                # 1. Cyclical PE Normalization & Growth Capping
                # Smooth boom/bust cyclical EPS by looking at baseline 5Y ROE
                if avg_roe_5y > 0:
                    # Normal cycle EPS based on historical ROE rather than just TTM
                    normalized_eps = (avg_roe_5y / 100.0) * book_value
                    # Cap abnormal TTM spikes (max 50% above normalized historical)
                    safe_eps = min(eps_ttm, normalized_eps * 1.5) if eps_ttm > 0 else normalized_eps
                else:
                    safe_eps = eps_ttm
                
                # If STILL negative after normalization, trigger Asset Floor fallback
                if safe_eps <= 0:
                    # Asset/Book Value fallback for negative EPS stocks (preventing zero-collapse)
                    # Assign liquidation/replacement value floor at 80% Book Value
                    graham_num = round(book_value * 0.8, 2)
                else:
                    # Dynamic Graham multiplier based on growth trajectory, capped at 25
                    fwd_pe = info.get('forwardPE', 15) or 15
                    base_multiplier = min(25.0, max(7.0, fwd_pe * 1.5)) 
                    
                    # Phase 5: Debt-Aware Fair Value Integration (Leverage Penalty)
                    raw_de = info.get('debtToEquity', 0)
                    debt_eq = raw_de / 100.0 if raw_de is not None else 0
                    if debt_eq > 1.0:
                        # De-rate the fair value expansion multiplier heavily for high debt
                        # Example: D/E = 3.0 -> penalty = 0.60 -> Shrinks valuation by 40%
                        leverage_penalty = max(0.5, 1.0 - (debt_eq - 1.0) * 0.2)
                        base_multiplier *= leverage_penalty

                    graham_num = round((base_multiplier * safe_eps * book_value) ** 0.5, 2)
                    
                # Value Gap %: (Intrinsic - Price) / Price
                if current_price > 0:
                    value_gap = round(((graham_num - current_price) / current_price) * 100, 2)
            except:
                graham_num = 0
                
        # --- Phase 7: Institutional Analyst Estimates (V7.0) ---
        est_analysis = get_estimate_data(
            ticker_symbol,
            info=info,
            allow_alpha_vantage=allow_alpha_vantage,
        )
        m_est = est_analysis.get("momentum")
        
        # Default from yfinance (kept as base if no momentum data)
        analyst_rating = info.get('recommendationKey', 'none').replace('_', ' ').title()
        target_mean = info.get('targetMeanPrice', 0)
        analyst_count = info.get('numberOfAnalystOpinions', 0)
        
        # High-Fidelity Override Logic (from manual_seed or Alpha Vantage)
        if est_analysis.get("source") == "manual_seed":
            seed = est_analysis.get("estimates", {})
            analyst_rating = seed.get("consensus", analyst_rating)
            target_mean = seed.get("target_high", target_mean) # We use High target for elite conviction
            analyst_count = seed.get("analyst_count", analyst_count)
        
        analyst_upside = 0
        if target_mean and target_mean > 0 and current_price > 0:
            analyst_upside = round(((target_mean - current_price) / current_price) * 100, 2)
            
        # Extract Momentum Signals for scoring
        momentum_signal = m_est.get("momentum_signal", "STABLE") if m_est else "STABLE"
        estimate_score_adj = m_est.get("score_adjustment", 0) if m_est else 0
            
        # Phase 22: Volume Data
        avg_vol_10d = info.get('averageVolume10days', info.get('averageVolume', 0))

        # Data-quality availability flags (presence-based, not score/value-based).
        dq_flags = {
            "PE_Ratio": trailing_pe is not None and trailing_pe > 0,
            "PEG_Ratio": peg_ratio is not None and np.isfinite(peg_ratio) and peg_ratio != 0,
            "ROE%": _is_finite_number(info.get('returnOnEquity')) or _is_present_metric(round(roe * 100, 2)),
            "Avg_ROE_5Y%": _is_present_metric(avg_roe_5y),
            "Debt_Equity": _is_finite_number(info.get('debtToEquity')),
            "EPS_Growth%": _is_finite_number(info.get('earningsGrowth')),
            "Sales_Growth_5Y%": _is_present_metric(revenue_cagr_5y) or _is_finite_number(info.get('revenueGrowth')),
            "CFO_PAT_Ratio": _is_present_metric(cfo_pat_ratio),
            "F_Score": (f_score_method == "9pt_piotroski") or (
                f_score > 0 and (
                    info.get('returnOnAssets') is not None or info.get('operatingCashflow') is not None
                )
            ),
            "Market_Cap_Cr": _is_present_metric(market_cap_crore),
        }
                
        final_data = {
            "Symbol": ticker_symbol,
            "Price": current_price,
            "Data_Source": data_source,
            "History_Bars_1Y": history_bars,
            "Last_Price_Date": last_price_date_iso,
            "Price_Age_Days": price_age_days,
            "Avg_Volume_10D": avg_vol_10d, # Added for Phase 22
            "Sector": sector,
            "Industry": industry,
            "Market_Cap_Cr": round(market_cap_crore, 2),
            "200_DMA": dma_200,
            "50_DMA": dma_50,
            "RSI": round(rsi_current, 2),
            "Sales_Growth_TTM%": round(sales_growth * 100, 2),
            "Sales_Growth_5Y%": revenue_cagr_5y,
            "ROE%": round(roe * 100, 2),
            "Avg_ROE_5Y%": avg_roe_5y,
            "Profit_Margin%": round(profit_margin * 100, 2),
            "Debt_Equity": round(debt_equity, 2) if debt_equity is not None else None,
            "PEG_Ratio": peg_ratio,
            "PE_Ratio": trailing_pe,
            "Down_From_52W_High%": down_from_high_pct,
            "Smart_Money%": round(total_smart_money * 100, 2),
            "Free_Cashflow": free_cashflow,
            "CFO_PAT_Ratio": cfo_pat_ratio,
            "EPS_Growth%": round(eps_growth * 100, 2),
            "F_Score": f_score,
            "F_Score_Method": f_score_method,
            "RS_Rating": rs_rating,
            "Earnings_Accel": earnings_accel,
            "Earnings_Inflection_Score": earnings_inflection_score,
            "Graham_Number": graham_num,
            "Value_Gap%": value_gap,
            "Technical_Signal": tech_signal,
            "MACD_Bullish": macd_bullish,
            "Analyst_Rating": analyst_rating,
            "Target_Mean_Price": target_mean,
            "Analyst_Upside%": analyst_upside,
            "Analyst_Count": analyst_count,
            "Promoter_Holding%": round(promoter_holding * 100, 2),
            "Inst_Holding%": round(inst_holding * 100, 2),
            "ATR": round(atr_current, 2),
            "Stop_Loss_ATR": stop_loss,
            "Max_Qty_1L": max_qty,
            "Estimate_Score_Adj": estimate_score_adj,
            "Momentum_Signal": momentum_signal,
            "High_52W": round(float(high_52w), 2),
            "Low_52W": round(float(low_52w), 2),
            "ROCE%": roce,
            "Median_PAT_Growth_5Y%": median_pat_growth_5y,
            "Pledge_Pct": pledge_pct,
            "Ret_1M": mom_features.get("ret_1m", 0),
            "Ret_3M": mom_features.get("ret_3m", 0),
            "Ret_6M": mom_features.get("ret_6m", 0),
            "Vol_Breakout": mom_features.get("vol_breakout", 1.0),
            "Dist_From_52W_High": mom_features.get("dist_from_52w_high", 0),
            "_dq_flags": dq_flags,
        }
        
        # --- V7.1: FUNDAMENTALS OVERRIDE LAYER ---
        # If the analyst seed provides hard fundamentals, override the dict
        f_override = m_est.get("fundamentals_override") if m_est else None
        if f_override:
            for k, v in f_override.items():
                if v is not None:
                    final_data[k] = v
        
        # --- Pydantic Validation ---
        try:
            payload = StockDataPayload(**final_data)
            return payload.model_dump(by_alias=True)
        except Exception as e:
            import logging
            logging.error(f"Pydantic Validation Error for {ticker_symbol}: {e}")
            return final_data

    except Exception as e:
        return {
            "Symbol": ticker_symbol,
            "_fetch_error": "fetch_exception",
            "_fetch_error_detail": str(e)[:180],
            "Data_Source": "unknown",
        }

# ============== V6.0: SECTOR-RELATIVE SCORING ==============
# calculate_sector_medians moved to modules/scoring.py

# calculate_institutional_score moved to modules/scoring.py

def analyze_sector_rotation(stock_list):
    """
    Analyzes sector performance based on 3M returns of stocks in the list.
    Returns a dict of Sector -> Avg Return.
    """
    sector_returns = {}
    sector_counts = {}
    
    print("\nCalculating Sector Rotation...")
    for stock in stock_list:
        sec = stock.get("Sector", "Unknown")
        rs = stock.get("RS_Rating", 0)
        
        if sec not in sector_returns:
            sector_returns[sec] = 0.0
            sector_counts[sec] = 0
        
        sector_returns[sec] += rs
        sector_counts[sec] += 1
        
    # Average
    avg_sector_rs = {}
    for sec, total_rs in sector_returns.items():
        if sector_counts[sec] > 0:
            avg_sector_rs[sec] = total_rs / sector_counts[sec]
            
    # Sort
    sorted_sectors = sorted(avg_sector_rs.items(), key=lambda x: x[1], reverse=True)
    
    print("Top 3 Leading Sectors (by RS):")
    top_3 = []
    for i, (sec, rs) in enumerate(sorted_sectors[:3]):
        print(f"{i+1}. {sec}: Avg RS {rs:.2f}")
        top_3.append(sec)
        
    return top_3

def calculate_macd(prices, slow=26, fast=12, signal=9):
    """
    Calculates MACDLine, SignalLine, and Histogram.
    Returns (macd_line, signal_line, histogram)
    """
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line
    return macd, signal_line, hist

def calculate_bollinger_bands(prices, window=20, num_std=2):
    """
    Calculates Upper, Middle, Lower bands.
    """
    rolling_mean = prices.rolling(window=window).mean()
    rolling_std = prices.rolling(window=window).std()
    upper = rolling_mean + (rolling_std * num_std)
    lower = rolling_mean - (rolling_std * num_std)
    return upper, rolling_mean, lower

def calculate_atr(high, low, close, period=14):
    """
    Calculates Average True Range (ATR).
    """
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return atr

def calculate_risk_params(price, atr, capital=100000, risk_per_trade=0.01):
    """
    Calculates Stop Loss and Position Size.
    Risk = 2 * ATR
    """
    stop_loss = price - (2 * atr)
    risk_per_share = price - stop_loss
    
    if risk_per_share <= 0:
        return stop_loss, 0
        
    risk_amount = capital * risk_per_trade
    qty = int(risk_amount / risk_per_share)
    
    return round(stop_loss, 2), qty

def calculate_trade_setup(stock):
    """
    Calculates standard Buy Below, Stop Loss, and Target prices.
    Phase 10: Standardized Trade Setup logic.
    """
    if not stock or "Price" not in stock:
        return stock
        
    cmp = stock["Price"]
    if cmp and cmp > 0:
        stock["Buy_Below"] = round(cmp * 1.02, 1)
        
        # Use ATR-based stop loss if available, otherwise default 10%
        atr_sl = stock.get("Stop_Loss_ATR")
        if atr_sl and atr_sl > 0:
            stock["Stop_Loss"] = round(atr_sl, 1)
        else:
            stock["Stop_Loss"] = round(cmp * 0.90, 1)
            
        stock["Target_1"] = round(cmp * 1.25, 1)
        
    return stock

def analyze_market_regime(symbol="^NSEI"):
    """
    Determines Market Regime: Bull, Bear, Correction, Sideways.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y") # Need 200 DMA
        
        if len(hist) < 200:
            return "Unknown"
            
        sma_50 = hist['Close'].tail(50).mean()
        sma_200 = hist['Close'].tail(200).mean()
        current_price = hist['Close'].iloc[-1]
        
        if current_price > sma_50 and sma_50 > sma_200:
            return "Bull Market"
        elif current_price < sma_50 and sma_50 < sma_200:
            return "Bear Market"
        elif current_price < sma_50 and current_price > sma_200:
            return "Correction"
        elif current_price > sma_50 and current_price < sma_200:
            return "Recovery"
        else:
            return "Sideways"
    except:
        return "Unknown"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Institutional Screener v3.0")
    parser.add_argument("--mode", type=str, default="balanced", choices=["balanced", "momentum", "value", "quality", "auto"], help="Scoring Strategy Mode")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated list of symbols to scan (e.g. TCS.NS,RELIANCE.NS)")
    parser.add_argument("--smoke", action="store_true", help="Run a quick smoke test on 10 symbols")
    parser.add_argument("--universe", type=str, default="STANDARD", help="Custom universe name (e.g. SECTORS)")
    args = parser.parse_args()

    import config
    from ticker_list import TICKERS, MULTIBAGGER_HUNT, SECTORS

    targeted_symbols = {s.strip().upper() for s in args.symbols.split(",")} if args.symbols else set()
    is_full_scan = len(targeted_symbols) == 0
    
    # Process universe and symbols override
    scan_tickers = TICKERS
    active_filters = None

    if args.universe.upper() == "SECTORS":
        scan_tickers = SECTORS
        active_filters = MULTIBAGGER_HUNT.get("filters")
        print(f" Specialized Universe: SECTORS ({len(scan_tickers)} symbols)")
        print(f" Applying Framework Filters: {MULTIBAGGER_HUNT.get('desc')}")
    elif args.symbols:
        scan_tickers = sorted(targeted_symbols)
        print(f" Targeted Scan: {scan_tickers}")
    elif args.smoke:
        scan_tickers = scan_tickers[:10]
        print(f" Smoke Test: Scanning first 10 symbols")

    # Auto-prune/flag integration: skip currently inactive symbols for full scans.
    auto_flag_enable = bool(getattr(config, "AUTO_FLAG_INVALID_SYMBOLS", True))
    flags_path = str(getattr(config, "UNIVERSE_FLAGS_PATH", "data/universe_flags.json"))
    flag_whitelist = {str(s).upper() for s in getattr(config, "AUTO_FLAG_WHITELIST", [])}
    universe_flags = None
    if is_full_scan and auto_flag_enable:
        universe_flags = load_universe_flags(flags_path)
        blocked = refresh_and_get_blocked_symbols(universe_flags, date.today())
        blocked_effective = blocked - flag_whitelist
        if blocked_effective:
            before = len(scan_tickers)
            scan_tickers = [s for s in scan_tickers if str(s).upper() not in blocked_effective]
            print(
                f"Universe flags: skipped {before - len(scan_tickers)} inactive symbols "
                f"(active blocked total: {len(blocked_effective)})."
            )
    
    # Auto-Regime Detection
    final_mode = args.mode
    if args.mode == "auto":
        print(" Auto-Regime: Analyzing Market Structure...")
        from modules.market_data import MarketDataProvider
        provider = MarketDataProvider()
        regime_data = provider.get_market_regime()
        final_mode = regime_data["strategy_suggestion"].lower()
        print(f" Auto-Selected Mode: {final_mode.upper()} (Confidence: High)")
        
    print(f"Scanning {len(scan_tickers)} stocks for Institutional Analysis (Phase 10)...")
    print(f"Strategy Mode: {final_mode.upper()}")
    
    # --- Model Version Check (Phase 2.2) ---
    from modules.logger import ScanLogger
    
    logger = ScanLogger()
    current_hash = logger._generate_version_hash()
    
    if current_hash != config.MODEL_VERSION_HASH:
        print("\n" + "!"*60)
        print(f"  MODEL INTEGRITY WARNING: Version Mismatch!")
        print(f"Expected: {config.MODEL_VERSION} ({config.MODEL_VERSION_HASH})")
        print(f"Actual:   {current_hash}")
        print("Code logic has changed since version freeze.")
        print("!"*60 + "\n")
        # In Strict Mode, we would exit here. For now, just warn.
    else:
        print(f" Model Integrity Verified: {config.MODEL_VERSION} ({current_hash})")
        
    results = []
    
    # Phase 10: Market Regime
    market_regime = analyze_market_regime()
    print(f"Market Regime Detected: {market_regime}")
    
    # 1. Fetch All Data
    min_mcap = getattr(config, 'MIN_MARKET_CAP_CR', 500)
    min_dq = float(getattr(config, 'MIN_DATA_QUALITY', 50))
    min_history_bars = int(getattr(config, "MIN_HISTORY_BARS", 120))
    min_fetch_core_fields = int(getattr(config, "MIN_FETCH_CORE_FIELDS", 2))
    min_fetch_core_fields_by_source = getattr(config, "MIN_FETCH_CORE_FIELDS_BY_SOURCE", {})
    sparse_fundamental_sources = getattr(config, "SPARSE_FUNDAMENTAL_SOURCES", ["pnsea"])
    sparse_source_min_core_fields = int(getattr(config, "SPARSE_SOURCE_MIN_CORE_FIELDS", 1))
    hard_block_zero_valuation_fields = bool(getattr(config, "HARD_BLOCK_ZERO_VALUATION_FIELDS", True))
    dq_zero_valuation_cap = float(getattr(config, "DQ_ZERO_VALUATION_CAP", 20.0))
    full_scan_base_concurrency = int(getattr(config, "FULL_SCAN_BASE_CONCURRENCY", 12))
    targeted_scan_concurrency = int(getattr(config, "TARGET_SCAN_CONCURRENCY", 20))
    full_scan_retry_enabled = bool(getattr(config, "FULL_SCAN_RETRY_ENABLED", True))
    full_scan_retry_min_concurrency = int(getattr(config, "FULL_SCAN_RETRY_MIN_CONCURRENCY", 4))
    full_scan_retry_max_concurrency = int(getattr(config, "FULL_SCAN_RETRY_MAX_CONCURRENCY", 10))
    full_scan_retry_backoff_seconds = float(getattr(config, "FULL_SCAN_RETRY_BACKOFF_SECONDS", 2.0))
    full_scan_retry_transient_reasons = {
        str(x).strip()
        for x in getattr(
            config,
            "FULL_SCAN_RETRY_TRANSIENT_REASONS",
            ["fetch_failed", "fetch_exception", "no_price_history", "invalid_price"],
        )
    }
    if not full_scan_retry_transient_reasons:
        full_scan_retry_transient_reasons = {"fetch_failed", "fetch_exception", "no_price_history", "invalid_price"}
    ipo_short_history_enabled = bool(getattr(config, "IPO_SHORT_HISTORY_POLICY_ENABLE", True))
    ipo_short_history_min_bars = int(getattr(config, "IPO_SHORT_HISTORY_MIN_BARS", 90))
    ipo_short_history_min_core_fields = int(getattr(config, "IPO_SHORT_HISTORY_MIN_CORE_FIELDS", 4))
    ipo_short_history_max_price_age_days = getattr(config, "IPO_SHORT_HISTORY_MAX_PRICE_AGE_DAYS", 7)
    ipo_short_history_soft_flag = str(getattr(config, "IPO_SHORT_HISTORY_SOFT_FLAG", "short_history_ipo")).strip() or "short_history_ipo"
    ipo_short_history_dq_penalty = float(getattr(config, "IPO_SHORT_HISTORY_DQ_PENALTY", 8.0))
    ipo_short_history_policy = {
        "enabled": ipo_short_history_enabled,
        "min_bars": ipo_short_history_min_bars,
        "min_core_fields": ipo_short_history_min_core_fields,
        "max_price_age_days": ipo_short_history_max_price_age_days,
        "soft_flag": ipo_short_history_soft_flag,
    }
    full_scan_min_pass_ratio = float(getattr(config, 'FULL_SCAN_MIN_PASS_RATIO', 0.20))
    full_scan_dq_floor = float(getattr(config, 'FULL_SCAN_DQ_FLOOR', 30))
    full_scan_disable_av = bool(getattr(config, 'FULL_SCAN_DISABLE_ALPHA_VANTAGE', True))
    auto_flag_failure_threshold = int(getattr(config, "AUTO_FLAG_FAILURE_THRESHOLD", 1))
    auto_flag_cooldown_days = int(getattr(config, "AUTO_FLAG_COOLDOWN_DAYS", 14))
    auto_flag_min_success_ratio = float(getattr(config, "AUTO_FLAG_MIN_SUCCESS_RATIO", 0.40))
    auto_flag_max_new_inactive = int(getattr(config, "AUTO_FLAG_MAX_NEW_INACTIVE_PER_RUN", 300))
    auto_flag_reason_thresholds = getattr(config, "AUTO_FLAG_REASON_THRESHOLDS", {})
    allow_alpha_vantage = not (is_full_scan and full_scan_disable_av)
    if is_full_scan and full_scan_disable_av:
        print("Full-scan mode: Alpha Vantage disabled (quota-safe fallback enabled).")
    skipped_mcap = 0
    scan_failed_reason_by_symbol = {}
    scan_success_symbols = set()
    
    # Run the async fetch loop
    async def fetch_all_data(dm):
        print(f"Fetching data for {len(scan_tickers)} stocks concurrently...")

        def _extract_hard_error(payload):
            if isinstance(payload, Exception) or payload is None or not isinstance(payload, dict):
                return "fetch_failed"
            return str(payload.get("_fetch_error", "") or "").strip() or None

        def _compute_retry_concurrency(base_concurrency, fail_count, total_count):
            if total_count <= 0:
                return max(full_scan_retry_min_concurrency, min(full_scan_retry_max_concurrency, base_concurrency))
            fail_ratio = float(fail_count) / float(total_count)
            scaled = int(round(base_concurrency * (1.0 - min(0.75, fail_ratio) * 0.6)))
            return max(full_scan_retry_min_concurrency, min(full_scan_retry_max_concurrency, scaled))

        async def _fetch_symbol(dm_instance, symbol, include_quarterly):
            try:
                return await get_stock_data(
                    symbol,
                    dm=dm_instance,
                    allow_alpha_vantage=allow_alpha_vantage,
                    include_quarterly=include_quarterly,
                )
            except Exception as e:
                return {
                    "Symbol": symbol,
                    "_fetch_error": "fetch_exception",
                    "_fetch_error_detail": str(e)[:180],
                    "Data_Source": "unknown",
                }

        async def _run_batch(symbols_batch, dm_instance, *, include_quarterly):
            tasks = [
                _fetch_symbol(dm_instance, sym, include_quarterly=include_quarterly)
                for sym in symbols_batch
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        raw_results = await _run_batch(scan_tickers, dm, include_quarterly=not is_full_scan)
        retry_attempted = 0
        retry_recovered = 0
        retry_concurrency = None
        if is_full_scan and full_scan_retry_enabled and raw_results:
            retry_indexes = []
            for idx, payload in enumerate(raw_results):
                reason = _extract_hard_error(payload)
                if reason and reason in full_scan_retry_transient_reasons:
                    retry_indexes.append(idx)
            retry_attempted = len(retry_indexes)
            if retry_attempted:
                retry_symbols = [scan_tickers[i] for i in retry_indexes]
                base_concurrency = max(4, int(full_scan_base_concurrency))
                retry_concurrency = _compute_retry_concurrency(base_concurrency, retry_attempted, len(scan_tickers))
                print(
                    f"Retry pass: attempting {retry_attempted} transient failures "
                    f"with concurrency={retry_concurrency}."
                )
                if full_scan_retry_backoff_seconds > 0:
                    await asyncio.sleep(full_scan_retry_backoff_seconds)
                async with DataManager(max_concurrency=retry_concurrency) as dm_retry:
                    retry_results = await _run_batch(retry_symbols, dm_retry, include_quarterly=False)
                for i, payload_retry in zip(retry_indexes, retry_results):
                    if _extract_hard_error(payload_retry) is None:
                        retry_recovered += 1
                        raw_results[i] = payload_retry
                print(f"Retry pass complete: recovered={retry_recovered}/{retry_attempted}.")
        
        candidate_data = []
        initial_pass = []
        fetch_failures_raw = 0
        fetch_rejected = 0
        fetch_short_history_rejected = 0  # Track IPO/short-history separately
        fetch_soft_flagged = 0
        failure_reason_counts = {}
        effective_min_dq = min_dq
        rejected_preview = []
        soft_preview = []
        nonlocal skipped_mcap
        
        for symbol, data in zip(scan_tickers, raw_results):
            sym_u = str(symbol).upper()
            if isinstance(data, Exception) or data is None or not isinstance(data, dict):
                fetch_failures_raw += 1
                scan_failed_reason_by_symbol[sym_u] = "fetch_failed"
                failure_reason_counts["fetch_failed"] = int(failure_reason_counts.get("fetch_failed", 0)) + 1
                continue

            hard_error = str(data.get("_fetch_error", "") or "").strip()
            if hard_error:
                fetch_failures_raw += 1
                scan_failed_reason_by_symbol[sym_u] = hard_error
                failure_reason_counts[hard_error] = int(failure_reason_counts.get(hard_error, 0)) + 1
                continue
                
            mcap = data.get("Market_Cap_Cr", 0)
            if mcap > 0 and mcap < min_mcap:
                skipped_mcap += 1
                continue

            fetch_gate = validate_fetch_payload(
                data,
                min_history_bars=min_history_bars,
                min_core_fields=min_fetch_core_fields,
                min_core_fields_by_source=min_fetch_core_fields_by_source,
                sparse_sources=sparse_fundamental_sources,
                sparse_source_min_core=sparse_source_min_core_fields,
                hard_block_zero_valuation=hard_block_zero_valuation_fields,
                short_history_policy=ipo_short_history_policy,
            )
            data["Fetch_Core_Present"] = fetch_gate["core_fields_present"]
            data["Fetch_Core_Required"] = fetch_gate.get("required_core_fields", min_fetch_core_fields)
            data["Fetch_History_Required"] = fetch_gate.get("required_history_bars", min_history_bars)
            if not fetch_gate["is_valid"]:
                reason = fetch_gate["primary_reason"] or "fetch_failed"
                if reason == "short_history":
                    fetch_short_history_rejected += 1
                else:
                    fetch_rejected += 1
                scan_failed_reason_by_symbol[sym_u] = reason
                if len(rejected_preview) < 25:
                    rejected_preview.append(
                        (
                            sym_u,
                            reason,
                            fetch_gate["core_fields_present"],
                            fetch_gate.get("required_core_fields", min_fetch_core_fields),
                            data.get("History_Bars_1Y", 0),
                            fetch_gate.get("required_history_bars", min_history_bars),
                            str(data.get("Data_Source", "unknown")).lower(),
                        )
                    )
                continue

            if fetch_gate.get("soft_flags"):
                fetch_soft_flagged += 1
                data["Fetch_Soft_Flags"] = ",".join(fetch_gate["soft_flags"])
                if ipo_short_history_soft_flag in fetch_gate.get("soft_flags", []):
                    data["Short_History_Exempt"] = True
                if len(soft_preview) < 15:
                    soft_preview.append(
                        (
                            sym_u,
                            data["Fetch_Soft_Flags"],
                            fetch_gate["core_fields_present"],
                            fetch_gate.get("required_core_fields", min_fetch_core_fields),
                            data.get("History_Bars_1Y", 0),
                            fetch_gate.get("required_history_bars", min_history_bars),
                            str(data.get("Data_Source", "unknown")).lower(),
                        )
                    )
            scan_success_symbols.add(sym_u)
            data["Fetch_Valid"] = True
                
            # V3.1: Data Quality Gate
            dq = calculate_data_quality(data, zero_valuation_cap=dq_zero_valuation_cap)
            if data.get("Short_History_Exempt") and ipo_short_history_dq_penalty > 0:
                dq = round(max(0.0, dq - ipo_short_history_dq_penalty), 1)
                data["DQ_Adjustment"] = f"-{ipo_short_history_dq_penalty} short_history_penalty"
            data["Data_Quality"] = dq
            data.pop("_dq_flags", None)
            data.pop("_dq_breakdown", None)
            candidate_data.append(data)

            symbol = str(data.get("Symbol", "Unknown")).upper()
            
            # Phase 11: Framework Filtering
            if active_filters:
                passes_filters = True
                if "sales_growth_5y_min" in active_filters:
                    val = data.get("Sales_Growth_5Y%", 0)
                    if val < active_filters["sales_growth_5y_min"] * 100: # Engine uses %, Framework uses decimal
                        passes_filters = False
                if "roe_min" in active_filters:
                    val = data.get("ROE%", 0)
                    if val < active_filters["roe_min"] * 100:
                        passes_filters = False
                if "roce_min" in active_filters:
                    val = data.get("ROCE%", 0)
                    if val < active_filters["roce_min"] * 100:
                        passes_filters = False
                if "pat_growth_5y_min" in active_filters:
                    val = data.get("Median_PAT_Growth_5Y%", 0)
                    if val < active_filters["pat_growth_5y_min"] * 100:
                        passes_filters = False
                if "peg_max" in active_filters:
                    val = data.get("PEG_Ratio")
                    if val is None or val > active_filters["peg_max"]:
                        passes_filters = False
                if "pledge_pct_max" in active_filters:
                    val = data.get("Pledge_Pct", 100)
                    if val > active_filters["pledge_pct_max"]:
                        passes_filters = False
                if "promoter_pct_min" in active_filters:
                    val = data.get("Promoter_Holding%", 0)
                    if val < active_filters["promoter_pct_min"]:
                        passes_filters = False
                if "debt_equity_max" in active_filters:
                    val = data.get("Debt_Equity", 999)
                    if val > active_filters["debt_equity_max"]:
                        passes_filters = False
                if "cfo_to_pat_min" in active_filters:
                    val = data.get("CFO_PAT_Ratio", 0)
                    if val < active_filters["cfo_to_pat_min"]:
                        passes_filters = False
                if "piotroski_min" in active_filters:
                    # Framework says piotroski_score or f_score
                    val = data.get("F_Score", 0)
                    if val < active_filters["piotroski_min"]:
                        passes_filters = False
                if "market_cap_max" in active_filters:
                    val = data.get("Market_Cap_Cr", 0)
                    if val > active_filters["market_cap_max"]:
                        passes_filters = False
                
                if not passes_filters:
                    scan_failed_reason_by_symbol[symbol] = "framework_filter_reject"
                    continue

            if dq < min_dq:
                if symbol in targeted_symbols:
                    print(f"   {symbol}: Data quality {dq}% < {min_dq}%  BYPASSED (Targeted Scan)")
                    initial_pass.append(data)
                else:
                    pass
                continue

            initial_pass.append(data)

        valid_data = initial_pass

        # Deterministic fail-soft fallback for full-universe scans.
        if is_full_scan and candidate_data:
            pass_ratio = len(valid_data) / len(candidate_data)
            if pass_ratio < full_scan_min_pass_ratio:
                target_count = max(1, int(len(candidate_data) * full_scan_min_pass_ratio))
                sorted_dq = sorted((d.get("Data_Quality", 0) for d in candidate_data), reverse=True)
                target_threshold = sorted_dq[target_count - 1]
                adaptive_min_dq = max(full_scan_dq_floor, min(min_dq, target_threshold))
                if adaptive_min_dq < min_dq:
                    valid_data = [d for d in candidate_data if d.get("Data_Quality", 0) >= adaptive_min_dq]
                    effective_min_dq = adaptive_min_dq
                    print(
                        f"Adaptive DQ fallback: pass ratio {pass_ratio:.1%} below {full_scan_min_pass_ratio:.1%}. "
                        f"Threshold lowered {min_dq}% -> {adaptive_min_dq}%."
                    )

        # Bounded skip logging: enough for auditability, no flood.
        final_skipped = []
        if candidate_data:
            passed_symbols = {str(d.get("Symbol", "")).upper() for d in valid_data}
            for d in candidate_data:
                sym = str(d.get("Symbol", "Unknown")).upper()
                if sym not in passed_symbols:
                    reason = scan_failed_reason_by_symbol.get(sym, "low_data_quality")
                    final_skipped.append((sym, d.get("Data_Quality", 0), reason))

        if final_skipped:
            preview_n = 50
            for sym, dq, reason in final_skipped[:preview_n]:
                if reason == "framework_filter_reject":
                    print(f"   {sym}: Framework criteria not met (Targeted/Universe screen) - REJECTED")
                else:
                    print(f"   {sym}: Data quality {dq}% < {effective_min_dq}%  SKIPPED")
            if len(final_skipped) > preview_n:
                print(f"   ... {len(final_skipped) - preview_n} more skipped/rejected.")

        if rejected_preview:
            for sym, reason, core_count, required_core, bars, required_bars, source in rejected_preview:
                print(
                    f"   {sym}: FETCH_REJECTED ({reason}), core_fields={core_count}/{required_core}, "
                    f"history_bars={bars}/{required_bars}, source={source}"
                )
            if fetch_rejected > len(rejected_preview):
                print(f"   ... {fetch_rejected - len(rejected_preview)} more rejected by fetch gate.")
        if soft_preview:
            for sym, flags, core_count, required_core, bars, required_bars, source in soft_preview:
                print(
                    f"   {sym}: FETCH_SOFT ({flags}), core_fields={core_count}/{required_core}, "
                    f"history_bars={bars}/{required_bars}, source={source}"
                )
            if fetch_soft_flagged > len(soft_preview):
                print(f"   ... {fetch_soft_flagged - len(soft_preview)} more with soft fetch flags.")
        if failure_reason_counts:
            top_reasons = sorted(failure_reason_counts.items(), key=lambda item: item[1], reverse=True)[:8]
            reason_text = ", ".join(f"{k}={v}" for k, v in top_reasons)
            print(f"Fetch failure reasons: {reason_text}")

        print(
            f"DQ Gate Summary: fetched={len(scan_success_symbols)}, "
            f"mcap_skipped={skipped_mcap}, dq_candidates={len(candidate_data)}, "
            f"dq_passed={len(valid_data)}, fetch_failed_raw={fetch_failures_raw}, "
            f"fetch_rejected={fetch_rejected}, fetch_short_history={fetch_short_history_rejected}, "
            f"fetch_soft_flagged={fetch_soft_flagged}, "
            f"fetch_failed_total={fetch_failures_raw + fetch_rejected + fetch_short_history_rejected}, "
            f"dq_threshold={effective_min_dq}%"
        )
        if retry_attempted:
            retry_c = retry_concurrency if retry_concurrency is not None else "n/a"
            print(
                f"Retry Summary: attempted={retry_attempted}, recovered={retry_recovered}, "
                f"retry_concurrency={retry_c}"
            )

        return valid_data

    async def run_scanner():
        scan_concurrency = full_scan_base_concurrency if is_full_scan else targeted_scan_concurrency
        scan_concurrency = max(4, int(scan_concurrency))
        print(f"DataManager concurrency: {scan_concurrency}")
        async with DataManager(max_concurrency=scan_concurrency) as dm:
            return await fetch_all_data(dm)

    results = asyncio.run(run_scanner())

    # --- Phase 2: ML Ranking ---
    if results:
        print("\nApplying LightGBM Ranking Engine...")
        ranker = LightGBMRanker()
        results = ranker.rank_stocks(results)

    # Persist fetch-failure flags for full-universe hygiene.
    if is_full_scan and auto_flag_enable and universe_flags is not None:
        flag_summary = update_universe_flags(
            universe_flags,
            failed_reason_by_symbol=scan_failed_reason_by_symbol,
            successful_symbols=scan_success_symbols,
            as_of=date.today(),
            failure_threshold=auto_flag_failure_threshold,
            cooldown_days=auto_flag_cooldown_days,
            min_success_ratio=auto_flag_min_success_ratio,
            max_new_inactive=auto_flag_max_new_inactive,
            whitelist=flag_whitelist,
            reason_thresholds=auto_flag_reason_thresholds,
        )
        save_universe_flags(flags_path, universe_flags)
        guard_note = " (guarded by outage ratio)" if flag_summary["guarded_by_outage"] else ""
        print(
            "Universe flag summary: "
            f"attempted={flag_summary['attempted']}, success={flag_summary['successful']}, "
            f"failed={flag_summary['failed']}, success_ratio={flag_summary['success_ratio']:.1%}, "
            f"new_inactive={flag_summary['new_inactive']}, blocked_total={flag_summary['blocked_total']}"
            f"{guard_note} | {flags_path}"
        )
    
    # 1.5 Phase 68: Batch VectorBT Optimization
    if results:
        symbols_to_backtest = [s.get("Symbol") for s in results if s.get("Symbol")]
        if symbols_to_backtest:
            max_bt_symbols = int(getattr(config, "MAX_VECTORBT_SYMBOLS", 200))
            bt_symbols = symbols_to_backtest
            if len(symbols_to_backtest) > max_bt_symbols:
                ranked = sorted(
                    results,
                    key=lambda s: (
                        s.get("Data_Quality", 0),
                        s.get("Market_Cap_Cr", 0),
                        s.get("Symbol", ""),
                    ),
                    reverse=True,
                )
                bt_symbols = [s.get("Symbol") for s in ranked if s.get("Symbol")][:max_bt_symbols]
                print(
                    f"Running VectorBT Optimization for top {len(bt_symbols)}/{len(symbols_to_backtest)} "
                    f"stocks (capped by MAX_VECTORBT_SYMBOLS={max_bt_symbols})."
                )
            else:
                print(f"Running VectorBT Optimization for {len(bt_symbols)} valid stocks...")

            from backtest.engine import VectorBTEngine
            bt_engine = VectorBTEngine(period="5y")
            batch_bt_results = bt_engine.run_batch_momentum_backtest(bt_symbols)
            for stock in results:
                sym = stock.get("Symbol", "")
                sym_with_ns = sym if sym.endswith('.NS') or sym.endswith('.BO') else sym + '.NS'
                bt = batch_bt_results.get(sym_with_ns, batch_bt_results.get(sym, {}))
                
                stock["Backtest_CAGR"] = bt.get("cagr", 0.0)
                stock["Backtest_Win_Rate"] = bt.get("win_rate", 0.0)
                stock["Backtest_Max_DD"] = bt.get("max_drawdown", 0.0)
                stock["Backtest_Sharpe"] = bt.get("sharpe_ratio", 0.0)
            
    # 2. Phase 3: Sector Analysis
    if results:
        top_sectors = analyze_sector_rotation(results)
        
        # V6.0: Calculate sector medians for relative scoring
        sector_medians = calculate_sector_medians(results)
        print(f"\n Sector Medians (V6.0):")
        for sec, med in sorted(sector_medians.items()):
            print(f"  {sec}: ROE={med['median_roe']}%, Growth={med['median_growth']}%, PE={med['median_pe']}")
        
        # 3. Calculate Final Scores
        for stock in results:
            bonus = 0
            if stock.get("Sector") in top_sectors:
                bonus = 5 
                stock["Sector_Leader"] = True
            else:
                stock["Sector_Leader"] = False
                
            # Pass the selected mode as 'market_regime' (overriding the auto-detection for strategy purposes)
            # This is a temporary bridge until we separate Market Regime from Scoring Strategy in the function signature.
            score_data = calculate_institutional_score(stock, sector_boost=bonus, market_regime=final_mode, sector_medians=sector_medians)
            
            # Pydantic Validation
            try:
                from modules.models import ScoringResult
                score_data = ScoringResult(**score_data).model_dump()
            except Exception as e:
                import logging
                logging.error(f"ScoringResult Validation Error for {stock.get('Symbol')}: {e}")
            score = score_data["total_score"]
            stock["Score"] = score
            stock["factor_penalties"] = score_data.get("factor_penalties", [])
            stock["Data_Confidence"] = score_data.get("data_confidence", 0)
            stock["Conviction_Score"] = score_data.get("conviction_score", 0)
            stock["Conviction_Boost"] = score_data.get("conviction_boost", 0)
            stock["Institutional_Interest"] = score_data.get("institutional_interest", False)
            stock["Super_Investors"] = score_data.get("super_investors", "")
            
            # Phase 4 Update: Rating with V6 Valuation Gate
            vg = stock.get("Value_Gap%", 0)
            if score >= 80 and vg >= -10: stock["Rating"] = "Strong Buy (Elite)"
            elif score >= 65: stock["Rating"] = "Buy"
            elif score >= 50: stock["Rating"] = "Hold"
            else: stock["Rating"] = "Avoid"
            
            # --- Phase 88: Hybrid Scoring (ML) ---
            try:
                from modules.hybrid_scoring import predict_and_explain
                factors = {
                    'score': score,
                    'sales_cagr_5y': stock.get("Sales_Growth_5Y%", 0),
                    'avg_roe_5y': stock.get("Avg_ROE_5Y%", 0),
                    'pe_ratio': stock.get("PE_Ratio", 0),
                    'debt_equity': stock.get("Debt_Equity", 0),
                    'cfo_pat_ratio': stock.get("CFO_PAT_Ratio", 0),
                    'market_cap_cr': stock.get("Market_Cap_Cr", 0)
                }
                ml_res = predict_and_explain(factors)
                stock["ML_Predicted_Return"] = ml_res.get("ml_prediction")
                
                # Convert SHAP dict to JSON string for easier SQLite storage
                import json
                stock["SHAP_Breakdown"] = json.dumps(ml_res.get("shap_values", {}))
            except Exception as e:
                # Silent fail if ML model not ready
                stock["ML_Predicted_Return"] = None
                stock["SHAP_Breakdown"] = "{}"
            
            # Trade Setup
            calculate_trade_setup(stock)
            
    # V3.1: Score Distribution Validation
    validate_score_distribution(results)
    
    # 4. Save
    print(f"\nAnalysis Complete. Found {len(results)} stocks. (Skipped {skipped_mcap} below MCap gate)")
    df = pd.DataFrame(results)
    
    if not df.empty:
        pre_save_count = len(df)
        if "Fetch_Valid" in df.columns:
            df = df[df["Fetch_Valid"] == True]
        if "Price" in df.columns:
            df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
            df = df[np.isfinite(df["Price"]) & (df["Price"] > 0)]
        if "History_Bars_1Y" in df.columns:
            df["History_Bars_1Y"] = pd.to_numeric(df["History_Bars_1Y"], errors="coerce").fillna(0).astype(int)
            if "Fetch_History_Required" in df.columns:
                df["Fetch_History_Required"] = pd.to_numeric(df["Fetch_History_Required"], errors="coerce").fillna(min_history_bars).astype(int)
                df = df[df["History_Bars_1Y"] >= df["Fetch_History_Required"]]
            else:
                df = df[df["History_Bars_1Y"] >= min_history_bars]
        if "Fetch_Core_Present" in df.columns:
            df["Fetch_Core_Present"] = pd.to_numeric(df["Fetch_Core_Present"], errors="coerce").fillna(0).astype(int)
            if "Fetch_Core_Required" in df.columns:
                df["Fetch_Core_Required"] = pd.to_numeric(df["Fetch_Core_Required"], errors="coerce").fillna(min_fetch_core_fields).astype(int)
                df = df[df["Fetch_Core_Present"] >= df["Fetch_Core_Required"]]
            else:
                df = df[df["Fetch_Core_Present"] >= min_fetch_core_fields]
        if hard_block_zero_valuation_fields and {"Market_Cap_Cr", "PE_Ratio"}.issubset(df.columns):
            mcap_series = pd.to_numeric(df["Market_Cap_Cr"], errors="coerce").fillna(0)
            pe_series = pd.to_numeric(df["PE_Ratio"], errors="coerce").fillna(0)
            df = df[(mcap_series != 0) | (pe_series != 0)]
        dropped_on_save = pre_save_count - len(df)
        if dropped_on_save > 0:
            print(f"Pre-save fetch-validity filter dropped {dropped_on_save} stocks. Remaining: {len(df)}")

        results = df.to_dict(orient="records")

    if not df.empty:
        # Save to CSV
        df.to_csv("screener_results.csv", index=False)
        print("Saved to csv.")
        
        # Save to SQLite
        # Save to SQLite
        try:
            import database
            database.save_multibaggers(df)
        except Exception as e:
            import logging
            from modules.exceptions import DatabaseConcurrencyError
            logging.error(f"Database error while saving multibaggers: {e}", exc_info=True)

        # Phase 40 & 41: Institutional Analysis Pipeline
        try:
            print("\n" + "="*50)
            print("  INSTITUTIONAL ANALYSIS PIPELINE")
            print("="*50)
            
            import logging
            
            # 1. Backtest Picks (Reads from screener_results.csv)
            try:
                import backtest_picks
                backtest_picks.backtest_picks()
            except Exception as e: 
                logging.error(f"Backtest Picks Error: {e}", exc_info=True)
            
            # 2. Alpha Attribution (Reads from stocks.db)
            try:
                import alpha_attribution
                alpha_attribution.run_attribution()
            except Exception as e: 
                logging.error(f"Alpha Attribution Error: {e}", exc_info=True)
            
            # 3. Liquidity Stress Test (Reads from stocks.db)
            try:
                import liquidity_simulator
                liquidity_simulator.run_liquidity_check()
            except Exception as e: 
                logging.error(f"Liquidity Check Error: {e}", exc_info=True)
            
            # 4. Walk-Forward Validation (Reads from stocks.db)
            try:
                import backtest_engine
                backtest_engine.run_backtest()
            except Exception as e: 
                logging.error(f"Backtest Engine Error: {e}", exc_info=True)
            
        except Exception as e:
            import logging
            logging.error(f"Error in Pipeline: {e}", exc_info=True)
    else:
        print("No stocks found matching criteria.")

    # 5. Audit Logging (Phase 2.2)
    try:
        logger = ScanLogger()
        
        # Snapshot Config (Mirroring logic in calculate_institutional_score)
        # In a future refactor, these should be loaded from a config.py
        config_snapshot = {
            "market_regime": market_regime,
            "weights_model": f"v2.2_{final_mode}",
            "risk_settings": {
                "max_sector_exposure": config.MAX_SECTOR_EXPOSURE, 
                "hard_kill_switch_vix": config.HARD_KILL_SWITCH_VIX
            }
        }
        
        # Summary Stats
        elite_count = len([s for s in results if s.get("Score", 0) >= 80])
        top_pick = max(results, key=lambda x: x.get("Score", 0))["Symbol"] if results else "None"
        
        results_summary = {
            "total_scanned": len(results),
            "elite_count": elite_count,
            "top_pick": top_pick,
            "market_regime": market_regime,
            "strategy_mode": final_mode
        }
        
        log_path = logger.log_scan(len(TICKERS), results_summary, config_snapshot)
        print(f"\n[AUDIT] Scan Logged: {log_path}")
        
    except Exception as e:
        print(f"Logging Error: {e}")

if __name__ == "__main__":
    main()
