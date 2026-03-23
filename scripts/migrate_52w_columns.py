import sqlite3
import os

DB_NAME = "stocks.db"

def migrate():
    if not os.path.exists(DB_NAME):
        print(f"Error: {DB_NAME} not found in current directory.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    tables = ["multibaggers", "fundamentals_pit"]
    columns_to_add = [("high_52w", "REAL"), ("low_52w", "REAL")]

    for table in tables:
        # Check if table exists
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
        if not cursor.fetchone():
            print(f"Skipping table {table} (not found).")
            continue

        # Get existing columns
        cursor.execute(f"PRAGMA table_info({table})")
        existing_cols = {row[1] for row in cursor.fetchall()}

        for col_name, col_type in columns_to_add:
            if col_name not in existing_cols:
                print(f"Adding column {col_name} to table {table}...")
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                except Exception as e:
                    print(f"Error adding {col_name} to {table}: {e}")
            else:
                print(f"Column {col_name} already exists in table {table}.")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
