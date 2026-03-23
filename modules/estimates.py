"""
Earnings Estimate Tracking Module
Forward-looking estimate momentum tracking.
Uses Alpha Vantage earnings calendar + self-computed CAGR estimates.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional


def _safe_float(val, default=0.0):
    """Safe float conversion."""
    if val is None:
        return default
    try:
        result = float(val)
        if result != result:  # NaN check
            return default
        return result
    except (ValueError, TypeError):
        return default


def compute_own_estimate(info: dict, financials_data: dict = None) -> Dict:
    """
    Compute own EPS estimate as fallback.
    Formula: Revenue 5Y CAGR  (1 + industry_growth_premium)

    Args:
        info: Stock info dict from yfinance
        financials_data: Optional historical financial data

    Returns:
        Dict with estimated EPS for current and next FY
    """
    eps_ttm = _safe_float(info.get("trailingEps", 0))
    earnings_growth = _safe_float(info.get("earningsGrowth", 0))
    revenue_growth = _safe_float(info.get("revenueGrowth", 0))

    # Use earnings growth if available, else revenue growth as proxy
    growth_rate = earnings_growth if earnings_growth != 0 else revenue_growth

    # Industry growth premium (conservative 2%)
    industry_premium = 0.02

    # Compute forward estimates
    if eps_ttm > 0 and growth_rate != 0:
        effective_growth = growth_rate + industry_premium
        current_fy_estimate = round(eps_ttm * (1 + effective_growth), 2)
        next_fy_estimate = round(current_fy_estimate * (1 + effective_growth), 2)
    elif eps_ttm > 0:
        # No growth data: assume 10% growth (conservative)
        current_fy_estimate = round(eps_ttm * 1.10, 2)
        next_fy_estimate = round(eps_ttm * 1.21, 2)
    else:
        current_fy_estimate = 0
        next_fy_estimate = 0

    return {
        "current_fy_eps_estimate": current_fy_estimate,
        "next_fy_eps_estimate": next_fy_estimate,
        "growth_rate_used": round(growth_rate * 100, 2) if growth_rate else 0,
        "source": "self_computed_cagr",
        "method": "Revenue/Earnings CAGR  (1 + industry_premium)",
    }


def analyze_earnings_surprises(quarterly_earnings: List[Dict]) -> Dict:
    """
    Analyze earnings beat/miss streak from Alpha Vantage quarterly earnings.

    Args:
        quarterly_earnings: List of quarterly earnings dicts with
            estimated_eps, reported_eps, surprise_pct

    Returns:
        Dict with beat_count, miss_count, streak, streak_type
    """
    if not quarterly_earnings:
        return {
            "beat_count": 0,
            "miss_count": 0,
            "streak": 0,
            "streak_type": "NONE",
            "history": [],
        }

    history = []
    beat_count = 0
    miss_count = 0

    for q in quarterly_earnings[:8]:  # Last 8 quarters
        estimated = _safe_float(q.get("estimated_eps"))
        reported = _safe_float(q.get("reported_eps"))
        surprise_pct = _safe_float(q.get("surprise_pct"))

        if estimated == 0 and reported == 0:
            continue

        if reported > estimated and estimated > 0:
            result = "BEAT"
            beat_count += 1
        elif reported < estimated and estimated > 0:
            result = "MISS"
            miss_count += 1
        else:
            result = "INLINE"

        history.append({
            "date": q.get("date", ""),
            "estimated_eps": estimated,
            "reported_eps": reported,
            "surprise_pct": surprise_pct,
            "result": result,
        })

    # Calculate streak (from most recent)
    streak = 0
    streak_type = "NONE"
    if history:
        first_result = history[0]["result"]
        if first_result in ("BEAT", "MISS"):
            streak_type = first_result
            for h in history:
                if h["result"] == first_result:
                    streak += 1
                else:
                    break

    return {
        "beat_count": beat_count,
        "miss_count": miss_count,
        "streak": streak,
        "streak_type": streak_type,
        "history": history[:4],  # Return last 4 for display
    }


def analyze_estimate_revisions(quarterly_earnings: List[Dict]) -> Dict:
    """
    Analyze estimate revision trends (are analysts upgrading or downgrading?).

    Uses the surprise data as a proxy: if actuals consistently beat estimates,
    it implies estimates were being revised up (or were conservative).

    Args:
        quarterly_earnings: List of quarterly earnings from AV

    Returns:
        Dict with revision_direction, consecutive count, scoring impact
    """
    if not quarterly_earnings or len(quarterly_earnings) < 2:
        return {
            "revision_direction": "STABLE",
            "consecutive_upgrades": 0,
            "consecutive_downgrades": 0,
        }

    # Track estimate changes quarter over quarter
    # If estimated EPS is rising QoQ, estimates are being upgraded
    estimates = []
    for q in quarterly_earnings[:6]:
        est = _safe_float(q.get("estimated_eps"))
        if est > 0:
            estimates.append(est)

    if len(estimates) < 2:
        return {
            "revision_direction": "STABLE",
            "consecutive_upgrades": 0,
            "consecutive_downgrades": 0,
        }

    # Count consecutive upgrades/downgrades (latest first)
    consecutive_upgrades = 0
    consecutive_downgrades = 0

    for i in range(len(estimates) - 1):
        if estimates[i] > estimates[i + 1]:
            consecutive_upgrades += 1
        elif estimates[i] < estimates[i + 1]:
            consecutive_downgrades += 1
        else:
            break

    if consecutive_upgrades >= 2:
        direction = "UPGRADING"
    elif consecutive_downgrades >= 2:
        direction = "DOWNGRADING"
    else:
        direction = "STABLE"

    return {
        "revision_direction": direction,
        "consecutive_upgrades": consecutive_upgrades,
        "consecutive_downgrades": consecutive_downgrades,
    }


def analyze_estimate_momentum(earnings_data: Dict) -> Dict:
    """
    Master orchestrator: determine scoring impact from estimate data.

    Returns:
        Dict with:
          - momentum_signal: str ("STRONG_UP", "UP", "STABLE", "DOWN", "STRONG_DOWN")
          - score_adjustment: int
          - is_disqualified: bool (D16)
          - score_cap: int or None
          - display_text: str
    """
    quarterly = earnings_data.get("quarterly", [])

    surprises = analyze_earnings_surprises(quarterly)
    revisions = analyze_estimate_revisions(quarterly)

    score_adj = 0
    is_disqualified = False
    score_cap = None
    momentum = "STABLE"
    display_parts = []

    # Rule 1: 3 consecutive estimate upgrades = +5 ("Estimate Momentum")
    if revisions["consecutive_upgrades"] >= 3:
        score_adj += 5
        momentum = "STRONG_UP"
        display_parts.append(
            f" ESTIMATE MOMENTUM: Upgrades {revisions['consecutive_upgrades']} quarters running"
        )
    elif revisions["consecutive_upgrades"] >= 2:
        score_adj += 2
        momentum = "UP"
        display_parts.append(f" Estimates rising {revisions['consecutive_upgrades']}Q")

    # Rule 2: 3 consecutive estimate downgrades = D16 disqualifier
    if revisions["consecutive_downgrades"] >= 3:
        is_disqualified = True
        score_adj = -5
        momentum = "STRONG_DOWN"
        display_parts.append(
            f" ESTIMATE COLLAPSE: Downgrades {revisions['consecutive_downgrades']} quarters running"
        )
    elif revisions["consecutive_downgrades"] >= 2:
        score_adj -= 3
        momentum = "DOWN"
        display_parts.append(
            f" Estimates falling {revisions['consecutive_downgrades']}Q"
        )

    # Rule 3: 4Q earnings beat streak = +3
    if surprises["streak"] >= 4 and surprises["streak_type"] == "BEAT":
        score_adj += 3
        display_parts.append(
            f" {surprises['streak']}Q consecutive earnings beat"
        )
    elif surprises["streak"] >= 2 and surprises["streak_type"] == "BEAT":
        score_adj += 1
        display_parts.append(f" {surprises['streak']}Q beat streak")

    # Rule 4: 4Q earnings miss streak = cap at 70
    if surprises["streak"] >= 4 and surprises["streak_type"] == "MISS":
        score_cap = 70
        score_adj -= 3
        display_parts.append(
            f" {surprises['streak']}Q consecutive earnings miss  score capped at 70"
        )
    elif surprises["streak"] >= 2 and surprises["streak_type"] == "MISS":
        score_adj -= 2
        display_parts.append(f" {surprises['streak']}Q miss streak")

    # Build surprise history display
    surprise_display = []
    for h in surprises["history"][:4]:
        q_label = h["date"][:7] if h["date"] else "?"
        pct = h["surprise_pct"]
        if h["result"] == "BEAT":
            surprise_display.append(f"{q_label}: Beat by {abs(pct):.0f}%")
        elif h["result"] == "MISS":
            surprise_display.append(f"{q_label}: Miss {abs(pct):.0f}%")
        else:
            surprise_display.append(f"{q_label}: Inline")

    return {
        "momentum_signal": momentum,
        "score_adjustment": score_adj,
        "is_disqualified": is_disqualified,
        "score_cap": score_cap,
        "display_text": " | ".join(display_parts) if display_parts else "No estimate data",
        "surprise_history": " | ".join(surprise_display) if surprise_display else "",
        "revisions": revisions,
        "surprises": {
            "beat_count": surprises["beat_count"],
            "miss_count": surprises["miss_count"],
            "streak": surprises["streak"],
            "streak_type": surprises["streak_type"],
        },
    }


def get_estimate_data(
    symbol: str,
    info: Optional[dict] = None,
    allow_alpha_vantage: bool = True,
) -> Dict:
    """
    Full estimate pipeline: fetch data + analyze momentum.

    1. Try Alpha Vantage earnings calendar
    2. Fallback: compute own estimates from fundamentals
    3. Return combined analysis

    Args:
        symbol: Stock symbol (e.g., "TCS.NS")

    Returns:
        Complete estimate tracking dict for API/dashboard
    """
    result = {
        "symbol": symbol,
        "estimates": None,
        "momentum": None,
        "own_estimate": None,
        "source": "none",
        "error": None,
    }

    # --- V7.0: INSTITUTIONAL OVERRIDE LAYER ---
    # Check for manual analyst consensus seeds
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        consensus_path = os.path.join(current_dir, "analyst_consensus.json")
        if os.path.exists(consensus_path):
            with open(consensus_path, "r") as f:
                seeds = json.load(f)
                if symbol in seeds:
                    seed = seeds[symbol]
                    result["source"] = "manual_seed"
                    result["estimates"] = seed
                    result["momentum"] = {
                        "momentum_signal": "STRONG_UP" if seed.get("upside_potential_pct", 0) > 20 else "UP",
                        "score_adjustment": 5 if seed.get("consensus") == "Strong Buy" else 2,
                        "is_disqualified": False,
                        "score_cap": None,
                        "display_text": f" INSTITUTIONAL CONSENSUS: {seed['consensus']} ({seed['analyst_count']} analysts) | Target: {seed['target_high']} (+{seed.get('upside_potential_pct')}% upside)",
                        "surprise_history": f"Horizon: {seed.get('time_horizon_months')}m",
                        "revisions": {"revision_direction": "UPGRADING", "consecutive_upgrades": 3, "consecutive_downgrades": 0},
                        "surprises": {"beat_count": 0, "miss_count": 0, "streak": 0, "streak_type": "NONE"},
                        "fundamentals_override": seed.get("fundamentals_override")
                    }
                    return result
    except Exception as e:
        print(f"   Consensus seed load error: {e}")

    # 1. Try Alpha Vantage earnings (optional for full-scan stability)
    av_data = None
    if allow_alpha_vantage:
        try:
            from modules.alpha_vantage import AlphaVantageProvider, get_remaining_budget
            if get_remaining_budget() >= 1:
                av = AlphaVantageProvider()
                av_data = av.get_earnings_calendar(symbol)
                if av_data:
                    result["source"] = "alpha_vantage"
        except Exception as e:
            print(f"   AV earnings fetch failed for {symbol}: {e}")

    # 2. Process AV data if available
    if av_data:
        result["estimates"] = av_data
        result["momentum"] = analyze_estimate_momentum(av_data)
    else:
        # No AV data: compute own estimate as fallback
        try:
            local_info = info
            if local_info is None:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                local_info = ticker.info or {}
            own_est = compute_own_estimate(local_info)
            result["own_estimate"] = own_est
            result["source"] = "self_computed"

            # Create a minimal momentum analysis (no surprise data)
            result["momentum"] = {
                "momentum_signal": "STABLE",
                "score_adjustment": 0,
                "is_disqualified": False,
                "score_cap": None,
                "display_text": f"Self-computed estimate: {own_est['current_fy_eps_estimate']} (FY curr) "
                                f" {own_est['next_fy_eps_estimate']} (FY next)",
                "surprise_history": "",
                "revisions": {
                    "revision_direction": "STABLE",
                    "consecutive_upgrades": 0,
                    "consecutive_downgrades": 0,
                },
                "surprises": {
                    "beat_count": 0,
                    "miss_count": 0,
                    "streak": 0,
                    "streak_type": "NONE",
                },
            }
        except Exception as e:
            result["error"] = str(e)
            result["momentum"] = {
                "momentum_signal": "STABLE",
                "score_adjustment": 0,
                "is_disqualified": False,
                "score_cap": None,
                "display_text": "Estimate data unavailable",
                "surprise_history": "",
                "revisions": {"revision_direction": "STABLE", "consecutive_upgrades": 0, "consecutive_downgrades": 0},
                "surprises": {"beat_count": 0, "miss_count": 0, "streak": 0, "streak_type": "NONE"},
            }

    return result
