import sqlite3
import pandas as pd
import yfinance as yf
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "stocks.db")

def calculate_portfolio_correlation(limit=20, threshold=0.75):
    """
    Calculates pairwise trailing 6-month correlation for the Top N portfolio picks.
    Flags if a high percentage of the portfolio is statistically identical (clustered beta risk).
    """
    if not os.path.exists(DB_PATH):
        return {"error": "Database not found"}
        
    try:
        conn = sqlite3.connect(DB_PATH)
        df_top = pd.read_sql(f"SELECT symbol FROM multibaggers ORDER BY score DESC, rs_rating DESC, market_cap_cr DESC LIMIT {limit}", conn)
        conn.close()
        
        if df_top.empty:
            return {"error": "No stocks found"}
            
        symbols = df_top['symbol'].tolist()
        
        # Fetch 6-month daily closing prices
        data = yf.download(symbols, period="6mo", interval="1d", progress=False)
        
        if isinstance(data.columns, pd.MultiIndex):
            if "Close" in data:
                close_prices = data["Close"]
            else:
                return {"error": "Close price not found in fetched data"}
        else:
            close_prices = pd.DataFrame(data) if len(symbols) == 1 else data

        # Calculate Pearson Correlation Matrix
        corr_matrix = close_prices.corr(method="pearson").round(2)
        
        # Analyze clusters
        high_corr_pairs = []
        total_pairs = 0
        
        for i in range(len(corr_matrix.columns)):
            for j in range(i + 1, len(corr_matrix.columns)):
                sym1 = corr_matrix.columns[i]
                sym2 = corr_matrix.columns[j]
                val = corr_matrix.iloc[i, j]
                
                if pd.notna(val):
                    total_pairs += 1
                    if val > threshold:
                        high_corr_pairs.append((sym1, sym2, val))
                        
        clustered_pct = (len(high_corr_pairs) / total_pairs * 100) if total_pairs > 0 else 0
        
        # Risk thresholds
        stress_level = "LOW"
        if clustered_pct > 35:
            stress_level = "CRITICAL (Systematic Beta Crash Risk)"
        elif clustered_pct > 20:
            stress_level = "WARNING (Moderate Clustering)"
            
        return {
            "symbols_analyzed": len(symbols),
            "threshold": threshold,
            "total_pairs": total_pairs,
            "high_corr_count": len(high_corr_pairs),
            "clustered_percentage": round(clustered_pct, 1),
            "stress_level": stress_level,
            "high_corr_pairs": [{"pair": f"{p[0]} ↔ {p[1]}", "correlation": float(p[2])} for p in sorted(high_corr_pairs, key=lambda x: x[2], reverse=True)]
        }
        
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    result = calculate_portfolio_correlation()
    print(json.dumps(result, indent=2))
