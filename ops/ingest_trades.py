
import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from modules.execution_analyzer import ExecutionAnalyzer
except ImportError:
    print("Error: Could not import 'modules'. Run from project root.")
    sys.exit(1)

def ingest(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
        
    print(f"Reading {file_path}...")
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        sys.exit(1)
        
    print(f"Loaded {len(df)} rows.")
    analyzer = ExecutionAnalyzer()
    analyzer.ingest_fills(df)
    print("Ingestion complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ops/ingest_trades.py <path_to_csv>")
        print("Expected CSV Headers: symbol, side, fill_price, expected_price, timestamp")
        sys.exit(1)
        
    ingest(sys.argv[1])
