
import yfinance as yf
import pandas as pd

candidates = ["ITDCEM.NS", "HBLPOWER.NS", "REC.NS", "TATAMOTORS.NS"]

print(f"Verifying {len(candidates)} candidates deeply...")

valid = []
delisted = []

for sym in candidates:
    print(f"\nChecking {sym}...")
    try:
        t = yf.Ticker(sym)
        
        # 1. History
        hist = t.history(period="1mo")
        if not hist.empty:
            print(f"  ✅ History found: {len(hist)} days. Last close: {hist['Close'].iloc[-1]}")
            valid.append(sym)
            continue
            
        # 2. Info
        info = t.info
        if info and 'currentPrice' in info:
            print(f"  ✅ Info found: Price {info['currentPrice']}")
            valid.append(sym)
            continue
            
        print("  ❌ No history or info found.")
        delisted.append(sym)
        
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        delisted.append(sym)

print("\n--- Verdict ---")
print(f"Valid: {valid}")
print(f"Delisted: {delisted}")
