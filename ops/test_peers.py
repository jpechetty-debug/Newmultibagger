import sqlite3
import pandas as pd

conn = sqlite3.connect('d:/Tradeidesa/Multibagger/stocks.db')
symbol = "MAHABANK.NS"

print("1. Target Query:")
target_query = "SELECT symbol, sector, current_price, score, pe, roe, debt_equity, price_change_3m FROM multibaggers WHERE symbol = ?"
target = pd.read_sql(target_query, conn, params=(symbol,))
print(target)

if not target.empty:
    print("\n2. Peers Query:")
    query = """
        SELECT symbol, name, current_price, score, pe, roe, debt_equity, price_change_3m
        FROM multibaggers 
        WHERE sector = (SELECT sector FROM multibaggers WHERE symbol = ?) 
        AND symbol != ?
        ORDER BY score DESC
        LIMIT 5
    """
    peers_df = pd.read_sql(query, conn, params=(symbol, symbol))
    print(peers_df)
