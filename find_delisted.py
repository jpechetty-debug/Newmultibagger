
import yfinance as yf
from ticker_list import TICKERS
import pandas as pd
import time


import yfinance as yf
from ticker_list import TICKERS
import pandas as pd
import time
import os

def check_symbol(symbol):
    """Deep check for a single symbol."""
    try:
        t = yf.Ticker(symbol)
        # 1. Try fetching history
        hist = t.history(period="5d")
        if not hist.empty:
            return True # Valid
            
        # 2. If history empty, check info
        # Note: Delisted stocks often have empty info or 'quoteType': 'NONE'
        info = t.info
        if info and 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
            return True # Valid
            
        return False # Likely Delisted
    except Exception as e:
        print(f"Error checking {symbol}: {e}")
        return False

def find_delisted():
    print(f"Scanning {len(TICKERS)} tickers for delisted status...")
    delisted_candidates = []
    
    # Check in smaller chunks
    chunk_size = 20
    for i in range(0, len(TICKERS), chunk_size):
        chunk = TICKERS[i:i+chunk_size]
        print(f"Checking batch {i} to {i+len(chunk)}...")
        
        try:
            # Batch download first (fastest)
            data = yf.download(chunk, period="5d", progress=False)
            
            if data.empty:
                # If entire batch fails, check individually
                for sym in chunk:
                    if not check_symbol(sym):
                        print(f"  -> FOUND DELISTED: {sym}")
                        delisted_candidates.append(sym)
                continue

            # Check individual columns in the batch data
            if "Close" in data:
                # Handle single ticker case (Series) vs multiple (DataFrame)
                close_cols = data["Close"]
                for sym in chunk:
                    is_suspect = False
                    if isinstance(close_cols, pd.Series):
                         # If only 1 ticker in chunk was requested/returned
                         if close_cols.name == sym:
                             if close_cols.isna().all(): is_suspect = True
                         else:
                             # Should not happen unless yfinance maps differently
                             pass
                    else:
                        if sym not in close_cols.columns:
                            is_suspect = True
                        elif close_cols[sym].isna().all():
                            is_suspect = True
                    
                    if is_suspect:
                        # Double check individually
                        if not check_symbol(sym):
                            print(f"  -> FOUND DELISTED: {sym}")
                            delisted_candidates.append(sym)
                            
        except Exception as e:
            print(f"Batch Error: {e}")
            # Fallback to individual check
            for sym in chunk:
                if not check_symbol(sym):
                    delisted_candidates.append(sym)
        
        # Slight pause to be nice to API
        time.sleep(0.5)

    print("\n--- SUMMARY ---")
    print(f"Found {len(delisted_candidates)} potentially delisted stocks.")
    
    with open("delisted_candidates.txt", "w") as f:
        for sym in delisted_candidates:
            f.write(f"{sym}\n")
    print("Saved to delisted_candidates.txt")

if __name__ == "__main__":
    find_delisted()
