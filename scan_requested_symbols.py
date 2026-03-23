import sys
import os
import pandas as pd
import sqlite3
import screener

def scan_specific_symbols():
    symbols = ["CHENNPETRO.NS", "PFC.NS", "MSUMI.NS", "SHRIPISTON.NS"]
    print(f"🚀 Scanning {len(symbols)} specific symbols with correct mapping...")
    
    results = []
    market_regime = screener.analyze_market_regime()
    
    for symbol in symbols:
        print(f"Analyzing {symbol}...")
        data = screener.get_stock_data(symbol)
        if data:
            score_data = screener.calculate_institutional_score(data, market_regime=market_regime)
            data['Score'] = score_data['total_score']
            
            # Add Rating
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
        print("\nResults:")
        print(df[['Symbol', 'Price', 'Score', 'Rating']])
        
        # Save to DB
        import database
        database.save_multibaggers(df)
        print("\n✅ Saved to database.")
    else:
        print("No results found.")

if __name__ == "__main__":
    scan_specific_symbols()
