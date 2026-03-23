def check_exit_conditions(stock_data):
    """
    Phase 34: Thesis Break Monitor (Exit Engine).
    Checks if a stock has violated critical 'Hold' criteria.
    Used to filter out 'Traps' from the screener or trigger Sells in a portfolio.
    
    Returns:
        exit_triggered (bool): True if stock should be sold/avoided.
        reason (str): The specific rule violated.
    """
    symbol = stock_data.get("Symbol", "Unknown")
    price = stock_data.get("Price", 0)
    dma_200 = stock_data.get("200_DMA", 0)
    f_score = stock_data.get("F_Score", 0)
    peg = stock_data.get("PEG_Ratio", 0)
    sales_growth = stock_data.get("Sales_Growth_TTM%", 0)
    
    # Rule 1: Trend Break (The 200 DMA Filter)
    # Institutional flows usually stop when Price < 200 DMA.
    if price > 0 and dma_200 > 0 and price < dma_200:
        return True, "Trend Break (Price < 200 DMA)"
        
    # Rule 2: Quality Collapse (F-Score)
    # If F-Score drops below 4, the fundamentals are deteriorating.
    if f_score < 4:
        return True, "Quality Collapse (F-Score < 4)"
        
    # Rule 3: Extreme Valuation (PEG)
    # If PEG > 5, growth is priced in 5x over. Danger zone.
    if peg > 5.0:
        return True, "Extreme Valuation (PEG > 5)"
        
    # Rule 4: Growth Stagnation (for Growth Stocks)
    # If standard growth stock stops growing.
    if sales_growth < 0:
        return True, "Growth Stagnation (Negative Sales Growth)"
        
    return False, "Safe"
