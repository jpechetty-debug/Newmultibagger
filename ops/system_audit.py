import sqlite3
import pandas as pd
import json
import os
import sys

# Add base dir to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
import ticker_list

DB_PATH = os.path.join(BASE_DIR, "stocks.db")

def run_audit():
    audit_results = {}
    
    # 1. Ticker List Audit
    raw_tickers = ticker_list.TICKERS
    unique_tickers = list(dict.fromkeys(raw_tickers))
    duplicates = [t for t in set(raw_tickers) if raw_tickers.count(t) > 1]
    
    audit_results["ticker_list"] = {
        "total_raw": len(raw_tickers),
        "total_unique": len(unique_tickers),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates
    }
    
    # 2. Database Audit
    if not os.path.exists(DB_PATH):
        audit_results["database"] = "Database file not found."
        return audit_results
        
    conn = sqlite3.connect(DB_PATH)
    try:
        # Check tables
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table';", conn)['name'].tolist()
        audit_results["database"] = {"tables": tables}
        
        if 'multibaggers' in tables:
            df = pd.read_sql("SELECT * FROM multibaggers", conn)
            
            # Record count
            audit_results["database"]["multibaggers_count"] = len(df)
            
            # Coverage
            db_symbols = set(df['symbol'].tolist())
            list_symbols = set(unique_tickers)
            missing_in_db = list(list_symbols - db_symbols)
            extra_in_db = list(db_symbols - list_symbols)
            
            audit_results["coverage"] = {
                "missing_in_db_count": len(missing_in_db),
                "missing_in_db_sample": missing_in_db[:10],
                "extra_in_db_count": len(extra_in_db),
                "extra_in_db_sample": extra_in_db[:10]
            }
            
            # Data Quality
            critical_metrics = ['pe_ratio', 'roe', 'avg_roe_5y', 'sales_cagr_5y', 'debt_equity', 'f_score', 'market_cap_cr']
            quality_stats = {}
            for metric in critical_metrics:
                if metric in df.columns:
                    # Count None/NaN values
                    is_null = df[metric].isna()
                    # Count zeros (often used as null proxy)
                    is_zero = (df[metric] == 0)
                    
                    null_count = int(is_null.sum())
                    zero_count = int(is_zero.sum())
                    total_records = len(df)
                    
                    quality_stats[metric] = {
                        "nulls": null_count,
                        "zeros": zero_count,
                        "coverage_pct": round(((total_records - null_count - zero_count) / total_records) * 100, 1) if total_records > 0 else 0
                    }
            audit_results["data_quality"] = quality_stats
            
            # Freshness
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                audit_results["freshness"] = {
                    "latest_update": df['timestamp'].max().isoformat(),
                    "oldest_update": df['timestamp'].min().isoformat()
                }
    finally:
        conn.close()
        
    return audit_results

if __name__ == "__main__":
    results = run_audit()
    print(json.dumps(results, indent=2))
    with open("system_audit_report.json", "w") as f:
        json.dump(results, f, indent=2)
