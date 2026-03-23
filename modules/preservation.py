def get_portfolio_allocation(market_regime, nifty_volatility_pct=0):
    """
    Phase 30: Capital Preservation Mode.
    Determines the safe Capital Allocation based on Market Conditions.
    
    Args:
        market_regime (str): "Bull Market", "Bear Market", "Sideways/Correction".
        nifty_volatility_pct (float): Optional volatility metric.
        
    Returns:
        equity_pct (int): Suggested Equity Exposure.
        cash_pct (int): Suggested Cash Position.
        message (str): War Room Advisory.
    """
    equity_pct = 100
    cash_pct = 0
    message = "✅ Conditions Favorable. Aggressive Deployment Permitted."
    
    if market_regime == "Bull Market":
        equity_pct = 100
        cash_pct = 0
        message = "🚀 BULL MARKET: Full Throttle (100% Equity)."
        
    elif market_regime == "Sideways":
        equity_pct = 80
        cash_pct = 20
        message = "⚠️ CHOPPY MARKET: Trim Positions (80% Equity / 20% Cash)."
        
    elif market_regime == "Bear Market":
        equity_pct = 40
        cash_pct = 60
        message = "🛡️ BEAR MARKET: CAPITAL PRESERVATION MODE (60% CASH)."
        
    elif market_regime == "Crash/Correction":
        equity_pct = 0
        cash_pct = 100
        message = "🚨 MARKET CRASH DETECTED: EXIT ALL POSITIONS (100% CASH)."
        
    # Volatility Override (if VIX proxy is high)
    # This is a placeholder for VIX logic if we had it
    
    return equity_pct, cash_pct, message
