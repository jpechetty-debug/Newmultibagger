
import asyncio
import os
import sys
import pandas as pd

# Add base dir to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

import screener
import database

async def update_sample():
    symbols = ["RELIANCE.NS", "TCS.NS", "TITAN.NS"]
    print(f"--- Updating Sample Database Entries for {symbols} ---")
    
    results = []
    for sym in symbols:
        data = await screener.get_stock_data(sym)
        if data:
            results.append(data)
            print(f"Fetched {sym}: ROE={data.get('ROE%')}%, SG={data.get('Sales_Growth_TTM%')}%")
    
    if results:
        df = pd.DataFrame(results)
        database.save_multibaggers(df)
        print("\n✅ Database updated for sample stocks.")
    else:
        print("\n❌ No data fetched.")

if __name__ == "__main__":
    asyncio.run(update_sample())
