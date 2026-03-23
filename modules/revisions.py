import pandas as pd

def analyze_revisions(ticker):
    """
    Phase 21: Earnings & Target Revisions.
    Analyzes analyst sentiment trends.
    Returns:
       score_impact (int): +5 / -5 based on trend.
       sentiment (str): "Improving", "Deteriorating", "Stable".
    """
    score = 0
    sentiment = "Stable"
    
    try:
        # 1. Analyst Recommendations Trend
        # yfinance returns a DataFrame with 'period', 'strongBuy', 'buy', 'hold', 'sell', 'strongSell'
        recs = ticker.recommendations
        
        if recs is not None and not recs.empty:
            # Sort by period if needed, usually it's correct.
            # We want to compare '0m' (Current) vs '-1m' (Last Month)
            # Or '-1m' vs '-2m'
            
            # Note: yf structure changes often. 
            # Assuming 'period' column exists and has values like '0m', '-1m'
            
            # Simplify: Check if 'strongBuy' + 'buy' is high relative to history or total
            # Actually, let's just look at the RATIO of Buy vs Sell in the latest period
            
            latest = recs.iloc[0] # Usually latest is first or last? Need to verify.
            # Usually yfinance recommendations are indexed 0..N
            
            # Let's calculate a "Sentiment Score" for each row and check trend
            # Score = (StrongBuy*2 + Buy*1) - (Sell*1 + StrongSell*2)
            
            sentiment_scores = []
            for idx, row in recs.iterrows():
                s = (row.get('strongBuy', 0) * 2) + row.get('buy', 0) - row.get('sell', 0) - (row.get('strongSell', 0) * 2)
                sentiment_scores.append(s)
                
            # Check 3-month trend
            if len(sentiment_scores) >= 3:
                curr = sentiment_scores[0]
                prev = sentiment_scores[1]
                prev2 = sentiment_scores[2]
                
                if curr > prev and prev >= prev2:
                    score += 5
                    sentiment = "Improving (Revisions Up)"
                elif curr < prev and prev <= prev2:
                    score -= 5
                    sentiment = "Deteriorating (Revisions Down)"
            
        # 2. Earnings Estimates (If available)
        # Cal = ticker.calendar
        # This is strictly future, but if 'Earnings Average' >> EPS TTM, it's positive
        
        return score, sentiment
        
    except:
        return 0, "Unknown"
