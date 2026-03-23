
import os
import sqlite3

def cleanup():
    # DB Cleanup
    try:
        conn = sqlite3.connect('stocks.db')
        conn.execute("DELETE FROM multibaggers WHERE symbol='TEST_SMALL.NS'")
        conn.execute("DELETE FROM executions WHERE source='TEST'")
        conn.commit()
        conn.close()
        print("Cleaned DB.")
    except Exception as e:
        print(f"DB Cleanup Error: {e}")

    # File Cleanup
    files = ['test_slippage_calibration.py', 'run_slippage_test.py', 'debug_slippage_test.py', 'cleanup_slippage_test.py']
    for f in files:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"Removed {f}")
            except Exception as e:
                print(f"Error removing {f}: {e}")

if __name__ == "__main__":
    cleanup()
