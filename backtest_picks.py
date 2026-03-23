import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def backtest_picks():
    # Load the Top 5 Picks from the CSV we just generated
    try:
        picks_df = pd.read_csv("screener_results.csv")
        symbols = picks_df["Symbol"].tolist()
    except FileNotFoundError:
        print("screener_results.csv not found. Using default list.")
        symbols = ["DATAPATTNS.NS", "PRICOLLTD.NS", "BSE.NS", "SANGHVIMOV.NS", "SARDAEN.NS"]

    print(f"Backtesting Portfolio: {symbols}")
    
    # Add Benchmark
    benchmark_symbol = "^NSEI" # Nifty 50
    all_symbols = symbols + [benchmark_symbol]
    
    # Fetch Data (1 Year)
    print("Fetching historical data (1 Year)...")
    # auto_adjust=True is new default, so 'Adj Close' might not exist or be just 'Close'
    data = yf.download(all_symbols, period="1y", progress=False, auto_adjust=False)["Adj Close"]
    
    if data.empty:
        print("No data fetched.")
        return

    # Normalize to 100 base
    normalized = (data / data.iloc[0]) * 100
    
    # Calculate Individual Returns
    final_returns = {}
    for sym in symbols:
        if sym in data.columns:
            ret = ((data[sym].iloc[-1] - data[sym].iloc[0]) / data[sym].iloc[0]) * 100
            final_returns[sym] = ret

    # Calculate Portfolio Curve (Equal Weighted)
    # We take the mean of the normalized curves of our stocks
    portfolio_curve = normalized[symbols].mean(axis=1)
    
    # Benchmark Curve
    benchmark_curve = normalized[benchmark_symbol]
    
    # Metrics
    port_return = portfolio_curve.iloc[-1] - 100
    bench_return = benchmark_curve.iloc[-1] - 100
    
    # Drawdown
    rolling_max = portfolio_curve.cummax()
    drawdown = (portfolio_curve - rolling_max) / rolling_max * 100
    max_drawdown = drawdown.min()

    print("\n--- BACKTEST RESULTS (Last 1 Year) ---")
    print(f"Portfolio Return:   {port_return:.2f}%")
    print(f"Benchmark (Nifty):  {bench_return:.2f}%")
    print(f"Alpha (Excess Ret): {port_return - bench_return:.2f}%")
    print(f"Max Drawdown:       {max_drawdown:.2f}%")
    
    print("\n--- INDIVIDUAL WINNERS ---")
    sorted_ret = sorted(final_returns.items(), key=lambda x: x[1], reverse=True)
    for sym, r in sorted_ret:
        print(f"{sym:<15}: {r:.1f}%")
        
    # Plotting (Optional text output for now)
    # plt.plot(portfolio_curve, label='Top 5 Portfolio')
    # plt.plot(benchmark_curve, label='Nifty 50')
    # plt.legend()
    # plt.show()

if __name__ == "__main__":
    backtest_picks()
