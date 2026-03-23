
import sys
import os
import pandas as pd
import asyncio

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import screener
import database

STOCKS = [
    "INDIGOPNTS.NS",
    "INOXWIND.NS",
    "IGL.NS",
    "GALAXYSURF.NS",
    "TIMETECHNO.NS",
    "CELLO.NS",
    "SIEMENS.NS",
    "ASTRAMICRO.NS",
    "BECTORFOOD.NS",
    "PETRONET.NS"
]

def scan_watchlist():
    print(f"🚀 Scanning {len(STOCKS)} High Conviction Stocks...")
    
    results = []
    
    # Get Market Regime once
    market_regime = screener.analyze_market_regime()
    print(f"Market Regime: {market_regime}")

    for symbol in STOCKS:
        print(f"Analyzing {symbol}...", end=" ")
        try:
            # 1. Get Data
            data = screener.get_stock_data(symbol)
            
            if data:
                # 2. Score
                score_data = screener.calculate_institutional_score(data, market_regime=market_regime)
                data['Score'] = score_data['total_score']
                
                # 3. Rate
                score = data['Score']
                if score >= 80: data["Rating"] = "Strong Buy (Elite)"
                elif score >= 65: data["Rating"] = "Buy"
                elif score >= 50: data["Rating"] = "Hold"
                else: data["Rating"] = "Avoid"
                
                # 4. Setup
                screener.calculate_trade_setup(data)
                
                results.append(data)
                print(f"✅ Score: {score}")
            else:
                print(f"❌ No Data")
                
        except Exception as e:
             print(f"❌ Error: {e}")

    if results:
        df = pd.DataFrame(results)
        print("\n--- Results Summary ---")
        print(df[['Symbol', 'Price', 'Score', 'Rating', 'Target_1']])
        
        # Save to DB
        try:
            database.save_multibaggers(df)
            print("\n✅ Successfully updated database with High Conviction Watchlist.")
        except Exception as e:
            print(f"\n❌ Database Save Error: {e}")
            
    else:
        print("\n❌ No valid results found.")

if __name__ == "__main__":
    scan_watchlist()
