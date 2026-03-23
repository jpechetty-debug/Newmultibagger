
import yfinance as yf

symbols = ["INDIGOPNTS.NS", "RELIANCE.NS", "TATAMOTORS.NS", "TATAMOTORS.BO", "ITDCEM.NS"]

print("Health Check:")
for s in symbols:
    print(f"--- {s} ---")
    try:
        t = yf.Ticker(s)
        hist = t.history(period="1d")
        if not hist.empty:
            print(f"✅ History Check: PASS ({hist['Close'].iloc[-1]})")
        else:
            print(f"❌ History Check: FAIL (Empty)")
            
        info = t.info
        if info and 'currentPrice' in info:
             print(f"✅ Info Check: PASS ({info['currentPrice']})")
        else:
             print(f"❌ Info Check: FAIL")
             
    except Exception as e:
        print(f"❌ Exception: {e}")
