def calculate_tax_efficiency(cagr, strategy_type="Balanced"):
    """
    Phase 38: Turnover & Tax Efficiency Layer.
    Estimates the impact of Taxes on the Portfolio's CAGR.
    Based on Indian Tax Regime (2024-25):
    - STCG (Short Term): 20% (Turnover < 1 year)
    - LTCG (Long Term): 12.5% (Turnover > 1 year)
    
    Args:
        cagr (float): The pre-tax Net CAGR (after slippage).
        strategy_type (str): "Momentum", "Value", "Quality", "Balanced".
        
    Returns:
        post_tax_cagr (float): Real compounding rate.
        tax_drag (float): % lost to taxes.
        turnover_est (float): Estimated annual turnover (0.0 to 1.0+).
    """
    
    # 1. Estimate Turnover based on Strategy
    # Momentum portfolios churn 200-300% a year.
    # Quality/Value portfolios might churn 20-50%.
    
    turnover_map = {
        "Aggressive (Bull)": 2.0,  # High Churn (Momentum)
        "Defensive (Bear)": 0.3,   # Low Churn (Quality/Div)
        "Balanced (Neutral)": 0.8, # Moderate
        "Momentum": 2.5,
        "Quality": 0.2,
        "Value": 0.4
    }
    
    turnover = turnover_map.get(strategy_type, 0.8)
    
    # 2. Estimate Tax Rate
    # If Turnover > 1.0, mostly STCG (20%)
    # If Turnover < 0.5, mostly LTCG (12.5%)
    
    # Weighted Average Tax Rate
    # Portion Short Term = min(turnover, 1.0) ? 
    # Let's simplify:
    # High Churn (>100%) -> 90% STCG, 10% LTCG
    # Med Churn (50-100%) -> 50% STCG, 50% LTCG
    # Low Churn (<50%) -> 20% STCG, 80% LTCG
    
    stcg_rate = 0.20
    ltcg_rate = 0.125
    
    if turnover > 1.0:
        effective_tax_rate = (0.9 * stcg_rate) + (0.1 * ltcg_rate)
    elif turnover > 0.5:
        effective_tax_rate = (0.5 * stcg_rate) + (0.5 * ltcg_rate)
    else:
        effective_tax_rate = (0.2 * stcg_rate) + (0.8 * ltcg_rate)
        
    # 3. Calculate Post-Tax Return
    # Tax is paid on the GAIN.
    # Post_Tax_Return = Nominal_Return * (1 - Tax_Rate)
    
    if cagr > 0:
        tax_drag = cagr * effective_tax_rate
        post_tax_cagr = cagr - tax_drag
    else:
        # No tax on losses (ignoring carry forward for simplicity)
        tax_drag = 0
        post_tax_cagr = cagr
        
    return post_tax_cagr, tax_drag, turnover, effective_tax_rate * 100
