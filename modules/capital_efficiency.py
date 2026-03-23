def analyze_capital_efficiency(stock_data):
    """
    Phase 28: Capital Efficiency Ranking.
    Distinguishes 'Compounders' from 'Capital Destroyers'.
    
    Returns:
        roic (float): Estimated ROIC %.
        efficiency_status (str): "Compounder", "Standard", "Destroyer".
        efficiency_score (int): Bonus/Penalty (+5 to -5).
    """
    try:
        # 1. Try to get ROIC from data if available (yfinance sometimes has returnOnEquity, returnOnAssets, but ROIC is scarce)
        # We will attempt to calculate or use proxies.
        
        # Proxy: ROIC ~ ROE * (1 - Debt/Asset) + RODA * (Debt/Asset)? 
        # Simpler: Use ROE if Debt is Low. If Debt is High, ROE is inflated.
        
        roe = stock_data.get("ROE%", 0)
        debt_equity = stock_data.get("Debt_Equity", 0)
        profit_margin = stock_data.get("Profit_Margin%", 0)
        
        # Estimate Invested Capital efficiency roughly
        # High ROE + Low Debt = True Compounding
        # High ROE + High Debt = Financial Engineering (Leveraged Returns)
        
        # Let's adjust ROE for Debt to get a "Unlevered Return" proxy
        # Adjusted ROE = ROE / (1 + Debt_Equity) * (something)
        # Actually, let's just use strict criteria.
        
        score = 0
        status = "Standard"
        
        # Criteria for COMPOUNDER (Value Creator)
        # ROE > 15% AND Debt/Equity < 0.5 AND Margins > 10%
        if roe > 15 and debt_equity < 0.5 and profit_margin > 10:
            status = "Compounder 💎"
            score = 5
        elif roe > 20 and debt_equity < 1.0:
            status = "Compounder (Lev)"
            score = 3
            
        # Criteria for CAPITAL DESTROYER
        # ROE < 8% (Below Cost of Capital in India)
        elif roe < 8:
            status = "Capital Destroyer 🗑️"
            score = -5
        elif roe < 12:
            status = "Sub-Par"
            score = -2
            
        return roe, status, score
        
    except Exception as e:
        return 0, "Error", 0
