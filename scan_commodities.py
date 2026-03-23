
import sys
import os
# Add current dir to path to import screener
sys.path.append(os.getcwd())

import screener
import pandas as pd
import sqlite3
from commodity_list import COMMODITIES

def scan_commodities():
    print(f"🚀 Starting Targeted Scan for {len(COMMODITIES)} Commodities (Gold & Silver)...")
    
    results = []
    # For commodities, we just need basic technicals and trend
    market_regime = screener.analyze_market_regime()
    print(f"Market Regime: {market_regime}")
    
    for symbol in COMMODITIES:
        print(f"Analyzing {symbol}...", end="\r")
        data = asyncio.run(screener.get_stock_data(symbol))
        if data:
            # Calculate technical score
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
        print(f"{'SYMBOL':<15} {'PRICE':<10} {'SCORE':<10} {'RATING':<20}")
        print("-" * 80)
        
        for _, row in df.sort_values(by='Score', ascending=False).iterrows():
            print(f"{row['Symbol']:<15} {row['Price']:<10.2f} {row['Score']:<10.1f} {row['Rating']:<20}")
        
        print("="*80)
        
        # Save to DB (Optional: separate table or same table?)
        # For now, saving to multibaggers table so it shows on UI
        try:
            import database
            database.save_multibaggers(df)
            print(f"\n✅ Successfully saved {len(results)} commodities to database.")
        except Exception as e:
            print(f"Error saving to DB: {e}")
            
        # Also save a CSV for summary
        df.to_csv("commodity_report.csv", index=False)
        print("✅ Commodity report saved to commodity_report.csv")
    else:
        print("\nNo data fetched for any symbols.")

import asyncio
if __name__ == "__main__":
    scan_commodities()
