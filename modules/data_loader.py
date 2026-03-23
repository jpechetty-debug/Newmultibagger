import pandas as pd
import os

def load_tickers_from_csv(file_paths):
    """
    Reads multiple CSV files, extracts symbols, deduplicates, and formats them for yfinance (.NS).
    """
    all_symbols = set()
    
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}")
            continue
            
        try:
            # key is usually "SYMBOL" or "Symbol"
            # Some NSE CSVs have garbage in first few lines or trailing whitespace
            df = pd.read_csv(file_path)
            
            # Clean column names (strip whitespace)
            df.columns = df.columns.str.strip()
            
            # Find symbol column
            symbol_col = None
            for col in ["SYMBOL", "Symbol", "Ticker", "ISIN"]:
                if col in df.columns:
                    symbol_col = col
                    break
            
            if symbol_col:
                symbols = df[symbol_col].dropna().unique()
                for sym in symbols:
                    sym = str(sym).strip()
                    if not sym.endswith(".NS") and not sym.endswith(".BO"):
                        sym += ".NS"
                    all_symbols.add(sym)
            else:
                print(f"Warning: No 'SYMBOL' column found in {file_path}")
                
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            
    return list(all_symbols)
