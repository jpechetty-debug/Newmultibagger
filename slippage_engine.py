
import sqlite3
import pandas as pd
import yfinance as yf
import numpy as np

def run_slippage_analysis():
    print("📉 Initiating Real-World Slippage Modeling (Phase 50)...")
    
    # 1. Load Data
    try:
        conn = sqlite3.connect('stocks.db')
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    # 2. Select the Winning Strategy (Momentum)
    # Phase 49 showed Momentum (RS Rating) as the winner.
    print("📊 Loading Momentum Portfolio (High RS Rating)...")
    
    if 'rs_rating' in df.columns:
        df['rs_rating'] = pd.to_numeric(df['rs_rating'], errors='coerce').fillna(0)
        
    portfolio = df[df['rs_rating'] > 0].sort_values(by='rs_rating', ascending=False).head(20).copy()
    
    if portfolio.empty:
        print("⚠️ No stocks found.")
        return

    # 3. Define Logic
    # Market Cap Logic: We need Market Cap to assign slippage tiers.
    # DB has 'market_cap_cr' column?
    if 'market_cap_cr' in df.columns:
         portfolio['market_cap_cr'] = pd.to_numeric(portfolio['market_cap_cr'], errors='coerce').fillna(0)
    else:
        # Fetch Market Cap if missing (Critical for this phase)
        print("⏳ Fetching Market Caps...")
        caps = []
        for sym in portfolio['symbol']:
            try:
                t = yf.Ticker(sym)
                info = t.info
                mc = info.get('marketCap', 0) / 10000000 # Convert to Crores
                caps.append(mc)
            except:
                caps.append(0)
        portfolio['market_cap_cr'] = caps

    # 4. Calculate Net Returns
    # Fetch 1Y Gross Return
    print("⏳ Fetching Real-Time Returns...")
    tickers = portfolio['symbol'].tolist()
    data = yf.download(tickers, period="1y", progress=False)['Close']
    
    if isinstance(data, pd.Series):
        data = data.to_frame()
        
    gross_returns = []
    slippages = []
    txn_costs = 0.2 # 0.1% Entry + 0.1% Exit (Brokerage + STT)
    
    for _, row in portfolio.iterrows():
        sym = row['symbol']
        mc = row['market_cap_cr']
        
        # Slippage Tier
        if mc > 50000:       # Large Cap
            slip = 0.2
        elif mc > 15000:     # Mid Cap
            slip = 0.5
        elif mc > 5000:      # Small Cap
            slip = 1.0
        else:                # Micro Cap
            slip = 2.0       # High Impact Cost
            
        slippages.append(slip)
        
        # Gross Return
        if sym in data.columns:
            prices = data[sym].dropna()
            if len(prices) > 200:
                ret = ((prices.iloc[-1] - prices.iloc[0]) / prices.iloc[0]) * 100
            else:
                ret = 0
        else:
            ret = 0
        gross_returns.append(ret)

    portfolio['gross_return'] = gross_returns
    portfolio['slippage_pct'] = slippages
    
    # Net Return Formula:
    # Net = Gross - (Slippage_Entry + Slippage_Exit) - Txn_Costs
    portfolio['net_return'] = portfolio['gross_return'] - (portfolio['slippage_pct'] * 2) - txn_costs
    
    # 5. Analysis
    avg_gross = portfolio['gross_return'].mean()
    avg_net = portfolio['net_return'].mean()
    avg_slippage = portfolio['slippage_pct'].mean()
    
    drag = avg_gross - avg_net
    
    print("-" * 50)
    print("📉 SLIPPAGE IMPACT REPORT")
    print("-" * 50)
    print(f"Strategy: Momentum (Top 20)")
    print(f"Arg. Market Cap:    ₹{portfolio['market_cap_cr'].mean():,.0f} Cr")
    print(f"Gross Return (1Y):  {avg_gross:.2f}%")
    print(f"Net Return (1Y):    {avg_net:.2f}%")
    print(f"🔻 Total Drag:      {drag:.2f}% (Slippage + Tax)")
    print("-" * 50)
    
    print("\n⚠️ High Impact Stocks (Microcaps):")
    microcaps = portfolio[portfolio['slippage_pct'] >= 2.0]
    if not microcaps.empty:
        print(microcaps[['symbol', 'market_cap_cr', 'gross_return', 'net_return']].to_string(index=False))
    else:
        print("None found in Top 20.")

    # Save Output
    with open("slippage_report.md", "w", encoding="utf-8") as f:
        f.write("# 📉 Phase 50: Real-World Slippage Report\n\n")
        f.write("## Impact Analysis (Momentum Portfolio)\n")
        f.write(f"- **Gross Return**: {avg_gross:.2f}%\n")
        f.write(f"- **Net Return**: **{avg_net:.2f}%**\n")
        f.write(f"- **Performance Drag**: {drag:.2f}%\n\n")
        f.write("### Portfolio Detail\n")
        f.write(portfolio[['symbol', 'market_cap_cr', 'slippage_pct', 'gross_return', 'net_return']].to_markdown(index=False))
        
    print("\n📄 Report saved to slippage_report.md")

if __name__ == "__main__":
    run_slippage_analysis()
