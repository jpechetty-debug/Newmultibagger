import yfinance as yf
import pandas as pd

def check_revisions(symbol):
    print(f"Checking Revisions for {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # 1. Recommendations (Target Price)
    try:
        recs = ticker.recommendations
        if recs is not None and not recs.empty:
            print("\nRecommendations (Tail):")
            print(recs.tail())
        else:
            print("\nNo Recommendations data.")
    except Exception as e:
        print(f"Error fetching recommendations: {e}")
        
    # 2. Upgrades/Downgrades
    try:
        upgrades = ticker.upgrades_downgrades
        if upgrades is not None and not upgrades.empty:
            print("\nUpgrades/Downgrades (Tail):")
            print(upgrades.tail())
        else:
            print("\nNo Upgrades/Downgrades data.")
    except Exception as e:
        print(f"Error fetching upgrades: {e}")
        
    # 3. Earnings Estimate
    try:
        # Some versions of yfinance or data providers might have this
        est = ticker.earnings_estimate
        if est is not None and not est.empty:
            print("\nEarnings Estimate:")
            print(est)
        else:
             print("\nNo Earnings Estimate data.")
    except Exception as e:
        print(f"Error fetching earnings estimate: {e}")
        
    # 4. Calendar (Next Earnings)
    try:
        cal = ticker.calendar
        print("\nCalendar:")
        print(cal)
    except Exception as e:
        print(f"Error fetching calendar: {e}")

if __name__ == "__main__":
    check_revisions("INFY.NS")
    check_revisions("TCS.NS")
