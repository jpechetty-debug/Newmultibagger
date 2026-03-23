
import sqlite3
import pandas as pd
import numpy as np
from statsmodels.stats.outliers_influence import variance_inflation_factor

def analyze_vif():
    print("🔬 Initiating Factor Redundancy Analysis (Phase 48)...")
    
    # 1. Load Data
    try:
        conn = sqlite3.connect('stocks.db')
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    print(f"📊 Analyzing Factors for {len(df)} stocks")

    # 2. Select Numerical Factors for Analysis
    # We want to check if any of these are saying the same thing
    factors = [
        'roe', 'avg_roe_5y',      # Quality
        'sales_growth', 'sales_cagr_5y', # Growth
        'pe_ratio', 'peg_ratio',  # Value
        'rsi', 'rs_rating',       # Momentum
        'f_score',                # Fundamental Health
        'atr',                    # Volatility
        'cfo_pat_ratio',          # Earnings Quality
        'promoter_holding'        # Ownership
    ]
    
    # 3. Preprocessing
    # Ensure columns exist and handle NaNs
    valid_factors = []
    for f in factors:
        if f in df.columns:
            df[f] = pd.to_numeric(df[f], errors='coerce').fillna(0)
            valid_factors.append(f)
        else:
            print(f"⚠️ Warning: Factor '{f}' not found in DB")

    if not valid_factors:
        print("❌ No valid factors found.")
        return

    # Filter out infinity/excessive outliers for stability
    data = df[valid_factors].copy()
    data = data.replace([np.inf, -np.inf], 0)
    
    # Normalize features (StandardScaler logic mostly implied by VIF but good to be clean)
    # VIF requires a constant term for intercept if using OLS logic, 
    # but strictly checking multicollinearity among vars doesn't inherently demand it if we just look at X
    # Standard implementation:
    
    print("\n🧮 Calculating Variance Inflation Factor (VIF)...")
    
    # VIF Calculation
    vif_data = pd.DataFrame()
    vif_data["Factor"] = valid_factors
    
    # Handling Singular Matrix (All zeros)
    # Filter out columns with 0 variance
    clean_factors = [col for col in data.columns if data[col].std() > 0]
    data = data[clean_factors]
    vif_data = pd.DataFrame()
    vif_data["Factor"] = clean_factors
    
    try:
        vif_data["VIF"] = [variance_inflation_factor(data.values, i) 
                           for i in range(len(data.columns))]
    except Exception as e:
        print(f"❌ VIF Calculation Error: {e}")
        return

    # Sort by VIF
    vif_data = vif_data.sort_values(by="VIF", ascending=False)
    
    print("-" * 50)
    print("FACTOR REDUNDANCY REPORT")
    print("-" * 50)
    print(vif_data.to_string(index=False))
    print("-" * 50)
    
    # 4. Correlation Matrix (for detailed pairwise check)
    corr_matrix = data.corr()
    
    print("\n🔗 Key Correlations (> 0.7):")
    high_corr_pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i):
            if abs(corr_matrix.iloc[i, j]) > 0.7:
                pair = f"{corr_matrix.columns[i]} vs {corr_matrix.columns[j]}"
                val = corr_matrix.iloc[i, j]
                print(f"  • {pair}: {val:.2f}")
                high_corr_pairs.append((pair, val))

    # 5. Interpretation
    print("\n📢 ANALYSIS:")
    high_vif = vif_data[vif_data["VIF"] > 5]
    if not high_vif.empty:
        print(f"⚠️ Found {len(high_vif)} factors with High Multicollinearity (VIF > 5).")
        print("   Consider removing or merging these to reduce noise.")
    else:
        print("✅ All factors provide unique information (VIF < 5). System is efficient.")

    # Save Report
    with open("vif_report.md", "w", encoding="utf-8") as f:
        f.write("# 🔬 Phase 48: Factor Redundancy (VIF) Report\n\n")
        f.write("## Variance Inflation Factor (VIF) Scores\n")
        f.write("*VIF > 5 indicates potential redundancy.*\n\n")
        f.write(vif_data.to_markdown(index=False))
        f.write("\n\n## High Correlation Pairs (> 0.7)\n")
        if high_corr_pairs:
            for p, v in high_corr_pairs:
                f.write(f"- **{p}**: {v:.2f}\n")
        else:
            f.write("None found.\n")
            
    print("\n📄 Report saved to vif_report.md")

if __name__ == "__main__":
    analyze_vif()
