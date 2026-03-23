
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.html_report import generate_premium_html_report

async def generate_watchlist_batch():
    watchlist = [
        "INDIGOPNTS.NS",    # Indigo Paints
        "INOXWIND.NS",      # Inox Wind
        "IGL.NS",           # Indraprastha Gas
        "GALAXYSURF.NS",    # Galaxy Surfactants
        "TIMETECHNO.NS",    # Time Technoplast
        "CELLO.NS",         # Cello World
        "SIEMENS.NS",       # Siemens Energy (Siemens Ltd in India context)
        "ASTRAMICRO.NS",    # Astra Microwave Products
        "BECTORFOOD.NS",    # Mrs. Bectors Food Specialities
        "PETRONET.NS",      # Petronet LNG
    ]
    
    print(f"🚀 Starting Batch Report Generation for {len(watchlist)} High-Conviction Stocks...")
    
    results = []
    for symbol in watchlist:
        try:
            path = await generate_premium_html_report(symbol)
            if "Error" not in path:
                print(f"✅ Generated: {symbol}")
                results.append(path)
            else:
                print(f"❌ Failed: {symbol} - {path}")
        except Exception as e:
            print(f"❌ Exception for {symbol}: {e}")

    print("\n--- Summary ---")
    print(f"Total Generated: {len(results)}/{len(watchlist)}")
    for r in results:
        print(f"📄 {r}")

if __name__ == "__main__":
    asyncio.run(generate_watchlist_batch())
