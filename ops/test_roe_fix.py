
import asyncio
import os
import sys

# Add base dir to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

import screener

async def test_extraction():
    symbol = "RELIANCE.NS"
    print(f"--- Testing Data Extraction for {symbol} ---")
    
    data = await screener.get_stock_data(symbol)
    if data:
        print(f"Symbol: {data.get('Symbol')}")
        print(f"Price: {data.get('Price')}")
        print(f"ROE%: {data.get('ROE%')}%")
        print(f"Sales Growth TTM%: {data.get('Sales_Growth_TTM%')}%")
        print(f"Sales Growth 5Y%: {data.get('Sales_Growth_5Y%')}%")
        print(f"Avg ROE 5Y%: {data.get('Avg_ROE_5Y%')}%")
        
        # Check if ROE is still 0
        if data.get('ROE%', 0) > 0:
            print("\nSUCCESS: Current ROE extracted!")
        else:
            print("\nFAILURE: Current ROE still 0.")
            
        if data.get('Sales_Growth_TTM%', 0) > 0 or data.get('Sales_Growth_5Y%', 0) > 0:
            print("SUCCESS: Sales Growth captured!")
        else:
            print("FAILURE: Sales Growth still 0.")
    else:
        print(f"Failed to fetch data for {symbol}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
