import yfinance as yf

def analyze_market_regime(symbol="^NSEI"):
    """
    Determines Market Regime: Bull, Bear, Correction, Sideways.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y") # Need 200 DMA
        
        if len(hist) < 200:
            return "Unknown"
            
        sma_50 = hist['Close'].tail(50).mean()
        sma_200 = hist['Close'].tail(200).mean()
        current_price = hist['Close'].iloc[-1]
        
        if current_price > sma_50 and sma_50 > sma_200:
            return "Bull Market"
        elif current_price < sma_50 and sma_50 < sma_200:
            return "Bear Market"
        elif current_price < sma_50 and current_price > sma_200:
            return "Correction"
        elif current_price > sma_50 and current_price < sma_200:
            return "Recovery"
        else:
            return "Sideways"
    except:
        return "Unknown"

def analyze_sector_rotation(stock_list):
    sector_returns = {}
    sector_counts = {}
    
    print("\nCalculating Sector Rotation...")
    for stock in stock_list:
        sec = stock.get("Sector", "Unknown")
        rs = stock.get("RS_Rating", 0)
        
        if sec not in sector_returns:
            sector_returns[sec] = 0.0
            sector_counts[sec] = 0
        
        sector_returns[sec] += rs
        sector_counts[sec] += 1
        
    avg_sector_rs = {}
    for sec, total_rs in sector_returns.items():
        if sector_counts[sec] > 0:
            avg_sector_rs[sec] = total_rs / sector_counts[sec]
            
    sorted_sectors = sorted(avg_sector_rs.items(), key=lambda x: x[1], reverse=True)
    
    print("Top 3 Leading Sectors (by RS):")
    top_3 = []
    for i, (sec, rs) in enumerate(sorted_sectors[:3]):
        print(f"{i+1}. {sec}: Avg RS {rs:.2f}")
        top_3.append(sec)
        
    return top_3
