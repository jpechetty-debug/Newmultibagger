def analyze_liquidity(stock_data):
    """
    Phase 22: Liquidity & Slippage Intelligence.
    Analyzes if a stock is liquid enough for institutional entry.
    
    Returns:
        liquidity_score (int): 0-100 (100 = Nifty 50 Liquidity).
        risk_flag (bool): True if liquidity is dangerously low.
        reason (str): Warning message.
    """
    try:
        price = stock_data.get("Price", 0)
        avg_vol = stock_data.get("Avg_Volume_10D", 0)
        mcap_cr = stock_data.get("Market_Cap_Cr", 0)
        
        if price == 0 or avg_vol == 0:
            return 0, True, "No Volume Data"
            
        # 1. Average Daily Value Traded (ADVT) in Crores
        advt_cr = (avg_vol * price) / 10000000
        
        # Scoring based on ADVT
        # > 100 Cr = 100 (Liquid)
        # > 10 Cr = 80 (Good for Retail/HNI)
        # > 2 Cr = 50 (Manageable)
        # < 1 Cr = 0 (Illiquid Trap)
        
        score = 0
        risk_flag = False
        reason = ""
        
        if advt_cr >= 100:
            score = 100
        elif advt_cr >= 50:
            score = 90
        elif advt_cr >= 10:
            score = 80
        elif advt_cr >= 5:
            score = 70
        elif advt_cr >= 2:
            score = 50
            reason = "Moderate Liquidity (< 5Cr)"
        elif advt_cr >= 1:
            score = 30
            risk_flag = True # Institutional Risk
            reason = "Low Liquidity (< 2Cr)"
        else:
            score = 0
            risk_flag = True
            reason = "Illiquid / Roach Motel (< 1Cr)"
            
        # 2. Impact Cost Proxy (Slippage Hazard)
        # High Impact Cost = High Volatility (ATR) on Low Volume
        # If ATR is high relative to price (%), and Volume is low, slippage is high.
        atr_pct = (stock_data.get("ATR", 0) / price) * 100
        
        if risk_flag:
            score -= 20 # Double penalty
            
        return score, risk_flag, reason
        
    except Exception as e:
        return 0, True, f"Error: {str(e)}"
