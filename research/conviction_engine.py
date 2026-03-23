
"""
Conviction Engine
-----------------
Calculates a 'Conviction Score' for a given stock based on:
1. Principle Alignment (Does it match our core filters?)
2. Institutional Presence (Is it held by Super Investors?)
3. Growth Quality (Consistency of growth)

This score feeds into the Allocation Engine to determine position sizing.
"""

from .super_investor_registry import get_super_investor_interest

def calculate_conviction_score(stock_data):
    """
    Analyzes stock data and returns a conviction dictionary.
    
    Expected stock_data keys:
    - symbol
    - sales_growth (float)
    - profit_growth (float)
    - roce (float)
    - debt_to_equity (float)
    - promoter_holding (float)
    - pledge (float)
    """
    score = 0
    max_score = 100
    details = []

    # 1. Institutional Presence (Cloning Layer)
    investors = get_super_investor_interest(stock_data.get('symbol', ''))
    institutional_boost = 0
    if investors:
        institutional_boost = 15 + (len(investors) * 5) # Base 15 + 5 per investor
        score += institutional_boost
        details.append(f"Super Investors: {', '.join(investors)} (+{institutional_boost})")
    
    # 2. Principle Alignment (Strategic Filter Layer)
    # ROCE > 20%
    roce = stock_data.get('roce', 0)
    if roce > 25:
        score += 20
        details.append("Excellent ROCE > 25% (+20)")
    elif roce > 18:
        score += 15
        details.append("Good ROCE > 18% (+15)")
    
    # Growth > 15%
    sales_growth = stock_data.get('sales_growth', 0)
    profit_growth = stock_data.get('profit_growth', 0)
    
    if sales_growth > 20 and profit_growth > 20:
        score += 25
        details.append("Double Engine Growth > 20% (+25)")
    elif sales_growth > 15:
        score += 15
        details.append("Healthy Sales Growth > 15% (+15)")
        
    # 3. Governance/Safety (Risk Layer)
    d2e = stock_data.get('debt_to_equity', 0)
    pledge = stock_data.get('pledge', 0)
    
    if d2e < 0.1:
        score += 15
        details.append("Debt Free (+15)")
    elif d2e < 0.5:
        score += 10
        details.append("Low Debt (+10)")
        
    if pledge == 0:
        score += 10
        details.append("Zero Pledge (+10)")
    elif pledge > 0:
        score -= 20
        details.append("Promoter Pledge Penalty (-20)")
        
    # Cap Score
    final_score = min(score, max_score)
    
    return {
        "conviction_score": final_score,
        "institutional_interest": bool(investors),
        "investors": investors,
        "details": details,
        "conviction_boost": round(institutional_boost / 100.0, 2) # e.g. 0.15 for allocation multiplier
    }
