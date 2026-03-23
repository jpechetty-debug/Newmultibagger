import sqlite3
import json

def get_stock_details(symbol):
    conn = sqlite3.connect('stocks.db')
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    full_data = {}
    for table in tables:
        try:
            # Check if table has 'symbol' column
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            if 'symbol' in columns:
                cursor.execute(f"SELECT * FROM {table} WHERE symbol=?", (symbol,))
                row = cursor.fetchone()
                if row:
                    full_data[table] = dict(zip(columns, row))
        except Exception as e:
            full_data[table] = {"error": str(e)}
            
    conn.close()
    return full_data

if __name__ == "__main__":
    symbol = "STYLAMIND.NS"
    data = get_stock_details(symbol)
    with open("full_stock_audit_data.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Data for {symbol} saved to full_stock_audit_data.json")
