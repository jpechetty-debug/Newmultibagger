import numpy as np
import config
from research.conviction_engine import calculate_conviction_score
from modules.promoter_intel import calculate_promoter_score
from modules.estimates import get_estimate_data

def normalize_metric(value, min_val, max_val, invert=False):
    """
    Normalizes a metric to a 0-100 scale using a Sigmoid function.
    Replaces binary step cliffs with a smooth continuous gradient.
    """
    if value is None or not np.isfinite(value): return 0
    
    mid = (min_val + max_val) / 2.0
    span = float(max_val - min_val)
    if span == 0: span = 1e-5
    
    # Scale so min_val is approx at x=-3 (4.7%) and max_val at x=+3 (95%)
    x_scaled = (value - mid) / (span / 6.0)
    
    # Cap exponent to avoid overflow warnings
    x_scaled = max(-100, min(100, x_scaled))
    
    sigmoid_val = 1.0 / (1.0 + np.exp(-x_scaled))
    
    if invert:
        return (1.0 - sigmoid_val) * 100.0
    else:
        return sigmoid_val * 100.0

def calculate_sector_medians(results):
    """Compute median ROE, Sales Growth, PE per sector for relative scoring."""
    sector_data = {}
    for stock in results:
        sector = stock.get("Sector", "Unknown")
        if sector == "Unknown":
            continue
        if sector not in sector_data:
            sector_data[sector] = {"roe": [], "growth": [], "pe": []}
        roe = stock.get("Avg_ROE_5Y%", 0) or stock.get("ROE%", 0) or 0
        growth = stock.get("Sales_Growth_5Y%", 0) or stock.get("Sales_Growth_TTM%", 0) or 0
        pe = stock.get("PE_Ratio", 0) or 0
        if roe != 0:
            sector_data[sector]["roe"].append(roe)
        if growth != 0:
            sector_data[sector]["growth"].append(growth)
        if pe > 0:
            sector_data[sector]["pe"].append(pe)
    
    medians = {}
    for sector, vals in sector_data.items():
        medians[sector] = {
            "median_roe": round(float(np.median(vals["roe"])), 1) if vals["roe"] else 15,
            "median_growth": round(float(np.median(vals["growth"])), 1) if vals["growth"] else 10,
            "median_pe": round(float(np.median(vals["pe"])), 1) if vals["pe"] else 20,
        }
    return medians

