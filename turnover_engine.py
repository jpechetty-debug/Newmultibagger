
import sqlite3
import pandas as pd
import numpy as np

def run_turnover_analysis():
    print("🔄 Initiating Turnover & Tax Efficiency Analysis (Phase 51)...")
    
    # 1. Load Data
    try:
        conn = sqlite3.connect('stocks.db')
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    # 2. Logic: Compare T-12 Portfolio vs T-0 Portfolio
    # Strategy: Momentum (High RS) - Identified as winner in Phase 49
    
    # Normalize Data
    if 'rs_rating' in df.columns:
        df['rs_rating'] = pd.to_numeric(df['rs_rating'], errors='coerce').fillna(0)
    # We need a metric for T-12. 
    # RS Rating is dynamic (Price based). 
    # Assumption for Simulation: verify overlap using 'sales_cagr_5y' and 'avg_roe_5y' (Fundamental Quality) 
    # vs 'rs_rating' (Price Momentum). 
    # Momentum strategies naturally have HIGH turnover (Rotate into winners).
    # Quality strategies have LOW turnover.
    
    # Let's Simulate Momentum Turnover
    # Since we don't have historical RS ratings, we simulate:
    # "New Winners" vs "Old Winners". 
    # Proxy: Stocks with High RS TODAY (T-0) vs Stocks with High RS 1 Year Ago? Impossible to know without history.
    
    # Better Proxy for Phase 51:
    # Use the "Win Rate" from Phase 47/49 to estimate holding period.
    # Momentum portfolios typically hold winners for 6-9 months (Trend).
    # Expected Turnover ~ 150-200% per year for aggressive Momentum.
    
    # Alternative: Compare "Quality" Portfolio (T-12) vs "Momentum" Portfolio (Now).
    # If they are totally different, it means we rotated from Quality to Momentum? No.
    
    # Let's use the FUNDAMENTAL Proxy method used in Phase 47.
    # Portfolio T-12: High Sales/ROE (The "Quality" list we backtested).
    # Portfolio T-0: High RS Rating (The "Momentum" list we selected today).
    
    # If our strategy shifts to "Momentum Regime", we sell Quality and buy Momentum.
    # Calculating Overlap between 'Quality Compounders' and 'High Momentum'.
    
    print("📊 Comparing Strategy Overlap...")
    
    # Portfolio A (Fundamental/Quality - Stable)
    if 'sales_cagr_5y' in df.columns and 'avg_roe_5y' in df.columns:
         df['sales_cagr_5y'] = pd.to_numeric(df['sales_cagr_5y'], errors='coerce').fillna(0)
         df['avg_roe_5y'] = pd.to_numeric(df['avg_roe_5y'], errors='coerce').fillna(0)
         
    port_fundamental = df[
        (df['sales_cagr_5y'] > 10) & (df['avg_roe_5y'] > 15)
    ].sort_values('avg_roe_5y', ascending=False).head(20)['symbol'].tolist()
    
    # Portfolio B (Momentum - Dynamic)
    port_momentum = df.sort_values('rs_rating', ascending=False).head(20)['symbol'].tolist()
    
    # Overlap
    common = set(port_fundamental).intersection(set(port_momentum))
    overlap_pct = (len(common) / 20) * 100
    churn_estimated = 100 - overlap_pct
    
    print(f"🔸 Fundamental Portfolio (Low Churn proxy): {len(port_fundamental)}")
    print(f"🔹 Momentum Portfolio (High Churn proxy): {len(port_momentum)}")
    print(f"🤝 Overlap: {len(common)} stocks ({overlap_pct}%)")
    print(f"🔄 Estimated Regime Churn: {churn_estimated}%")
    
    if common:
         print(f"   Stocks in Both: {', '.join(common)}")
         
    # 3. Tax Calculation
    # Assumption based on Churn:
    # If High Churn (>50%), we trigger STCG.
    # If Low Churn (<20%), we trigger LTCG.
    
    gross_return = 102.13 # From Phase 50
    net_return_slippage = 100.59 # From Phase 50
    portfolio_value = 1000000 # 10L Base
    
    profit_pre_tax = portfolio_value * (net_return_slippage / 100)
    
    print("\n🧾 TAX EFFICIENCY AUDIT")
    if churn_estimated > 50:
        tax_rate = 0.20 # 20% STCG
        tax_type = "Short Term Capital Gains (STCG)"
        print(f"   Scenario: High Turnover ({churn_estimated}%). Active Trading.")
    else:
        tax_rate = 0.125 # 12.5% LTCG
        tax_type = "Long Term Capital Gains (LTCG)"
        print(f"   Scenario: Buy & Hold ({churn_estimated}% churn). Passive Investing.")
        
    tax_liability = profit_pre_tax * tax_rate
    profit_post_tax = profit_pre_tax - tax_liability
    post_tax_return = (profit_post_tax / portfolio_value) * 100
    
    tax_drag_pct = net_return_slippage - post_tax_return
    
    print("-" * 50)
    print(f"Strategy: Momentum (High RS)")
    print("-" * 50)
    print(f"Net Return (Pre-Tax):  {net_return_slippage:.2f}%")
    print(f"Tax Rate Applied:      {tax_rate*100}% ({tax_type})")
    print(f"Tax Liability:         ₹{tax_liability:,.0f} (on 10L Capital)")
    print(f"Post-Tax Return:       {post_tax_return:.2f}%")
    print(f"🔻 Tax Drag:           {tax_drag_pct:.2f}%")
    print("-" * 50)
    
    efficiency_score = (post_tax_return / gross_return) * 100
    print(f"💡 Efficiency Score: {efficiency_score:.1f}/100")
    
    if efficiency_score < 70:
        print("⚠️ WARNING: Tax is eating >30% of your profits. Consider holding longer.")
    else:
        print("✅ Tax Efficiency is Acceptable.")

    # Save Report
    with open("tax_report.md", "w", encoding="utf-8") as f:
        f.write("# 🔄 Phase 51: Turnover & Tax Efficiency Report\n\n")
        f.write("## Churn Analysis\n")
        f.write(f"- **Estimated Churn**: {churn_estimated}%\n")
        f.write(f"- **Overlap (Quality vs Momentum)**: {overlap_pct}%\n\n")
        f.write("## Tax Impact (Pro Forma)\n")
        f.write(f"- **Net Return (Pre-Tax)**: {net_return_slippage:.2f}%\n")
        f.write(f"- **Tax Efficiency**: **{post_tax_return:.2f}%** (Post-Tax)\n")
        f.write(f"- **Tax Drag**: {tax_drag_pct:.2f}%\n")
        f.write(f"- **Regime**: {tax_type}\n\n")
        f.write("## Stocks in 'Sweet Spot' (Momentum + Quality)\n")
        if common:
             f.write(f"{', '.join(common)}\n")
        else:
             f.write("No overlap found. Pure Momentum play.\n")

    print("\n📄 Report saved to tax_report.md")

if __name__ == "__main__":
    run_turnover_analysis()
