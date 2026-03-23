
import asyncio
import os
import sys
import pandas as pd

# Add base dir to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from modules.data_manager import data_manager
from modules.fundamentals import calculate_current_roe, calculate_recent_sales_growth, extract_financial_metric

async def debug_reliance():
    symbol = "RELIANCE.NS"
    print(f"--- Debugging Raw Data for {symbol} ---")
    
    raw = await data_manager.async_fetch_fundamentals(symbol)
    print(f"Source: {raw.get('source')}")
    print(f"Price (Raw): {raw.get('price')}")
    
    info = raw.get("info", {})
    fin = raw.get("financials", pd.DataFrame())
    bs = raw.get("balance_sheet", pd.DataFrame())
    
    print(f"Info Available: {not not info}")
    print(f"Financials Empty: {fin.empty}")
    if not fin.empty:
        print("Financials Keys:", fin.index.tolist()[:10], "... (Total:", len(fin.index), ")")
    
    print(f"Balance Sheet Empty: {bs.empty}")
    if not bs.empty:
        print("Balance Sheet Keys:", bs.index.tolist()[:10], "... (Total:", len(bs.index), ")")
        
    print("\n--- Detailed Metric Extraction ---")
    
    net_income = extract_financial_metric(
            fin, ["Net Income", "Net Income Common Stockholders", "Net Profit"]
        )
    print(f"Net Income Found: {net_income}")
    
    equity = extract_financial_metric(
            bs, ["Stockholders Equity", "Common Stock Equity", "Total Equity"]
        )
    print(f"Equity Found: {equity}")
    
    roe = calculate_current_roe(type('obj', (object,), {'financials': fin, 'balance_sheet': bs}))
    print(f"Calculated ROE: {roe}")
    
    growth = calculate_recent_sales_growth(type('obj', (object,), {'financials': fin}))
    print(f"Calculated Sales Growth: {growth}")

if __name__ == "__main__":
    asyncio.run(debug_reliance())
