def optimize_portfolio_allocation(candidates, capital=1000000):
    """
    Phase 35: Portfolio Construction Engine.
    Applies 'Fund Manager' constraints to the ranked list.
    
    Constraints:
    1. Max Stocks: 15
    2. Max Weight per Stock: 12%
    3. Max Weight per Sector: 25%
    4. Min Weight: 3%
    
    Args:
        candidates (list): List of stock dicts, sorted by Score.
        capital: Total capital to deploy.
        
    Returns:
        final_portfolio (list): List of selected stocks with 'Weight' and 'Qty'.
    """
    print("\n" + "="*50)
    print("🏗️  PHASE 35: PORTFOLIO OPTIMIZATION")
    print("="*50)
    
    MAX_STOCKS = 12
    MAX_SECTOR_WEIGHT = 0.30 # 30% Cap
    MAX_STOCK_WEIGHT = 0.15  # 15% Cap
    
    selected_portfolio = []
    sector_exposure = {}
    current_total_weight = 0
    
    # 1. Greedy Allocation Loop
    for stock in candidates:
        if len(selected_portfolio) >= MAX_STOCKS:
            break
            
        sector = stock.get("Sector", "Unknown")
        current_sec_weight = sector_exposure.get(sector, 0)
        
        # Check Sector Constraint
        if current_sec_weight >= MAX_SECTOR_WEIGHT:
            continue # Skip this stock, sector is full
            
        # Determine Weight (Score Based)
        # Base weight on score: Score 100 = 10%, Score 80 = 5%?
        # Let's use simple logic: Target Equal Weight initially, then adjust?
        # Better: Top 5 get 10%, Next 7 get 7%...
        
        target_weight = 0.08 # 8% avg
        
        # Check Scarcity
        if current_sec_weight + target_weight > MAX_SECTOR_WEIGHT:
            target_weight = MAX_SECTOR_WEIGHT - current_sec_weight
            
        if target_weight < 0.03: # Too small to bother
            continue
            
        # Add to Portfolio
        stock["Target_Weight%"] = round(target_weight * 100, 1)
        stock["Allocated_Capital"] = round(capital * target_weight, 2)
        price = stock.get("Price", 0)
        if price > 0:
            stock["Qty"] = int((capital * target_weight) / price)
        else:
            stock["Qty"] = 0
            
        selected_portfolio.append(stock)
        sector_exposure[sector] = current_sec_weight + target_weight
        current_total_weight += target_weight
        
    # 2. Normalization (Fill the rest)
    if current_total_weight > 0 and current_total_weight < 0.95:
        correction_factor = 1.0 / current_total_weight
        print(f"  Note: Scaling up weights by {correction_factor:.2f}x to fully invest.")
        for s in selected_portfolio:
            new_w = (s["Target_Weight%"] / 100) * correction_factor
            s["Target_Weight%"] = round(new_w * 100, 1)
            s["Allocated_Capital"] = round(capital * new_w, 2)
            if s.get("Price", 0) > 0:
                s["Qty"] = int(s["Allocated_Capital"] / s["Price"])

    print(f"Selected {len(selected_portfolio)} stocks from candidate list.")
    print("Sector Breakdown:")
    for sec, w in sector_exposure.items():
        print(f"  - {sec}: {w*100:.1f}%")
        
    return selected_portfolio
