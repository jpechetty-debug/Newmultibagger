# db/migrate.py
"""
Sovereign AI Trading Engine v4.0 — SQLite → PostgreSQL Migration Script
One-time migration utility that reads all data from the existing SQLite
database and bulk-inserts it into the configured PostgreSQL/TimescaleDB instance.

Usage:
    1. Set DATABASE_URL to your PostgreSQL connection string.
    2. Run: python -m db.migrate
"""
import sqlite3
import os
import pandas as pd
from datetime import datetime
from db.engine import engine, init_tables, IS_SQLITE
from db.models import Base


SQLITE_SOURCE = os.getenv("SQLITE_SOURCE", "stocks.db")

# Tables to migrate in dependency order
MIGRATION_ORDER = [
    "multibaggers",
    "fundamentals_pit",
    "score_history",
    "factor_penalties",
    "valuation_metrics",
    "microcaps",
    "executions",
    "slippage_metrics",
    "buy_thesis",
]


def _read_sqlite_table(sqlite_conn, table_name: str) -> pd.DataFrame:
    """Safely read a table from SQLite, returning empty DataFrame if missing."""
    try:
        return pd.read_sql(f"SELECT * FROM {table_name}", sqlite_conn)
    except Exception:
        print(f"  ⚠ Table '{table_name}' not found in SQLite source. Skipping.")
        return pd.DataFrame()


def run_migration():
    """Execute the full SQLite → PostgreSQL migration."""
    if IS_SQLITE:
        print("⚠ DATABASE_URL points to SQLite. Migration requires a PostgreSQL target.")
        print("  Set DATABASE_URL=postgresql+psycopg://user:pass@host:5432/sovereign_db")
        return

    if not os.path.exists(SQLITE_SOURCE):
        print(f"⚠ SQLite source '{SQLITE_SOURCE}' not found. Nothing to migrate.")
        return

    print(f"🔄 Starting migration: {SQLITE_SOURCE} → PostgreSQL")
    print(f"   Target: {engine.url}")

    # Step 1: Create all tables in PostgreSQL
    print("\n📐 Creating PostgreSQL schema...")
    init_tables()

    # Step 2: Connect to SQLite source
    sqlite_conn = sqlite3.connect(SQLITE_SOURCE)

    # Step 3: Migrate each table
    total_rows = 0
    for table_name in MIGRATION_ORDER:
        print(f"\n📦 Migrating: {table_name}")
        df = _read_sqlite_table(sqlite_conn, table_name)

        if df.empty:
            continue

        row_count = len(df)
        try:
            df.to_sql(
                table_name,
                engine,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=500,
            )
            total_rows += row_count
            print(f"  ✅ {row_count:,} rows migrated successfully.")
        except Exception as e:
            print(f"  ❌ Migration failed for {table_name}: {e}")

    sqlite_conn.close()

    print(f"\n{'='*50}")
    print(f"✅ Migration Complete: {total_rows:,} total rows transferred.")
    print(f"   Source: {SQLITE_SOURCE}")
    print(f"   Target: PostgreSQL/TimescaleDB")
    print(f"{'='*50}")


if __name__ == "__main__":
    run_migration()
