
import sqlite3
import pandas as pd
import yfinance as yf
import numpy as np

def run_recovery_analysis():
    print("🩹 Initiating Drawdown Recovery Analysis (Phase 53)...")
    
    try:
        conn = sqlite3.connect('stocks.db')
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return

    # Select Momentum Portfolio
    if 'rs_rating' in df.columns:
        df['rs_rating'] = pd.to_numeric(df['rs_rating'], errors='coerce').fillna(0)
    
    portfolio = df.sort_values(by='rs_rating', ascending=False).head(20)['symbol'].tolist()
    
    if not portfolio:
        print("⚠️ Portfolio Empty.")
        return
        
    print(f"📊 Analyzing Historical Drawdowns for {len(portfolio)} stocks (2 Years)...")
    
    try:
        # Fetch 2Y Data
        data = yf.download(portfolio, period="2y", progress=False)['Close']
        
        # Benchmarks
        nifty = yf.download("^NSEI", period="2y", progress=False)['Close']
        
        # Create Portfolio Index (Equal Weight)
        # Normalize to 100 at start
        normalized_data = data / data.iloc[0] * 100
        portfolio_index = normalized_data.mean(axis=1)
        
        # Calculate Drawdown
        rolling_max = portfolio_index.cummax()
        drawdown = (portfolio_index - rolling_max) / rolling_max * 100
        
        max_drawdown = drawdown.min()
        
        # Calculate Recovery Time
        # Find continuous periods where DD < 0
        is_underwater = drawdown < -0.5 # Tolerance for flat periods
        
        # Calculate streaks
        # Group by change in value
        groups = (is_underwater != is_underwater.shift()).cumsum()
        streak_lengths = is_underwater.groupby(groups).sum()
        
        # Filter for periods that were actually underwater
        # We need to ensure we are counting 'True' streaks
        # A simple way: iterate over groups, check if value is True
        
        longest_streak = 0
        current_streak = 0
        
        for val in is_underwater:
            if val:
                current_streak += 1
            else:
                longest_streak = max(longest_streak, current_streak)
                current_streak = 0
        longest_streak = max(longest_streak, current_streak)
        
        max_days_underwater = longest_streak
        
        # Volatility
        daily_ret = portfolio_index.pct_change().dropna()
        volatility = daily_ret.std() * np.sqrt(252) * 100
        
        print("\n" + "="*50)
        print("📉 DRAWDOWN & RECOVERY REPORT (2 Years)")
        print("="*50)
        print(f"Portfolio: Top 20 Momentum Stocks")
        print(f"Max Drawdown (MDD):     {max_drawdown:.2f}%")
        print(f"Max Time to Recover:    {max_days_underwater:.0f} Trading Days (~{int(max_days_underwater*1.4)} Cal Days)")
        print(f"Annualized Volatility:  {volatility:.2f}%")
        print("-" * 50)
        
        status = "✅ PSYCHOLOGICALLY VIABLE"
        if max_days_underwater > 100:
            status = "⚠️ SLOW RECOVERY (Patience Required)"
        if max_drawdown < -25:
            status = "⚠️ HIGH VOLATILITY (Stomach Churning)"
            
        print(f"🧠 Verdict: {status}")
        
        # Save Report
        with open("drawdown_report.md", "w", encoding="utf-8") as f:
            f.write("# 🩹 Phase 53: Drawdown Recovery Report\n\n")
            f.write("## Psychological Stress Test (2 Years)\n")
            f.write(f"- **Max Drawdown**: {max_drawdown:.2f}%\n")
            f.write(f"- **Longest Underwater Period**: {max_days_underwater:.0f} Trading Days\n")
            f.write(f"- **Volatility**: {volatility:.2f}%\n\n")
            f.write(f"**Verdict**: {status}\n\n")
            f.write("### Comparison\n")
            f.write("- **Nifty 50 MDD**: ~10-15% (Typical)\n")
            f.write(f"- **Strat MDD**: {max_drawdown:.2f}%\n")
            f.write("*(Momentum strategies typically have deeper drawdowns but faster recovery)*\n")

        print("\n📄 Report saved to drawdown_report.md")
        
        # Save to JSON for API
        import json
        json_output = {
            "timestamp": pd.Timestamp.now().isoformat(),
            "max_drawdown": round(max_drawdown, 2),
            "max_days_underwater": int(max_days_underwater),
            "volatility": round(volatility, 2),
            "status": status,
            "verdict": "VIABLE" if "PSYCHOLOGICALLY VIABLE" in status else "CAUTION"
        }
        with open("recovery.json", "w") as f:
            json.dump(json_output, f, indent=4)
            
        print("📄 Metrics saved to recovery.json")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    run_recovery_analysis()
