import sqlite3
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path('d:/Tradeidesa/Multibagger/stocks.db')

def audit_database():
    report = {
        "timestamp": datetime.now().isoformat(),
        "database_path": str(DB_PATH),
        "tables": {},
        "integrity": {
            "score": "8/10",
            "critical_issues": [],
            "warnings": []
        }
    }
    
    if not DB_PATH.exists():
        report["integrity"]["score"] = "0/10"
        report["integrity"]["critical_issues"].append("Database file not found.")
        print(json.dumps(report, indent=2))
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        required_tables = [
            'multibaggers', 'microcaps', 'valuation_metrics', 'fundamentals_pit',
            'score_history', 'factor_penalties', 'buy_thesis'
        ]
        
        for table in required_tables:
            if table in existing_tables:
                count = pd.read_sql(f"SELECT COUNT(*) FROM {table}", conn).iloc[0, 0]
                report["tables"][table] = {"status": "EXISTS", "row_count": int(count)}
            else:
                report["tables"][table] = {"status": "MISSING", "row_count": 0}
                report["integrity"]["critical_issues"].append(f"Table '{table}' is missing.")
                report["integrity"]["score"] = "4/10"

        if 'multibaggers' in existing_tables:
            df = pd.read_sql("SELECT * FROM multibaggers", conn)
            
            # Duplicates check
            if 'symbol' in df.columns:
                dupes = len(df) - df['symbol'].nunique()
                if dupes > 0:
                    report["integrity"]["critical_issues"].append(f"Found {dupes} duplicate symbols in 'multibaggers'.")
                    report["integrity"]["score"] = "4/10"
                report["tables"]["multibaggers"]["duplicates"] = int(dupes)

            # Nulls/Zeros check
            check_cols = ['pe_ratio', 'avg_roe_5y', 'sales_cagr_5y']
            null_summary = {}
            for col in check_cols:
                if col in df.columns:
                    missing = df[col].isnull().sum() + (df[col] == 0).sum()
                    null_summary[col] = int(missing)
            report["tables"]["multibaggers"]["null_or_zero_leakage"] = null_summary

        conn.close()
    except Exception as e:
        report["integrity"]["score"] = "0/10"
        report["integrity"]["critical_issues"].append(f"Audit failed with error: {str(e)}")

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    audit_database()
