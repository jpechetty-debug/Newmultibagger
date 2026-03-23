
import sqlite3
import pandas as pd
import os

def check_system():
    print("--- Checking Database ---")
    if not os.path.exists("stocks.db"):
        print("ERROR: stocks.db not found!")
    else:
        try:
            conn = sqlite3.connect("stocks.db")
            res = pd.read_sql("SELECT * FROM multibaggers LIMIT 5", conn)
            print(f"DB Read Successful. Columns: {res.columns.tolist()}")
            if 'market_cap_cr' in res.columns:
                print("Schema Verified: New columns present.")
            else:
                print("Schema WARNING: New columns MISSING.")
            conn.close()
        except Exception as e:
            print(f"DB Error: {e}")

    print("\n--- Checking CSV ---")
    if os.path.exists("screener_results.csv"):
        try:
            df = pd.read_csv("screener_results.csv")
            print(f"CSV Read Successful. Rows: {len(df)}")
        except Exception as e:
            print(f"CSV Error: {e}")
    else:
        print("screener_results.csv not found.")

    print("\n--- Checking Imports ---")
    try:
        import main
        print("Import main.py Successful.")
    except Exception as e:
        print(f"Import Error: {e}")

if __name__ == "__main__":
    check_system()
