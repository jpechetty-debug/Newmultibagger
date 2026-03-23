import sqlite3
import os

def cleanup_db(db_path='stocks.db'):
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Identify TEST tickers
    cursor.execute('SELECT symbol FROM multibaggers WHERE symbol LIKE "TEST%"')
    test_tickers = [row[0] for row in cursor.fetchall()]
    
    if not test_tickers:
        print("No TEST tickers found in multibaggers table.")
    else:
        print(f"Removing TEST tickers: {', '.join(test_tickers)}")
        placeholders = ', '.join(['?'] * len(test_tickers))
        cursor.execute(f"DELETE FROM multibaggers WHERE symbol IN ({placeholders})", test_tickers)
        
    # Also check other tables
    for table in ['valuation_metrics', 'fundamentals_pit']:
        try:
            cursor.execute(f"SELECT symbol FROM {table} WHERE symbol LIKE 'TEST%'")
            results = cursor.fetchall()
            if results:
                print(f"Removing test data from {table}...")
                cursor.execute(f"DELETE FROM {table} WHERE symbol LIKE 'TEST%'")
        except sqlite3.OperationalError:
            pass # Table might not exist
            
    conn.commit()
    conn.close()
    print("Cleanup complete.")

if __name__ == "__main__":
    cleanup_db()
