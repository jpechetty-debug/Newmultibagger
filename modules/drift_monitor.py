def get_sector_thresholds(sector=None):
    """Returns dynamic thresholds based on stock sector."""
    # Tech/Growth generally handle higher valuations
    if sector and ("Technology" in sector or "Software" in sector):
        return {"peg_limit": 5.0, "sales_growth_min": 0, "f_score_min": 4}
    # Value/Manufacturing
    elif sector and ("Manufacturing" in sector or "Metals" in sector):
         return {"peg_limit": 3.0, "sales_growth_min": -5, "f_score_min": 5}
    # Defaults
    return {"peg_limit": 4.0, "sales_growth_min": -5, "f_score_min": 4}

def monitor_drift(stock_data):
    """
    Phase 27: Live Drift Monitor.
    Detects if the Investment Thesis is broken using dynamic thresholds and momentum.
    Acts as "Exit Intelligence".
    
    Returns:
        status (str): "Safe", "Warning", "Thesis Broken"
        reason (str): Explanation
    """
    reasons = []
    
    # 1. Technical Drift (Trend Breakdown)
    price = stock_data.get("Price", 0)
    dma_50 = stock_data.get("50_DMA", 0)
    dma_200 = stock_data.get("200_DMA", 0)
    rsi = stock_data.get("RSI", 50) # Neutral default
    
    if price > 0:
        if price < dma_200:
            reasons.append("Price < 200DMA (Long Term Trend Broken)")
        elif price < dma_50:
             reasons.append("Price < 50DMA (Short Term Weakness)")
             
        # Momentum check
        if rsi < 35:
            reasons.append("RSI < 35 (Severe Momentum Loss)")
            
    # Get dynamic thresholds
    sector = stock_data.get("Sector", "Unknown")
    thresholds = get_sector_thresholds(sector)
             
    # 2. Fundamental Drift (Quality Decay)
    f_score = stock_data.get("F_Score", 0)
    if f_score <= thresholds["f_score_min"]:
        reasons.append(f"F-Score Deterioration (<={thresholds['f_score_min']})")
        
    # 3. Growth Drift
    sales_growth = stock_data.get("Sales_Growth_TTM%", 0)
    if sales_growth < thresholds["sales_growth_min"]:
        reasons.append(f"Negative/Poor Sales Growth (<{thresholds['sales_growth_min']}%)")
        
    # 4. Valuation Drift (Overvaluation)
    peg = stock_data.get("PEG_Ratio", 0)
    if peg > thresholds["peg_limit"]:
        reasons.append(f"Sector Extreme Overvaluation (PEG > {thresholds['peg_limit']})")
        
    # Determine Status
    if not reasons:
        return "Safe", "Thesis Intact"
        
    # Count severity
    severe_count = sum(1 for r in reasons if "200DMA" in r or "Sales" in r or "F-Score" in r or "Momentum" in r)
    
    if severe_count >= 2:
        return "THESIS BROKEN", "; ".join(reasons)
    elif severe_count == 1:
        return "Warning", "; ".join(reasons)
    else:
        return "Caution", "; ".join(reasons)
