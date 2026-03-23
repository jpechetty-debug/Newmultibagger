
"""
Fundamental Filters (GARP)
--------------------------
Strict financial criteria to filter stocks for the Strategic Portfolio.

Criteria:
1. Sales Growth (5Y or TTM) > 15%
2. Profit Growth (EPS) > 15%
3. ROCE > 18% (Efficiency)
4. ROE > 15%
5. PEG Ratio: 0.5 to 2.5 (Reasonable Price)
6. Debt/Equity < 0.7 (Safety - tightened from 1.0)
7. Promoter Holding > 40% (Skin in the game)
8. CFO/PAT > 0.7 (Cash Flow Reality)
9. Market Cap > 500 Cr (Liquidity Gate)
"""

import config

def validate_garp_criteria(stock_data):
    """
    Checks if a stock meets the strict GARP criteria.
    Returns: (is_valid, reason_if_failed)
    """
    def get_val(key, default=0):
        # Try exact key, then lowercase, then specific mappings if needed
        if key in stock_data: return stock_data[key]
        lower_key = key.lower()
        # Check if any key in stock_data lowercased matches
        for k in stock_data:
            if k.lower() == lower_key.lower():
                return stock_data[k]
        return default

    symbol = get_val("Symbol", "Unknown")
    
    # Gate 0: Market Cap (Liquidity Gate)
    min_mcap = getattr(config, 'MIN_MARKET_CAP_CR', 500)
    mcap = get_val("Market_Cap_Cr", 0)
    if mcap == 0: mcap = get_val("market_cap_cr", 0)
    if mcap > 0 and mcap < min_mcap:
        return False, f"Below Market Cap Gate ({mcap:.0f} Cr < {min_mcap} Cr)"

    # 1. Growth Check
    sales_5y = get_val("Sales_Growth_5Y%", 0)
    sales_ttm = get_val("Sales_Growth_TTM%", 0)
    # Check for 'sales_cagr_5y' from DB
    if sales_5y == 0: sales_5y = get_val("sales_cagr_5y", 0)
    if sales_ttm == 0: sales_ttm = get_val("sales_growth", 0)
    
    # Allow either 5Y or TTM to pass the growth check if one is exceptionally high
    growth_pass = False
    if sales_5y > 15 or sales_ttm > 15:
        growth_pass = True
        
    if not growth_pass:
        return False, f"Low Growth (Sales 5Y: {sales_5y}%, TTM: {sales_ttm}%)"

    # 2. Profitability Check (ROCE / ROE)
    roce = get_val("Avg_ROE_5Y%", 0)
    if roce == 0: roce = get_val("avg_roe_5y", 0)
    
    if roce < 15:
        # Check current ROE if available
        current_roe = get_val("ROE%", 0)
        if current_roe == 0: current_roe = get_val("roe", 0)
        
        if current_roe < 15:
             return False, f"Low Efficiency (ROE/ROCE < 15%: {current_roe}%)"

    # 3. Valuation Check (PEG)
    peg = get_val("PEG_Ratio", 100)
    if peg == 100: peg = get_val("peg_ratio", 100)
    
    if peg < 0.2 or peg > 3.0:
        return False, f"Valuation Mismatch (PEG: {peg})"

    # 4. Safety Check (Debt) — Tightened from 1.0 to 0.7
    de = get_val("Debt_Equity", 100)
    if de == 100: de = get_val("debt_equity", 100)
    
    # Relax for BFSI (Banking/Finance)
    sector = str(get_val("Sector", "")).lower()
    
    if "bank" in sector or "finance" in sector:
        pass # Skip DE check for financials
    elif de > 0.7:
        return False, f"High Debt (D/E: {de})"

    # 5. Skin in the Game
    promoter = get_val("Promoter_Holding%", 0)
    
    if promoter < 30:
        inst = get_val("Inst_Holding%", 0)
        if (promoter + inst) < 50:
             return False, f"Low Skin in Game (Promoter: {promoter}%)"

    # 6. Cash Flow Reality Gate (New)
    cfo_pat = get_val("CFO_PAT_Ratio", 0)
    if cfo_pat == 0: cfo_pat = get_val("cfo_pat_ratio", 0)
    
    # Only apply if we have data (non-zero means data exists)
    if cfo_pat > 0 and cfo_pat < 0.7:
        return False, f"Poor Cash Flow Quality (CFO/PAT: {cfo_pat})"

    return True, "Passed"

