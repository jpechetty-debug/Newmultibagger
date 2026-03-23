
import sys
import os
# Add current dir to path to import screener
sys.path.append(os.getcwd())

import screener
import pandas as pd
import sqlite3
from user_picks_v5 import USER_PICKS_V5

def scan_user_picks_v5():
    print(f"🚀 Starting Targeted Scan for {len(USER_PICKS_V5)} Top Conviction Ideas (Batch 5)...")
    
    results = []
    market_regime = screener.analyze_market_regime()
    print(f"Market Regime: {market_regime}")
    
    for symbol in USER_PICKS_V5:
        print(f"Analyzing {symbol}...", end="\r")
        data = screener.get_stock_data(symbol)
        if data:
            # Calculate institutional score
            score_data = screener.calculate_institutional_score(data, market_regime=market_regime)
            data['Score'] = score_data['total_score']
            
            # Map rating
            score = data['Score']
            if score >= 80: data["Rating"] = "Strong Buy (Elite)"
            elif score >= 65: data["Rating"] = "Buy"
            elif score >= 50: data["Rating"] = "Hold"
            else: data["Rating"] = "Avoid"
            
            # Trade Setup
            screener.calculate_trade_setup(data)
            
            results.append(data)
    
    if results:
        df = pd.DataFrame(results)
        print("\n\n" + "="*80)
        print(f"{'SYMBOL':<15} {'PRICE':<10} {'ROE%':<10} {'SCORE':<10} {'RATING':<20}")
        print("-" * 80)
        
        for _, row in df.sort_values(by='Score', ascending=False).iterrows():
            print(f"{row['Symbol']:<15} {row['Price']:<10.2f} {row['Avg_ROE_5Y%']:<10.1f} {row['Score']:<10.1f} {row['Rating']:<20}")
        
        print("="*80)
        
        # Save to DB
        try:
            import database
            database.save_multibaggers(df)
            print(f"\n✅ Successfully saved {len(results)} stocks to database (multibaggers table).")
        except Exception as e:
            print(f"Error saving to DB: {e}")
            
        # Also save a CSV for summary
        df.to_csv("user_picks_v5_report.csv", index=False)
        print("✅ Report saved to user_picks_v5_report.csv")
    else:
        print("\nNo data fetched for any symbols.")

if __name__ == "__main__":
    scan_user_picks_v5()
