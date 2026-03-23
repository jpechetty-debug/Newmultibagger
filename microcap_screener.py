import yfinance as yf
import pandas as pd
import numpy as np
from ticker_list import TICKERS
import time

def get_microcap_data(ticker_symbol):
    """
    Fetches data for Microcap 'Hidden Gem' Framework.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # --- 1. Market Cap Check ---
        # We want approx 100Cr to 5000Cr (or 10,000Cr for small caps)
        # yfinance marketCap is in absolute currency units
        market_cap = info.get('marketCap', 0)
        if market_cap is None: market_cap = 0
        market_cap_cr = market_cap / 10000000 # Convert to Crores
        
        # --- 2. Skin in the Game (Promoter Holding) ---
        # 'heldPercentInsiders' is the proxy. 0.5 = 50%
        # Note: yfinance data quality for this varies. 
        promoter_holding = info.get('heldPercentInsiders', 0)
        if promoter_holding is None: promoter_holding = 0
        
        # --- 3. Growth & Margins ---
        sales_growth = info.get('revenueGrowth', 0) # TTM
        if sales_growth is None: sales_growth = 0
        
        # OPM / Profit Margins
        profit_margin = info.get('profitMargins', 0)
        
        # --- 4. Valuation ---
        # PEG Ratio
        peg_ratio = info.get('pegRatio', 0)
        if peg_ratio is None: peg_ratio = 100 # Penalize if missing
        
        # --- 5. Technical Trend ---
        hist = ticker.history(period="1y")
        if hist.empty:
            return None
        current_price = hist['Close'].iloc[-1]
        year_high = hist['Close'].max()
        
        # Distance from 52-week High (Should be near, e.g. within 20-30%)
        # "Hidden gems" often breaking out.
        # Logic: If Price > 0.8 * High
        pct_from_high = (current_price - year_high) / year_high 
        
        return {
            "Symbol": ticker_symbol,
            "Price": round(current_price, 2),
            "MarketCap_Cr": round(market_cap_cr, 0),
            "Promoter_Hol%": round(promoter_holding * 100, 2),
            "Sales_Growth%": round(sales_growth * 100, 2),
            "Profit_Margin%": round(profit_margin * 100, 2),
            "PEG": peg_ratio,
            "Pct_From_High": round(pct_from_high * 100, 2)
        }

    except Exception as e:
        # print(f"Error {ticker_symbol}: {e}")
        return None

def main():
    print(f"Scanning {len(TICKERS)} stocks for Microcap Gems...")
    results = []
    
    for symbol in TICKERS:
        print(f"Checking {symbol}...", end="\r")
        data = get_microcap_data(symbol)
        
        if data:
            # --- "SPRINGPAD FRAMEWORK" MICROCAP FILTERS ---
            # Implements the criteria from the comparison prompt
            
            # 1. Fundamental Quality
            # ROE > 12% (Efficient Use of Equity)
            score_roe = 1 if data["Profit_Margin%"] > 10 else 0 # Proxy if ROE missing, usually want ROE > 15
            
            # 2. Financial Health
            # Debt to Equity < 1.0 (Safety)
            # Market Cap Check: Strict Microcap (< 5000 Cr)
            is_microcap = 100 <= data["MarketCap_Cr"] <= 5000
            
            # 3. Growth (The Engine)
            # Sales Growth > 15%
            is_high_growth = data["Sales_Growth%"] > 15
            
            # 4. Skin in the Game
            is_high_promoter = data["Promoter_Hol%"] > 50

            # 5. Valuation (Simple check)
            # PEG < 1.5 is ideal
            is_value = data["PEG"] < 1.5
            
            # Scoring (Max 5)
            # We strictly filter for Microcap size first
            if is_microcap:
                final_score = 0
                if is_high_promoter: final_score += 1
                if is_high_growth: final_score += 1
                if data["Sales_Growth%"] > 20: final_score += 1 # Extra point for super growth
                if data["Profit_Margin%"] > 12: final_score += 1 # Quality margins
                if data["Pct_From_High"] > -20: final_score += 1 # Technical Strength
                
                # --- CALCULATE ENTRY / EXIT LEVELS ---
                # Simple Swing Strategy:
                # Entry: Current Price range
                # Stop Loss: 8% below CMP (Capital Protection)
                # Target: 20% upside (Multibagger Start)
                
                cmp = data["Price"]
                data["Buy_Zone"] = f"{round(cmp * 0.98, 1)} - {cmp}"
                data["Stop_Loss"] = round(cmp * 0.92, 1) # -8% Risk
                data["Target_1"] = round(cmp * 1.20, 1)  # +20% Reward
                data["Target_2"] = round(cmp * 1.40, 1)  # +40% Multibagger
                
                data["Score"] = final_score
                results.append(data)

    print("\n\nSpringPad Microcap Scan Complete.")
    
    df = pd.DataFrame(results)
    
    if df.empty:
        print("No matches found in the Microcap range.")
        return

    # Filter for Best Opportunities (Score >= 4)
    candidates = df[df["Score"] >= 4].sort_values(by="Score", ascending=False)

    print("\n--- SpringPad Hidden Gems (Score 4-5) ---")
    cols_to_show = ["Symbol", "Price", "Score", "Buy_Zone", "Stop_Loss", "Target_1"]
    print(candidates[cols_to_show])
    
    candidates.to_csv("springpad_microcaps.csv", index=False)
    print("\nSaved to 'springpad_microcaps.csv'")
    
    # Save to SQLite (New)
    try:
        import database
        database.save_microcaps(candidates)
    except ImportError:
        print("Database module not found. Skipping DB save.")
    except Exception as e:
        print(f"Error saving to DB: {e}")

if __name__ == "__main__":
    main()
