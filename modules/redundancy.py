import pandas as pd
import numpy as np

def analyze_factor_redundancy(stock_list):
    """
    Phase 32: Factor Redundancy Check (VIF Analysis).
    Detects if multiple factors are telling the same story.
    If Correlation > 0.8, we have 'Multicollinearity' (Overfitting Risk).
    """
    print("\n" + "="*50)
    print("🧬 PHASE 32: FACTOR REDUNDANCY AUDIT")
    print("="*50)
    
    if len(stock_list) < 10:
        print("Not enough data points for Factor Analysis.")
        return

    try:
        # 1. Extract Factors into DataFrame
        data = []
        for s in stock_list:
            row = {
                "RS": s.get("RS_Rating", 0),
                "Momentum": s.get("Down_From_52W_High%", 0), # Note: This is usually inverse momentum
                "RSI": s.get("RSI", 50),
                "PEG": s.get("PEG_Ratio", 0),
                "Growth": s.get("Sales_Growth_TTM%", 0),
                "ROE": s.get("ROE%", 0),
                "F_Score": s.get("F_Score", 0),
                "Beta_Proxy": s.get("ATR", 0) / s.get("Price", 1) # Volatility
            }
            data.append(row)
            
        df = pd.DataFrame(data)
        
        # 2. Compute Correlation Matrix
        corr_matrix = df.corr()
        
        # 3. Detect Redundancy
        redundant_pairs = []
        c = corr_matrix
        visited = set()
        
        print("Factor Correlation Matrix (Key Relationships):")
        for i in range(len(c.columns)):
            for j in range(i+1, len(c.columns)):
                val = c.iloc[i, j]
                col1 = c.columns[i]
                col2 = c.columns[j]
                
                # Check for High Correlation (Positive or Negative)
                if abs(val) > 0.75:
                    redundant_pairs.append(f"{col1} <-> {col2} ({val:.2f})")
                    
        # 4. Report
        if redundant_pairs:
            print("⚠️  WARNING: REDUNDANT FACTORS DETECTED (> 0.75):")
            for pair in redundant_pairs:
                print(f"  - {pair}")
            print("  -> Implication: You are overweighting this signal.")
            print("  -> Suggestion: Prune one factor or reduce weights.")
        else:
            print("✅  Factor Independence: Healthy (No overlaps > 0.75)")
            
    except Exception as e:
        print(f"Factor Audit Error: {e}")
    print("="*50 + "\n")
