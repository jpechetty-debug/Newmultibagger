import asyncio
from sovereign_mcp import get_market_regime, analyze_ticker

async def test():
    print("Testing get_market_regime...")
    regime = await get_market_regime()
    print(regime)
    
    print("\nTesting analyze_ticker for RELIANCE.NS...")
    analysis = await analyze_ticker("RELIANCE.NS")
    print(analysis)

if __name__ == "__main__":
    asyncio.run(test())
