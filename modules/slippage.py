def calculate_slippage(market_cap_cr, avg_volume_cr):
    """
    Phase 33: Real-World Slippage Model.
    Estimates the 'Impact Cost' of entering and exiting a position.
    
    Args:
        market_cap_cr: Market Cap in Crores.
        avg_volume_cr: Average Daily Value Traded in Crores.
        
    Returns:
        slippage_pct (float): One-way slippage %.
        reason (str): Basis for estimate.
    """
    # Base Transaction Costs (STT + Exchange + Brokerage + GST) ~ 0.1%
    base_cost = 0.1
    impact_cost = 0.0
    
    reason = "Standard"
    
    # 1. Liquidity-Based Impact
    if avg_volume_cr > 500: # Mega Liquid (Reliance, HDFC)
        impact_cost = 0.1 # Very tight spreads
        reason = "Tier 1 Liquid"
    elif avg_volume_cr > 100: # Liquid Large Cap
        impact_cost = 0.2
        reason = "Large Cap"
    elif avg_volume_cr > 10: # Mid Cap
        impact_cost = 0.5
        reason = "Mid Cap Impact"
    elif avg_volume_cr > 2: # Small Cap
        impact_cost = 1.0 
        reason = "Small Cap Slippage"
    else: # Illiquid / Micro
        impact_cost = 2.5 
        reason = "Micro Cap Trap ⚠️"
        
    # Total One-Way Cost
    total_slippage = base_cost + impact_cost
    
    return total_slippage, reason

def apply_slippage_to_returns(gross_return_pct, slippage_pct, turnover=1.0):
    """
    Calculates Net Return after Entry + Exit slippage.
    
    Args:
        gross_return_pct: The theoretical backtest return.
        slippage_pct: One-way cost.
        turnover: Portfolio turnover per year (1.0 = 100% replacement).
    """
    # Round Trip Cost = Entry + Exit = 2 * slippage
    total_drag = (slippage_pct * 2) * turnover
    
    net_return = gross_return_pct - total_drag
    return net_return, total_drag
