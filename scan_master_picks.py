
import sys
import os
# Add current dir to path to import screener
sys.path.append(os.getcwd())

import screener
import pandas as pd
import sqlite3
from master_picks import MASTER_PICKS

def scan_master_picks():
    print(f"🚀 Starting MASTER Targeted Scan for {len(MASTER_PICKS)} Consolidated Picks...")
    
    results = []
    market_regime = screener.analyze_market_regime()
    print(f"Market Regime: {market_regime}")
    
    for symbol in MASTER_PICKS:
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
            
            # --- Phase 88: Hybrid Scoring (ML) ---
            try:
                from modules.hybrid_scoring import predict_and_explain
                factors = {
                    'score': score,
                    'sales_cagr_5y': data.get("Sales_Growth_5Y%", 0),
                    'avg_roe_5y': data.get("Avg_ROE_5Y%", 0),
                    'pe_ratio': data.get("PE_Ratio", 0),
                    'debt_equity': data.get("Debt_Equity", 0),
                    'cfo_pat_ratio': data.get("CFO_PAT_Ratio", 0),
                    'market_cap_cr': data.get("Market_Cap_Cr", 0)
                }
                ml_res = predict_and_explain(factors)
                data["ML_Predicted_Return"] = ml_res.get("ml_prediction")
                
                import json
                data["SHAP_Breakdown"] = json.dumps(ml_res.get("shap_values", {}))
            except Exception as e:
                data["ML_Predicted_Return"] = None
                data["SHAP_Breakdown"] = "{}"
            
            # Trade Setup
            screener.calculate_trade_setup(data)
            
            results.append(data)
    
    if results:
        # 1.5 Phase 68: Batch VectorBT Optimization
        symbols_to_backtest = [s.get("Symbol") for s in results if s.get("Symbol")]
        if symbols_to_backtest:
            print(f"\nRunning VectorBT Optimization for {len(symbols_to_backtest)} valid stocks...")
            from backtest.engine import VectorBTEngine
            bt_engine = VectorBTEngine(period="5y")
            batch_bt_results = bt_engine.run_batch_momentum_backtest(symbols_to_backtest)
            for stock in results:
                sym = stock.get("Symbol", "")
                sym_with_ns = sym if sym.endswith('.NS') or sym.endswith('.BO') else sym + '.NS'
                bt = batch_bt_results.get(sym_with_ns, batch_bt_results.get(sym, {}))
                
                stock["Backtest_CAGR"] = bt.get("cagr", 0.0)
                stock["Backtest_Win_Rate"] = bt.get("win_rate", 0.0)
                stock["Backtest_Max_DD"] = bt.get("max_drawdown", 0.0)
                stock["Backtest_Sharpe"] = bt.get("sharpe_ratio", 0.0)

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
        df.to_csv("master_picks_report.csv", index=False)
        print("✅ Consolidated report saved to master_picks_report.csv")
    else:
        print("\nNo data fetched for any symbols.")

if __name__ == "__main__":
    scan_master_picks()
