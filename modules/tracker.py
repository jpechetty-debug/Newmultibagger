import datetime
import sqlite3

import pandas as pd

DB_NAME = "portfolio_history.db"


class PortfolioTracker:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_name)

    def _init_db(self):
        """Initialize portfolio history database schema."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                entry_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_score REAL,
                quantity INTEGER,
                status TEXT DEFAULT 'OPEN',
                exit_date TEXT,
                exit_price REAL,
                exit_reason TEXT,
                pnl_abs REAL,
                pnl_pct REAL,
                holding_days INTEGER
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                date TEXT PRIMARY KEY,
                total_equity REAL,
                cash_balance REAL,
                invested_amount REAL,
                open_positions_count INTEGER
            )
            """
        )

        conn.commit()
        conn.close()

    def log_entry(self, symbol, price, score, quantity=0):
        """Log a new trade entry."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM trades WHERE symbol = ? AND status = 'OPEN'", (symbol,)
        )
        if cursor.fetchone():
            message = f"Position already open for {symbol}. Skipping."
            print(message)
            conn.close()
            return {"status": "rejected", "reason": message}

        entry_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            INSERT INTO trades (symbol, entry_date, entry_price, entry_score, quantity, status)
            VALUES (?, ?, ?, ?, ?, 'OPEN')
            """,
            (symbol, entry_date, price, score, quantity),
        )

        conn.commit()
        print(f"Trade Logged: BUY {symbol} @ {price}")
        conn.close()
        return {
            "status": "accepted",
            "action": "BUY",
            "symbol": symbol,
            "entry_date": entry_date,
        }

    def log_exit(self, symbol, exit_price, exit_reason):
        """Log a trade exit."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, entry_price, entry_date FROM trades WHERE symbol = ? AND status = 'OPEN'",
            (symbol,),
        )
        row = cursor.fetchone()

        if not row:
            message = f"No open position found for {symbol} to close."
            print(message)
            conn.close()
            return {"status": "rejected", "reason": message}

        trade_id, entry_price, entry_date_str = row

        pnl_abs = exit_price - entry_price
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        exit_date = datetime.datetime.now()
        entry_date = datetime.datetime.strptime(entry_date_str, "%Y-%m-%d %H:%M:%S")
        holding_days = (exit_date - entry_date).days

        cursor.execute(
            """
            UPDATE trades
            SET status = 'CLOSED',
                exit_date = ?,
                exit_price = ?,
                exit_reason = ?,
                pnl_abs = ?,
                pnl_pct = ?,
                holding_days = ?
            WHERE id = ?
            """,
            (
                exit_date.strftime("%Y-%m-%d %H:%M:%S"),
                exit_price,
                exit_reason,
                pnl_abs,
                pnl_pct,
                holding_days,
                trade_id,
            ),
        )

        conn.commit()
        print(f"Trade Closed: SELL {symbol} @ {exit_price} ({pnl_pct:.2f}%) [{exit_reason}]")
        conn.close()
        return {
            "status": "accepted",
            "action": "SELL",
            "symbol": symbol,
            "exit_reason": exit_reason,
            "pnl_pct": round(pnl_pct, 2),
        }

    def get_open_positions(self):
        """Return a DataFrame of open positions."""
        conn = self._get_conn()
        df = pd.read_sql("SELECT * FROM trades WHERE status = 'OPEN'", conn)
        conn.close()
        return df

    def get_trade_history(self):
        """Return a DataFrame of all closed trades."""
        conn = self._get_conn()
        df = pd.read_sql("SELECT * FROM trades WHERE status = 'CLOSED'", conn)
        conn.close()
        return df
