
import sqlite3
import pandas as pd

def run_thesis_check():
    print("🚦 Initiating Advanced Thesis Break Engine (Phase 54)...")
    
    try:
        conn = sqlite3.connect('stocks.db')
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    # Select Active Portfolio (Momentum: Top 20 by RS)
    if 'rs_rating' in df.columns:
        df['rs_rating'] = pd.to_numeric(df['rs_rating'], errors='coerce').fillna(0)
    
    portfolio = df.sort_values(by='rs_rating', ascending=False).head(20).copy()
    
    if portfolio.empty:
        print("⚠️ Portfolio Empty.")
        return
        
    print(f"🧐 Auditing {len(portfolio)} positions for Thesis Breaks...")
    
    sell_signals = []
    
    # Define SELL Rules
    # 1. Momentum Break: RS Rating < 50 (Lost Leadership)
    # 2. Fundamental Break: Sales Growth < 0 (Turnaround Failed) -> If available
    # 3. Technical Break: Price < Stop Loss (Risk Hit)
    
    for _, row in portfolio.iterrows():
        reasons = []
        
        # Rule 1
        # RS Rating in DB is a RATIO (Stock Ret / Nifty Ret).
        # > 1.0 = Outperformance. < 1.0 = Underperformance.
        # Sell if RS < 0.8 (Lagging significantly)
        if row['rs_rating'] < 0.8:
            reasons.append(f"Momentum Lost (RS Ratio {row['rs_rating']:.2f} < 0.8)")
            
        # Rule 2
        # Check sales growth column exists
        if 'sales_cagr_5y' in row and pd.to_numeric(row['sales_cagr_5y'], errors='coerce') < 0:
             reasons.append(f"Growth Failed (Sales CAGR {row['sales_cagr_5y']}% < 0)")
             
        # Rule 3
        # Assuming 'stop_loss' and 'price' columns exist
        if 'stop_loss' in row and 'price' in row:
             sl = pd.to_numeric(row['stop_loss'], errors='coerce') 
             p = pd.to_numeric(row['price'], errors='coerce')
             if p < sl and sl > 0:
                 reasons.append(f"Stop Loss Hit ({p} < {sl})")
                 
        if reasons:
            sell_signals.append({
                "Symbol": row['symbol'],
                "Price": row.get('price', 0),
                "Reasons": ", ".join(reasons),
                "Action": "SELL"
            })
            
    # Save Report
    with open("sell_report.md", "w", encoding="utf-8") as f:
        f.write("# 🚦 Phase 54: Thesis Break Report\n\n")
        
        if sell_signals:
            df_sell = pd.DataFrame(sell_signals)
            f.write(f"## ❌ Sell Signals Detected: {len(sell_signals)}\n")
            f.write(df_sell.to_markdown(index=False))
            f.write("\n\n**Action Required**: Execute exits immediately to preserve capital.")
            print(f"⚠️ FOUND {len(sell_signals)} THESIS BREAKS!")
            print(df_sell[['Symbol', 'Reasons']].to_string(index=False))
        else:
            f.write("## ✅ Portfolio Healthy\n")
            f.write("No Thesis Breaks detected. All positions meet retention criteria.\n")
            print("✅ All positions are healthy.")

    print("\n📄 Report saved to sell_report.md")
    
    # Save to JSON for API
    import json
    json_output = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "signals_count": len(sell_signals),
        "status": "HEALTHY" if not sell_signals else "ACTION_REQUIRED",
        "signals": sell_signals
    }
    with open("thesis_break.json", "w") as f:
        json.dump(json_output, f, indent=4)
        
    print("📄 Signals saved to thesis_break.json")

if __name__ == "__main__":
    run_thesis_check()