def calculate_institutional_score(data, sector_boost=0, market_regime="Neutral", sector_medians=None):
    """
    Calculates a 'Composite Institutional Score' out of 100.
    Phase 23: Dynamic Factor Weights based on Market Regime.
    """
    mode = market_regime.lower() if market_regime else "balanced"
    
    if mode not in config.SCORING_WEIGHTS:
        mode = "balanced"
        
    weights = config.SCORING_WEIGHTS[mode]
    scoring_strategy = mode.capitalize()
    
    # Unpack
    w_sales = weights["w_sales"]
    w_roe = weights["w_roe"]
    w_cfo = weights["w_cfo"]
    w_val = weights["w_val"]
    w_eps = weights["w_eps"]
    w_fscore = weights["w_fscore"]
    w_de = weights["w_de"]
    w_mom = weights["w_mom"]
    
    # --- V6.0: METRIC CALCULATION (Pre-Scoring) ---
    # 1. Sales Growth
    # (used in V6.0 sector relative scoring)
    sg_val = data.get("Sales_Growth_5Y%", 0) or data.get("Sales_Growth_TTM%", 0) or 0
    score_sales = normalize_metric(data.get("Sales_Growth_5Y%", 0), 5, 25)

    # 2. ROE (with cascading fallback + V3.1 confidence penalty)
    roe_5y = data.get("Avg_ROE_5Y%", 0)
    roe_current = data.get("ROE%", 0)
    profit_margin = data.get("Profit_Margin%", 0)
    if roe_5y > 0:
        roe_val = roe_5y
        best_roe = roe_5y
        roe_confidence = 1.0   # Full confidence: 5Y average
    elif roe_current > 0:
        roe_val = roe_current
        best_roe = roe_current
        roe_confidence = 0.85  # 15% penalty: single-year only
    elif profit_margin > 0:
        roe_val = profit_margin
        best_roe = profit_margin
        roe_confidence = 0.70  # 30% penalty: proxy metric
    else:
        roe_val = 0
        best_roe = 0
        roe_confidence = 0.0
    
    score_roe = normalize_metric(roe_val, 10, 30) * roe_confidence
    
    # 3. CFO / PAT
    score_cfo = normalize_metric(data.get("CFO_PAT_Ratio", 0), 0.5, 1.5)
    
    # 4. Valuation
    pe = data.get("PE_Ratio")
    peg = data.get("PEG_Ratio")
    score_pe = normalize_metric(pe, 15, 60, invert=True) if (pe is not None and pe > 0) else 0
    score_peg = normalize_metric(peg, 0.8, 2.5, invert=True) if (peg is not None and peg > 0) else 0
    # Smart valuation: use what's available
    if score_pe > 0 and score_peg > 0:
        score_val = (score_pe * 0.5) + (score_peg * 0.5)
    elif score_pe > 0:
        score_val = score_pe  # PE-only when PEG is missing
    else:
        score_val = score_peg  # PEG-only (unlikely)
    
    # 5. EPS Growth
    score_eps = normalize_metric(data.get("EPS_Growth%", 0), 5, 30)
    
    # 6. F-Score (0-9)
    score_fscore = (data.get("F_Score", 0) / 9) * 100
    
    # 7. Debt / Equity
    if "Bank" in data.get("Sector", "") or "Financial" in data.get("Sector", ""):
        score_de = 80 
    else:
        score_de = normalize_metric(data.get("Debt_Equity", 0), 0, 1.0, invert=True)
        
    # 8. Momentum
    down_from_high = data.get("Down_From_52W_High%", 0)
    price = data.get("Price", 0) or 0
    score_mom_tech = normalize_metric(down_from_high, 0, 40, invert=True) if price > 0 else 0
    
    rs_rating = data.get("RS_Rating", 0)
    score_rs = 0
    if rs_rating > 1.2: score_rs = 100
    elif rs_rating > 1.0: score_rs = 75
    elif rs_rating > 0.8: score_rs = 50
    else: score_rs = 25
    
    score_mom_combined = (score_mom_tech * 0.5) + (score_rs * 0.5)

    # --- DYNAMIC WEIGHT REDISTRIBUTION ---
    # Build factor list with scores and weights
    factors = [
        ("sales", score_sales, w_sales),
        ("roe", score_roe, w_roe),
        ("cfo", score_cfo, w_cfo),
        ("val", score_val, w_val),
        ("eps", score_eps, w_eps),
        ("fscore", score_fscore, w_fscore),
        ("de", score_de, w_de),
        ("mom", score_mom_combined, w_mom),
    ]
    
    # Identify which factors have actual data
    # FIX: Check if the source DATA existed, not just if score > 0. 
    # Otherwise, bad data (score 0) gets excluded and weight is redistributed!
    available = []
    
    # 1. Sales
    if data.get("Sales_Growth_5Y%", 0) != 0 or data.get("Sales_Growth_TTM%", 0) != 0:
        available.append(("sales", score_sales, w_sales))
    # 2. ROE (roe_val calculated above)
    if roe_val != 0:
        available.append(("roe", score_roe, w_roe))
    # 3. CFO
    if data.get("CFO_PAT_Ratio", 0) != 0:
        available.append(("cfo", score_cfo, w_cfo))
    # 4. Valuation (PE or PEG)
    if (pe is not None and pe > 0) or (peg is not None and peg > 0):
        available.append(("val", score_val, w_val))
    # 5. EPS
    if data.get("EPS_Growth%", 0) != 0:
        available.append(("eps", score_eps, w_eps))
    # 6. F-Score (Always exists 0-9)
    available.append(("fscore", score_fscore, w_fscore))
    # 7. Debt/Equity (Always exists, default 0 is valid)
    available.append(("de", score_de, w_de))
    # 8. Momentum (Always exists)
    available.append(("mom", score_mom_combined, w_mom))
    
    # V3.1: Data Confidence  fraction of factors with real data
    # (Denominator is 8 total factors)
    data_confidence = round((len(available) / 8) * 100, 1)
    
    if available:
        # Redistribute total weight (1.0) proportionally among available factors
        total_available_weight = sum(w for _, _, w in available)
        if total_available_weight > 0:
            scale = 1.0 / total_available_weight
        else:
            scale = 1.0
        
        base_score = sum(score * weight * scale for _, score, weight in available)
    else:
        base_score = 0
    
    # --- FIX A & Phase 4: DATA CONFIDENCE PENALTY (Continuous Decay) ---
    # Prevent weight redistribution from inflating sparse-data stocks without hard cliffs
    factor_count = len(available)
    if factor_count < 6:
        # Smooth decay multiplier from 1.0 (at 6 factors) down to 0.1 (at 0)
        data_multiplier = max(0.1, min(1.0, (factor_count / 6.0) ** 1.5))
        base_score *= data_multiplier
    
    # --- V7.0: INSTITUTIONAL ANALYST ADJUSTMENT ---
    # Apply adjustment from manual seeds or Alpha Vantage momentum
    est_adj = data.get("Estimate_Score_Adj", 0)
    base_score += est_adj
    
    # --- V6.0 UPGRADE 1: SECTOR-RELATIVE BONUS/PENALTY ---
    stock_sector = data.get("Sector", "Unknown")
    if sector_medians and stock_sector in sector_medians:
        sm = sector_medians[stock_sector]
        sector_rel_bonus = 0
        # ROE vs Sector Median
        if best_roe > sm["median_roe"] * 1.2:
            sector_rel_bonus += 3  # Sector leader in profitability
        elif best_roe > 0 and best_roe < sm["median_roe"] * 0.5:
            sector_rel_bonus -= 5  # Sector laggard
        # Growth vs Sector Median
        if sg_val > sm["median_growth"] * 1.2:
            sector_rel_bonus += 3  # Sector leader in growth
        elif sg_val > 0 and sg_val < sm["median_growth"] * 0.5:
            sector_rel_bonus -= 5  # Sector laggard
        # Apply (capped)
        sector_rel_bonus = max(-10, min(6, sector_rel_bonus))
        base_score += sector_rel_bonus
    
    # --- V3.1: BONUS SYSTEM (Capped at MAX_BONUS to prevent score inflation) ---
    MAX_BONUS = 15
    total_bonus = 0
    
    # Phase 2: Earnings Inflection Bonus (Graduated 0-5 Score)
    inflection_score = data.get("Earnings_Inflection_Score", 0)
    if inflection_score >= 4:
        total_bonus += 8  # Strong acceleration across revenue, earnings, and margins
    elif inflection_score >= 3:
        total_bonus += 5  # Good acceleration
    elif inflection_score >= 2:
        total_bonus += 3  # Moderate acceleration
    elif data.get("Earnings_Accel", False):
        total_bonus += 2  # Basic acceleration fallback

    # Phase 3: Sector Bonus
    total_bonus += sector_boost
    
    # Phase 4: Value Gap Bonus (Margin of Safety)
    value_gap = data.get("Value_Gap%", 0)
    if value_gap > 50:
        total_bonus += 10
    elif value_gap > 20:
        total_bonus += 5
        
    # Phase 5: Financial Fortress Bonus (F-Score 8 or 9)
    if data.get("F_Score", 0) >= 8:
        total_bonus += 5
        
    # Phase 6: Technical Trend Bonus
    if data.get("Technical_Signal") == "Bullish":
        total_bonus += 5
        
    # Phase 7: Analyst Consensus Bonus
    rating = data.get("Analyst_Rating", "").lower()
    upside = data.get("Analyst_Upside%", 0)
    
    if "strong buy" in rating:
        total_bonus += 5
    elif "buy" in rating:
        total_bonus += 2
        
    if upside > 20: 
        total_bonus += 5
        
    # Phase 8: Institutional Sponsorship Bonus
    inst_hold = data.get("Inst_Holding%", 0)
    prom_hold = data.get("Promoter_Holding%", 0)
    
    if inst_hold > 20:
        total_bonus += 5
    elif inst_hold > 10:
        total_bonus += 2
        
    if prom_hold > 60:
        total_bonus += 3
        
    # Phase 9: Volatility Bonus (only the positive part)
    atr = data.get("ATR", 0) or 0
    price = data.get("Price", 1) or 1
    if price > 0:
        atr_pct = atr / price
        if atr_pct < 0.03: # Low Volatility (Stable)
            total_bonus += 2

    # PHASE 43: ALPHA FACTOR TUNING (VALUE GEMS)
    # 1. Deep Value + High Quality (Coal India Case)
    if pe is not None and 0 < pe < 12 and data.get("Avg_ROE_5Y%", 0) > 25:
        total_bonus += 7
        
    # 2. Statistically Cheapest Gem (PFC / REC Case)
    if pe is not None and 0 < pe < 7 and data.get("Avg_ROE_5Y%", 0) > 15:
        total_bonus += 7
        
    # 3. Utility Debt Shield (Power Grid Case)
    sector = data.get("Sector", "")
    if "Utility" in sector or "Energy" in sector or "Power" in sector:
        if data.get("Debt_Equity", 0) > 1.0 and data.get("F_Score", 0) >= 6:
            total_bonus += 5

    # --- APPLY CAPPED BONUS ---
    capped_bonus = min(total_bonus, MAX_BONUS)
    base_score += capped_bonus

    # --- PENALTY SYSTEM (Uncapped  bad stocks must be punished) ---
    total_penalty = 0
    factor_audit = []
    
    # Volatility Penalties
    if price > 0:
        atr_pct = atr / price
        if atr_pct > 0.07: # High Volatility (Risky)
            total_penalty += 2
            factor_audit.append({"name": "High Volatility", "value": -2})
        if atr_pct > 0.10: # Extremely Volatile
            total_penalty += 5
            factor_audit.append({"name": "Extreme Volatility", "value": -5})

    # P1: Declining Revenue
    sales_5y = data.get("Sales_Growth_5Y%", 0)
    sales_ttm = data.get("Sales_Growth_TTM%", 0)
    if sales_5y < 0 and sales_ttm < 0:
        total_penalty += 5  # Both long-term and short-term revenue declining
        factor_audit.append({"name": "Declining Revenue (Long & Short)", "value": -5})
    elif sales_5y < 0 or sales_ttm < 0:
        total_penalty += 3  # One of them declining
        factor_audit.append({"name": "Declining Revenue (Partial)", "value": -3})

    # P2: Extreme Overvaluation
    if pe is not None and pe > 80:
        total_penalty += 5
        factor_audit.append({"name": "Extreme Overvaluation", "value": -5})
    elif pe is not None and pe > 60:
        total_penalty += 3
        factor_audit.append({"name": "High Overvaluation", "value": -3})

    # P3: Low Promoter Holding (Governance Risk)
    if prom_hold > 0 and prom_hold < 20:
        total_penalty += 5
        factor_audit.append({"name": "Low Promoter Holding (<20%)", "value": -5})
    elif prom_hold > 0 and prom_hold < 30:
        total_penalty += 2
        factor_audit.append({"name": "Low Promoter Holding (<30%)", "value": -2})

    base_score -= total_penalty 
            
    # --- PHASE 10: RESEARCH LAYER (CLONING + CONVICTION) ---
    stock_data_for_conviction = {
        "symbol": data.get("Symbol", ""),
        "sales_growth": data.get("Sales_Growth_5Y%", 0),
        "profit_growth": data.get("EPS_Growth%", 0), # Proxy
        "roce": data.get("Avg_ROE_5Y%", 0), # Proxy
        "debt_to_equity": data.get("Debt_Equity", 0),
        "promoter_holding": data.get("Promoter_Holding%", 0),
        "pledge": 0 # Not currently in data but engine handles 0
    }
    
    conviction = calculate_conviction_score(stock_data_for_conviction)
    
    # 1. Add Institutional Boost to Base Score
    if conviction['institutional_interest']:
        base_score += 10 # Direct boost for super investor interest

    # --- V3.1 & Phase 4: DISQUALIFIER RULES (Continuous Score Ceilings) ---
    score_ceiling = 100.0
    disqualifiers = []
    
    # Helper for smooth ceiling splines to prevent step-cliffs
    def apply_spline_cap(val, full_score_val, max_penalty_val, min_cap, name):
        nonlocal score_ceiling, disqualifiers
        if val is None or not np.isfinite(val): return
        
        cap = 100.0
        if full_score_val > max_penalty_val:
            if val <= max_penalty_val: 
                cap = min_cap
            elif val < full_score_val:
                ratio = (full_score_val - val) / float(full_score_val - max_penalty_val)
                cap = 100.0 - (ratio ** 1.5) * (100.0 - min_cap)
        else:
            if val >= max_penalty_val: 
                cap = min_cap
            elif val > full_score_val:
                ratio = (val - full_score_val) / float(max_penalty_val - full_score_val)
                cap = 100.0 - (ratio ** 1.5) * (100.0 - min_cap)
                
        if cap < 96:
            score_ceiling = min(score_ceiling, cap)
            disqualifiers.append(f"{name} ({val:.1f})")

    # D1 & D10: ROE Spline (Good: >15%, Bad: <0%, Cap: 60)
    roe_5y = data.get("Avg_ROE_5Y%", 0)
    roe_curr = data.get("ROE%", 0)
    best_roe = roe_5y if roe_5y != 0 else roe_curr
    apply_spline_cap(best_roe, 15.0, 0.0, 60, "ROE Decay Spline")
    if best_roe < 0:
        apply_spline_cap(best_roe, 0.0, -15.0, 40, "Value Destruction Spline")
        
    # D2 & D11: Revenue Growth Spline (Good: >10%, Bad: <-5%, Cap: 60)
    sg_check = data.get("Sales_Growth_5Y%", 0) or data.get("Sales_Growth_TTM%", 0)
    if sg_check is not None:
        apply_spline_cap(sg_check, 10.0, -5.0, 60, "Growth Decay Spline")
        if sg_check < -5:
            apply_spline_cap(sg_check, -5.0, -25.0, 40, "Declining Revenue Spline")

    # D3: Extreme ROE anomaly (data error)  ROE > 100% decaying aggressively
    if best_roe is not None and best_roe > 100:
        apply_spline_cap(best_roe, 100.0, 250.0, 45, "Anomalous ROE Risk")
    
    # D4: Profit margin spline
    pm = data.get("Profit_Margin%", 0)
    if pm is not None:
        apply_spline_cap(pm, 10.0, -5.0, 60, "Margin Decay Spline")
    
    # D5: F-Score quality mismatch
    f_score_val = data.get("F_Score", 0)
    if f_score_val <= 4:
        # If F-Score is low, prevent high overall scores smoothly
        score_ceiling = min(score_ceiling, 65 + (f_score_val * 6.5))
        disqualifiers.append(f"Quality Floor Spline (F:{f_score_val})")
    
    # D6: Overvaluation Spline (Good gap: 0%, Bad gap: -70%, Cap: 65)
    value_gap = data.get("Value_Gap%", 0)
    if value_gap < 0:
        apply_spline_cap(value_gap, 0.0, -70.0, 65, "Overvaluation Spline")
        
    # D8: Cash Flow conversion (Good: >0.8, Bad: <0.0, Cap: 60)
    cfo_pat = data.get("CFO_PAT_Ratio", 0)
    if cfo_pat is not None:
        apply_spline_cap(cfo_pat, 0.8, 0.0, 60, "Cash Quality Spline")
    
    # D9: Governance Risk (Soft anchor)
    if prom_hold > 0 and inst_hold is not None:
        if prom_hold < 30 and inst_hold < 10:
            apply_spline_cap(prom_hold, 30.0, 10.0, 65, "Anchor Investor Spline")
            
    # D12: EPS Growth Spline
    eps_check = data.get("EPS_Growth%", 0)
    if eps_check is not None:
        apply_spline_cap(eps_check, 10.0, -10.0, 65, "EPS Decay Spline")

    # --- Phase 4: D13 MULTI-DIMENSION QUALITY GATE (Continuous) ---
    factor_scores = [score_sales, score_roe, score_cfo, score_val, 
                     score_eps, score_fscore, score_de, score_mom_combined]
    avg_quality = sum(factor_scores) / len(factor_scores)
    apply_spline_cap(avg_quality, 50.0, 30.0, 55, "Lopsided Profile Spline")
    
    # --- Phase 4: D14 CYCLICALITY GUARD (Smooth Peak Risk) ---
    CYCLICAL_SECTORS = {"Energy", "Basic Materials", "Utilities"}
    if stock_sector in CYCLICAL_SECTORS:
        if best_roe > 0 and pe is not None and pe > 0:
            cycle_risk = best_roe / pe
            apply_spline_cap(cycle_risk, 2.0, 5.0, 65, "Cyclical Peak Spline")
    
    # --- D15: PROMOTER BEHAVIOUR INTELLIGENCE ---
    # Heavy insider dumping after stock run-up
    try:
        from modules.promoter_intel import calculate_promoter_score
        _prom_result = calculate_promoter_score(data.get("Symbol", ""))
        if _prom_result and _prom_result.get("is_disqualified"):
            score_ceiling = min(score_ceiling, 60)
            disqualifiers.append("D15: Heavy Insider Sell-Off")
            factor_audit.append({"name": "D15: Heavy Insider Sell-Off", "value": -40})
        _prom_adj = _prom_result.get("score_adjustment", 0)
        if _prom_adj > 0:
            total_bonus += _prom_adj  # Promoter buying conviction
            factor_audit.append({"name": "Promoter Buying Boost", "value": _prom_adj})
        elif _prom_adj < 0:
            total_penalty += abs(_prom_adj)  # Promoter selling penalty
            factor_audit.append({"name": "Promoter Selling Penalty", "value": _prom_adj})
    except Exception:
        pass  # Graceful degradation: promoter intel is optional
    
    # --- D16: ESTIMATE MOMENTUM DISQUALIFIER ---
    # 3 consecutive estimate downgrades
    try:
        from modules.estimates import get_estimate_data
        _est_result = get_estimate_data(data.get("Symbol", ""))
        _est_mom = _est_result.get("momentum", {})
        if _est_mom.get("is_disqualified"):
            score_ceiling = min(score_ceiling, 55)
            disqualifiers.append("D16: Estimate Collapse (3Q consecutive downgrades)")
            factor_audit.append({"name": "D16: Estimate Collapse", "value": -45})
        _est_cap = _est_mom.get("score_cap")
        if _est_cap is not None:
            score_ceiling = min(score_ceiling, _est_cap)
            disqualifiers.append(f"Earnings Miss Streak (cap {_est_cap})")
            factor_audit.append({"name": "Earnings Miss Streak", "value": -(100-_est_cap)})
        _est_adj = _est_mom.get("score_adjustment", 0)
        if _est_adj > 0:
            total_bonus += _est_adj  # Estimate momentum bonus
            factor_audit.append({"name": "Estimate Momentum Bonus", "value": _est_adj})
        elif _est_adj < 0:
            total_penalty += abs(_est_adj)  # Estimate downgrade penalty
            factor_audit.append({"name": "Estimate Downgrade Penalty", "value": _est_adj})
    except Exception:
        pass  # Graceful degradation: estimates are optional
    
    # --- D7: 12-POINT INSTITUTIONAL QUALITY CHECKLIST ---
    # Combines Finology + Tickertape + Sovrenn methodology
    checklist_pass = 0
    checklist_total = 12
    
    # C1: Market Cap > 1,000 Cr (liquidity & stability)
    if data.get("Market_Cap_Cr", 0) > 1000:
        checklist_pass += 1
    # C2: Valuation  PE < 25 (reasonable price)
    if pe is not None and 0 < pe < 25:
        checklist_pass += 1
    # C3: Profitability  ROE > 17% (institutional threshold)
    if best_roe > 17:
        checklist_pass += 1
    # C4: Leverage  Debt/Equity between 0 and 1.0 (must have data)
    de = data.get("Debt_Equity", -1)
    if 0 <= de < 1.0:
        checklist_pass += 1
    # C5: Cash Quality  CFO/PAT > 1.0 (profits backed by cash)
    if data.get("CFO_PAT_Ratio", 0) > 1.0:
        checklist_pass += 1
    # C6: Momentum  between 0 and 25% drop from 52W high (must have data)
    down_pct = data.get("Down_From_52W_High%", -1)
    if 0 <= down_pct < 25:
        checklist_pass += 1
    # C7: Revenue Growth > 15% CAGR (Aggressive Growth Gate)
    sg = data.get("Sales_Growth_5Y%", 0) or data.get("Sales_Growth_TTM%", 0)
    if sg > 15:
        checklist_pass += 1
    # C8: Earnings Growth  EPS Growth positive
    eps_g = data.get("EPS_Growth%", 0)
    if eps_g > 0:
        checklist_pass += 1
    # C9: Promoter Conviction  Holding > 50% (skin in the game)
    if prom_hold > 50:
        checklist_pass += 1
    # C10: Financial Fortress  F-Score >= 6 (Piotroski quality)
    if data.get("F_Score", 0) >= 6:
        checklist_pass += 1
    # C11: Profit Uptrend (Sovrenn)  both revenue AND earnings growing > 10%
    #       Aggressive confirmation of execution
    if sg > 10 and eps_g > 10:
        checklist_pass += 1
    # C12: Valuation Comfort (Sovrenn + Workflow Step 3)
    #       Trading at or below fair value OR PE < 20 (good business at fair price)
    if value_gap > 0 or (pe is not None and 0 < pe < 20):
        checklist_pass += 1
    
    # Checklist  Bonus (only for Institutional/Strong Elite quality > 9/12)
    if checklist_pass >= 11:
        base_score += 5  # Institutional grade  nearly all boxes ticked
    # Removed +3 bonus for 9/12 pass to increase difficulty for Elite status
    
    # --- Phase 4: CONTINUOUS CHECKLIST SPLINE (Institutional fix for step-cliffs) ---
    # Replaces binary steps with a smooth decay curve from 12 passes down to 0
    # Elite Gate (9/12) is preserved as a inflection point
    
    # Smooth Penalty Spline: 12 passes (0) -> 9 passes (-2) -> 6 passes (-8) -> 0 passes (-20)
    if checklist_pass >= 9:
        checklist_penalty = (12 - checklist_pass) * 0.66  # Linear decay for top tier
    else:
        # Exponential decay for lower tiers
        checklist_penalty = 2.0 + ((9 - checklist_pass) / 9.0 * 18.0)
    
    # Smooth Ceiling Spline: 12 passes (100) -> 9 passes (80) -> 6 passes (65) -> 0 passes (40)
    if checklist_pass >= 9:
        # Interpolate between 80 and 100
        current_ceiling = 80 + (checklist_pass - 9) * (20 / 3.0)
    else:
        # Interpolate between 40 and 80
        current_ceiling = 40 + (checklist_pass / 9.0 * 40.0)
        
    base_score -= checklist_penalty
    score_ceiling = min(score_ceiling, current_ceiling)
    
    if checklist_pass < 9:
        disqualifiers.append(f"Institutional Quality Gate {checklist_pass}/{checklist_total}")

    # Apply ceiling
    final_score = min(base_score, score_ceiling)
    
    # --- PHASE 4: DETERMINISTIC TIE-BREAKER (Institutional Requirement) ---
    # Add a microscopic deterministic epsilon based on symbol hash to prevent ranking draws
    # This ensures two stocks with the same fundamental score have a stable, non-random order
    import hashlib
    sym_hash = int(hashlib.md5(data.get("Symbol", "").encode()).hexdigest(), 16) % 1000
    epsilon = sym_hash / 100000.0 # Range 0.00000 to 0.00999
    
    final_score += epsilon
    
    # Phase 1: Track Disqualifiers in Audit payload
    for dq in disqualifiers:
        factor_audit.append({"name": dq, "value": round(score_ceiling - 100, 1)})
    
    # --- FINAL SCORE ---
    raw_score = round(base_score, 1)
    
    return {
        "total_score": round(max(0, min(final_score, 100)), 3), # Preserving epsilon precision
        "raw_score": raw_score,
        "checklist_score": f"{checklist_pass}/{checklist_total}",
        "data_confidence": data_confidence,
        "conviction_score": conviction['conviction_score'],
        "conviction_boost": conviction['conviction_boost'],
        "institutional_interest": conviction['institutional_interest'],
        "super_investors": ", ".join(conviction['investors']),
        "scoring_strategy": scoring_strategy,
        "factor_penalties": factor_audit,
        "factor_breakdown": {
             "Fundamentals": round((score_sales*w_sales + score_roe*w_roe + score_cfo*w_cfo + score_eps*w_eps), 1),
             "Value": round((score_val*w_val), 1),
             "Risk": round((score_fscore*w_fscore + score_de*w_de), 1),
             "Momentum": round((score_mom_combined*w_mom), 1),
             "Smart_Money": 10 if conviction['institutional_interest'] else 0,
             "Sector": sector_boost
        }
    }
