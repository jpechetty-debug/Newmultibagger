import sqlite3
import pandas as pd
import json

conn = sqlite3.connect('d:/Tradeidesa/Multibagger/stocks.db')
symbol = "MAHABANK.NS"

# 1. Get Target Metrics
target_query = "SELECT symbol, sector, price as current_price, score as terminal_score, pe_ratio as pe, roe, debt_equity, rs_rating as price_change_3m FROM multibaggers WHERE symbol = ?"
target = pd.read_sql(target_query, conn, params=(symbol,))

if not target.empty:
    start_sector = target.iloc[0]['sector']

    # 2. Get Peers using Subquery for Sector (More robust)
    query = """
        SELECT symbol, symbol as name, price as current_price, score as terminal_score, pe_ratio as pe, roe, debt_equity, rs_rating as price_change_3m
        FROM multibaggers 
        WHERE sector = (SELECT sector FROM multibaggers WHERE symbol = ?) 
        AND symbol != ?
        ORDER BY score DESC
        LIMIT 5
    """
    peers_df = pd.read_sql(query, conn, params=(symbol, symbol))
    peers = peers_df.to_dict(orient="records")
    
    # 3. Sector Averages
    avg_query = """
        SELECT 
            AVG(pe_ratio) as pe, 
            AVG(roe) as roe, 
            AVG(score) as terminal_score 
        FROM multibaggers 
        WHERE sector = (SELECT sector FROM multibaggers WHERE symbol = ?)
    """
    avg_df = pd.read_sql(avg_query, conn, params=(symbol,))
    avgs = avg_df.iloc[0].to_dict() if not avg_df.empty else {}

    result = {
        "sector": start_sector,
        "peers": peers,
        "sector_avg": avgs,
        "stock_metrics": target.iloc[0].to_dict(),
        "rankings": {"score_rank_desc": "Top 10"}
    }
    print(json.dumps(result, indent=2))
else:
    print("Target empty")
