from modules.data_manager import data_manager
import logging

# Enable logging to see which source is processing
logging.basicConfig(level=logging.INFO)

def test_live_fetch():
    symbol = "SBIN.NS"
    print(f"Fetching fundamentals for {symbol}...")
    data = data_manager.fetch_fundamentals(symbol)
    
    if "error" in data:
        print(f"Error: {data['error']}")
    else:
        info = data.get("info", {})
        print(f"Success! Name: {info.get('longName')}, Price: {info.get('currentPrice')}")
        print(f"Financials shape: {data.get('financials').shape}")

    print("\nFetching quarterly results...")
    timeline = data_manager.fetch_quarterly_results(symbol)
    print(f"Quarterly data points: {len(timeline)}")
    if timeline:
        print(f"Latest: {timeline[0]}")

if __name__ == "__main__":
    test_live_fetch()
