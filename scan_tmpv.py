
import pandas as pd
from screener import get_stock_data, calculate_institutional_score
import database
import sys

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

TICKERS_TO_SCAN = ["TMPV.NS"]

def scan_and_update():
    print(f"Scanning {len(TICKERS_TO_SCAN)} tickers...")
    
    records = []
    
    for symbol in TICKERS_TO_SCAN:
        print(f"Fetching data for {symbol}...")
        try:
            stock_data = get_stock_data(symbol)
            if stock_data:
                # Calculate Score
                score_blob = calculate_institutional_score(stock_data)
                
                score = 0
                if isinstance(score_blob, dict):
                    score = score_blob.get('total_score', 0)
                else:
                    score = score_blob

                stock_data['Score'] = score
                stock_data['Symbol'] = symbol
                
                # Check required keys
                keys_needed = [
                    "Symbol", "Price", "Sector", "Score", "F_Score", "Rating",
                    "Sales_Growth_TTM%", "ROE%", "PEG_Ratio", "Debt_Equity",
                    "RSI", "Smart_Money%", "Market_Cap_Cr", "CFO_PAT_Ratio",
                    "Sales_Growth_5Y%", "Avg_ROE_5Y%", "PE_Ratio", "Down_From_52W_High%",
                    "RS_Rating", "Earnings_Accel", "Sector_Leader", "Graham_Number",
                    "Value_Gap%", "Technical_Signal", "Analyst_Rating", "Analyst_Upside%",
                    "Promoter_Holding%", "Inst_Holding%", "ATR", "Stop_Loss_ATR", "Max_Qty_1L",
                    "Conviction_Score", "Conviction_Boost", "Institutional_Interest"
                ]
                
                for k in keys_needed:
                    if k not in stock_data:
                        stock_data[k] = 0 # Default fill
                
                records.append(stock_data)
                print(f"  > Scanned {symbol} (Score: {score})")
            else:
                print(f"  > No data found for {symbol}")
        except Exception as e:
            print(f"  > Error scanning {symbol}: {e}")
            import traceback
            traceback.print_exc()

    if records:
        df = pd.DataFrame(records)
        print(f"Saving {len(df)} records to DB...")
        database.save_multibaggers(df)
        print("Done.")

if __name__ == "__main__":
    scan_and_update()
