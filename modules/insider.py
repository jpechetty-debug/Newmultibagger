def analyze_insider_activity(stock_data):
    """
    Phase 29: Insider & Institutional Activity.
    Analyzes ownership structure for conviction signals.
    
    Returns:
        insider_score (int): Bonus/Penalty.
        insider_status (str): "High Conviction", "Neutral", "Red Flag".
    """
    try:
        promoter_hold = stock_data.get("Promoter_Holding%", 0)
        inst_hold = stock_data.get("Inst_Holding%", 0)
        pledged = stock_data.get("Pledged_Shares%", 0) # Assumes we extracted this if available
        
        score = 0
        status = "Neutral"
        
        # 1. Promoter Holding (Skin in the Game)
        # > 70%: Very High (Owners are confident, but low float)
        # > 50%: Healthy
        # < 20%: Warning (No skin in the game, professional management or dump?)
        
        if promoter_hold > 65:
            score += 5
            status = "Owner Operator 👑"
        elif promoter_hold > 50:
            score += 3
            status = "Healthy Owner"
        elif promoter_hold < 10:
            score -= 3
            status = "Low Promoter Hold"
            
        # 2. Institutional Holding (Smart Money)
        # > 30%: Institutional Favorite (Crowded?)
        # > 15%: Smart Money Entry
        # < 1%: Retail Trap?
        
        if inst_hold > 25:
            score += 3
            status += " + Big Inst"
        elif inst_hold > 10:
            score += 1
            status += " + Inst"
            
        # 3. Pledged Shares (The Killer)
        # If Promoters have pledged their shares, it's a huge risk.
        if pledged > 20:
             score -= 10
             status = "CRITICAL: HIGH PLEDGE ⚠️"
        elif pledged > 5:
             score -= 5
             status += " (Pledged!)"
             
        return score, status
        
    except:
        return 0, "Unknown"
