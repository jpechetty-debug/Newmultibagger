
import sys
import os
# Add current dir to path to import screener
sys.path.append(os.getcwd())

import screener
import pandas as pd
import sqlite3

def scan_picks():
    picks = ["COALINDIA.NS", "ONGC.NS", "POWERGRID.NS", "HEROMOTOCO.NS", "RECLTD.NS", "PFC.NS"]
    print(f"Direct Verification of {len(picks)} picks...")
    
    results = []
    market_regime = screener.analyze_market_regime()
    
    for symbol in picks:
        print(f"Analyzing {symbol}...")
        data = screener.get_stock_data(symbol)
        if data:
            score_data = screener.calculate_institutional_score(data, market_regime=market_regime)
            data['score'] = score_data['total_score']
            data['factor_penalties'] = score_data.get('factor_penalties', [])
            results.append(data)
    
    if results:
        df = pd.DataFrame(results)
        print("\n--- RESULTS ---")
        
        # Calculate scores and trade setup
        processed_results = []
        for _, row in df.iterrows():
            data = row.to_dict()
            # Score is already in 'score' from calculate_institutional_score
            # Let's normalize it to 'Score' if needed, but calculate_institutional_score returns total_score
            # In scan_picks, data['score'] = score_data['total_score']
            data['Score'] = data.pop('score')
            
            # Map rating
            score = data['Score']
            if score >= 80: data["Rating"] = "Strong Buy (Elite)"
            elif score >= 65: data["Rating"] = "Buy"
            elif score >= 50: data["Rating"] = "Hold"
            else: data["Rating"] = "Avoid"
            
            # Trade Setup
            screener.calculate_trade_setup(data)
            processed_results.append(data)
            
        df_final = pd.DataFrame(processed_results)
        cols_display = ['Symbol', 'PE_Ratio', 'Avg_ROE_5Y%', 'Score', 'Value_Gap%']
        print(df_final[cols_display].to_string(index=False))
        
        # Save to DB immediately for the user to see in UI
        try:
            import database
            database.save_multibaggers(df_final)
            print("\n✅ Successfully saved to 'multibaggers' table via database.py.")
        except Exception as e:
            print(f"Error saving to DB: {e}")
            
if __name__ == "__main__":
    scan_picks()
