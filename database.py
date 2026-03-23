import sqlite3
import pandas as pd
from datetime import datetime
import time

DB_NAME = "stocks.db"
DB_BUSY_TIMEOUT_MS = 5000
SQLITE_WRITE_RETRIES = 5
SQLITE_RETRY_BASE_SECONDS = 0.05
PIT_RETENTION_DAYS = 365 * 3


def _normalize_as_of_date(value=None):
    """
    Normalize as-of values to YYYY-MM-DD.
    If missing/invalid, defaults to today's date.
    """
    if value is None:
        return datetime.now().date().isoformat()

    if isinstance(value, datetime):
        return value.date().isoformat()

    text = str(value).strip()
    if not text:
        return datetime.now().date().isoformat()

    try:
        if len(text) <= 10:
            return datetime.fromisoformat(text[:10]).date().isoformat()
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return datetime.now().date().isoformat()


def _table_columns(conn, table_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_column(conn, table_name, column_name, column_type):
    columns = _table_columns(conn, table_name)
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _ensure_fundamentals_pit_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamentals_pit (
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            price REAL,
            sector TEXT,
            score INTEGER,
            sales_cagr_5y REAL,
            avg_roe_5y REAL,
            pe_ratio REAL,
            debt_equity REAL,
            market_cap_cr REAL,
            cfo_pat_ratio REAL,
            high_52w REAL,
            low_52w REAL,
            roce REAL,
            median_pat_growth REAL,
            ret_1m REAL,
            ret_3m REAL,
            ret_6m REAL,
            vol_breakout REAL,
            dist_from_52w_high REAL,
            ml_rank_score REAL,
            source_updated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, as_of_date)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fundamentals_pit_as_of_date
        ON fundamentals_pit (as_of_date)
        """
    )


def _ensure_runtime_schema():
    """
    Ensure runtime schema is upgraded for Phase 67 point-in-time storage.
    """
    conn = get_connection()
    try:
        if _table_exists(conn, "multibaggers"):
            _ensure_column(conn, "multibaggers", "as_of_date", "TEXT")
        if _table_exists(conn, "valuation_metrics"):
            _ensure_column(conn, "valuation_metrics", "as_of_date", "TEXT")
        
        # Phase 10: Research Layer
        if _table_exists(conn, "multibaggers"):
            _ensure_column(conn, "multibaggers", "conviction_score", "REAL")
            _ensure_column(conn, "multibaggers", "conviction_boost", "REAL")
            _ensure_column(conn, "multibaggers", "institutional_interest", "INTEGER")
            _ensure_column(conn, "multibaggers", "super_investors", "TEXT")
            # V3.1 columns
            _ensure_column(conn, "multibaggers", "data_quality", "REAL")
            _ensure_column(conn, "multibaggers", "data_confidence", "REAL")
            _ensure_column(conn, "multibaggers", "f_score_method", "TEXT")
            
            # Backtest columns
            _ensure_column(conn, "multibaggers", "backtest_cagr", "REAL")
            _ensure_column(conn, "multibaggers", "backtest_win_rate", "REAL")
            _ensure_column(conn, "multibaggers", "backtest_max_dd", "REAL")
            _ensure_column(conn, "multibaggers", "backtest_sharpe", "REAL")
            
            # Hybrid Scoring (ML) columns
            _ensure_column(conn, "multibaggers", "ml_predicted_return", "REAL")
            _ensure_column(conn, "multibaggers", "shap_breakdown", "TEXT")
            
            # 52W Range columns
            _ensure_column(conn, "multibaggers", "high_52w", "REAL")
            _ensure_column(conn, "multibaggers", "low_52w", "REAL")
            
            # Multibagger Hunt columns
            _ensure_column(conn, "multibaggers", "pledge_pct", "REAL")
            _ensure_column(conn, "multibaggers", "piotroski_score", "INTEGER")
            
            # Momentum Features
            _ensure_column(conn, "multibaggers", "ret_1m", "REAL")
            _ensure_column(conn, "multibaggers", "ret_3m", "REAL")
            _ensure_column(conn, "multibaggers", "ret_6m", "REAL")
            _ensure_column(conn, "multibaggers", "vol_breakout", "REAL")
            _ensure_column(conn, "multibaggers", "dist_from_52w_high", "REAL")
            
            # New Fundamental Scores
            _ensure_column(conn, "multibaggers", "roce", "REAL")
            _ensure_column(conn, "multibaggers", "median_pat_growth", "REAL")
            
            # ML Rank Score
            _ensure_column(conn, "multibaggers", "ml_rank_score", "REAL")
            
        _ensure_fundamentals_pit_table(conn)
        conn.commit()
    finally:
        conn.close()


def _write_fundamentals_snapshot(df_db):
    """
    Persist point-in-time fundamentals snapshot for audit-safe historical replay.
    """
    if df_db.empty or "symbol" not in df_db.columns:
        return

    as_of_date = (
        df_db["as_of_date"].iloc[0]
        if "as_of_date" in df_db.columns and not df_db["as_of_date"].empty
        else _normalize_as_of_date()
    )
    as_of_date = _normalize_as_of_date(as_of_date)

    def _to_sql_timestamp(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        # Handles pandas Timestamp without importing pandas-specific types.
        if hasattr(value, "to_pydatetime"):
            try:
                dt_val = value.to_pydatetime()
                return dt_val.isoformat(sep=" ", timespec="seconds")
            except Exception:
                pass
        return str(value)

    records = []
    for _, row in df_db.iterrows():
        records.append(
            (
                row.get("symbol"),
                as_of_date,
                row.get("price"),
                row.get("sector"),
                row.get("score"),
                row.get("sales_cagr_5y"),
                row.get("avg_roe_5y"),
                row.get("pe_ratio"),
                row.get("debt_equity"),
                row.get("market_cap_cr"),
                row.get("cfo_pat_ratio"),
                row.get("high_52w"),
                row.get("low_52w"),
                row.get("roce"),
                row.get("median_pat_growth"),
                row.get("ret_1m"),
                row.get("ret_3m"),
                row.get("ret_6m"),
                row.get("vol_breakout"),
                row.get("dist_from_52w_high"),
                row.get("ml_rank_score"),
                _to_sql_timestamp(row.get("updated_at")),
            )
        )

    def _write():
        conn = get_connection()
        try:
            _ensure_fundamentals_pit_table(conn)
            conn.executemany(
                """
                INSERT OR REPLACE INTO fundamentals_pit
                (
                    symbol, as_of_date, price, sector, score,
                    sales_cagr_5y, avg_roe_5y, pe_ratio, debt_equity,
                    market_cap_cr, cfo_pat_ratio, high_52w, low_52w,
                    roce, median_pat_growth, ret_1m, ret_3m, ret_6m,
                    vol_breakout, dist_from_52w_high, ml_rank_score, source_updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            conn.commit()
        finally:
            conn.close()

    _run_sqlite_write_with_retry(_write, "fundamentals_pit snapshot upsert")

    # --- PIT Auditor Integration ---
    try:
        from modules.pit_auditor import PITDataStore
        pit_store = PITDataStore()
        for idx, row in df_db.iterrows():
            sym = row.get("symbol")
            if not sym: continue
            
            source = "ScreenerLive"
            # In live scans, the report date is when we pulled it (updated_at)
            report_dt = str(row.get("updated_at", as_of_date)) 
            
            metrics = {
                "score": row.get("score"),
                "sales_cagr_5y": row.get("sales_cagr_5y"),
                "avg_roe_5y": row.get("avg_roe_5y"),
                "pe_ratio": row.get("pe_ratio"),
                "debt_equity": row.get("debt_equity"),
                "cfo_pat_ratio": row.get("cfo_pat_ratio"),
                "market_cap_cr": row.get("market_cap_cr")
            }
            
            for m_name, m_val in metrics.items():
                if m_val is not None:
                    # Mathematical cast avoids DB type errors
                    pit_store.insert_record(
                        sym, m_name, float(m_val), report_dt, as_of_date, source
                    )
        pit_store.close()
    except Exception as e:
        print(f"Warning: PITDataStore sync failed: {e}")


def _backfill_fundamentals_pit_from_multibaggers():
    """
    One-time migration helper:
    if PIT table is empty but multibaggers has rows, seed PIT from latest universe.
    """
    conn = get_connection()
    try:
        if not _table_exists(conn, "multibaggers"):
            return
        _ensure_fundamentals_pit_table(conn)

        pit_count = conn.execute("SELECT COUNT(*) FROM fundamentals_pit").fetchone()[0]
        if pit_count > 0:
            return

        source = pd.read_sql(
            """
            SELECT symbol, price, sector, score, sales_cagr_5y, avg_roe_5y,
                   pe_ratio, debt_equity, market_cap_cr, cfo_pat_ratio,
                   as_of_date, updated_at
            FROM multibaggers
            """,
            conn,
        )
        if source.empty:
            return

        source["as_of_date"] = source["as_of_date"].apply(_normalize_as_of_date)
        records = [
            (
                row["symbol"],
                row["as_of_date"],
                row.get("price"),
                row.get("sector"),
                row.get("score"),
                row.get("sales_cagr_5y"),
                row.get("avg_roe_5y"),
                row.get("pe_ratio"),
                row.get("debt_equity"),
                row.get("market_cap_cr"),
                row.get("cfo_pat_ratio"),
                str(row.get("updated_at")) if row.get("updated_at") is not None else None,
            )
            for _, row in source.iterrows()
        ]

        conn.executemany(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (
                symbol, as_of_date, price, sector, score,
                sales_cagr_5y, avg_roe_5y, pe_ratio, debt_equity,
                market_cap_cr, cfo_pat_ratio, source_updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        conn.commit()
    finally:
        conn.close()


def get_fundamentals_snapshot_as_of(symbol, as_of_date=None):
    target_date = _normalize_as_of_date(as_of_date)
    conn = get_connection()
    try:
        _ensure_fundamentals_pit_table(conn)
        query = """
            SELECT *
            FROM fundamentals_pit
            WHERE symbol = ? AND as_of_date <= ?
            ORDER BY as_of_date DESC
            LIMIT 1
        """
        df = pd.read_sql(query, conn, params=(symbol, target_date))
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    finally:
        conn.close()


def load_fundamentals_universe_as_of(as_of_date=None):
    """
    Load full universe snapshot at latest available date <= as_of_date.
    Returns: (dataframe, snapshot_date)
    """
    target_date = _normalize_as_of_date(as_of_date)
    conn = get_connection()
    try:
        _ensure_fundamentals_pit_table(conn)
        snapshot_df = pd.read_sql(
            """
            SELECT MAX(as_of_date) as snapshot_date
            FROM fundamentals_pit
            WHERE as_of_date <= ?
            """,
            conn,
            params=(target_date,),
        )
        snapshot_date = snapshot_df.iloc[0]["snapshot_date"]
        if not snapshot_date:
            return pd.DataFrame(), None
        universe = pd.read_sql(
            "SELECT * FROM fundamentals_pit WHERE as_of_date = ?",
            conn,
            params=(snapshot_date,),
        )
        return universe, snapshot_date
    finally:
        conn.close()

def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _is_sqlite_lock_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg


def _run_sqlite_write_with_retry(write_fn, operation_name):
    for attempt in range(SQLITE_WRITE_RETRIES):
        try:
            return write_fn()
        except sqlite3.OperationalError as exc:
            if _is_sqlite_lock_error(exc) and attempt < SQLITE_WRITE_RETRIES - 1:
                wait = SQLITE_RETRY_BASE_SECONDS * (2 ** attempt)
                print(f"SQLite lock during {operation_name}; retrying in {wait:.2f}s.")
                time.sleep(wait)
                continue
            raise


def prune_fundamentals_pit_retention(keep_days=PIT_RETENTION_DAYS):
    """
    Retention policy for PIT snapshots.
    Keeps snapshots for `keep_days` and deletes older rows.
    Returns number of deleted rows.
    """
    if keep_days is None:
        return 0

    try:
        keep_days_int = int(keep_days)
    except (TypeError, ValueError):
        keep_days_int = PIT_RETENTION_DAYS

    if keep_days_int <= 0:
        return 0

    cutoff_date = (datetime.now().date() - pd.Timedelta(days=keep_days_int)).isoformat()

    def _prune():
        conn = get_connection()
        try:
            _ensure_fundamentals_pit_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM fundamentals_pit WHERE as_of_date < ?",
                (cutoff_date,),
            )
            deleted = cursor.rowcount if cursor.rowcount is not None else 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    return _run_sqlite_write_with_retry(_prune, "fundamentals_pit retention prune")


def init_db():
    """Initialize the database tables."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Multibagger Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS multibaggers (
            symbol TEXT PRIMARY KEY,
            price REAL,
            sector TEXT,
            score INTEGER,
            f_score INTEGER,
            rating TEXT,
            buy_below REAL,
            stop_loss REAL,
            target_1 REAL,
            target_2 REAL,
            sales_growth REAL,
            roe REAL,
            peg_ratio REAL,
            debt_equity REAL,
            rsi REAL,
            smart_money REAL,
            market_cap_cr REAL,
            cfo_pat_ratio REAL,
            sales_cagr_5y REAL,
            avg_roe_5y REAL,
            pe_ratio REAL,
            down_from_52w REAL,
            rs_rating REAL,
            earnings_accel INTEGER,
            sector_leader INTEGER,
            graham_number REAL,
            value_gap REAL,
            technical_signal TEXT,
            analyst_rating TEXT,
            analyst_upside REAL,
            promoter_holding REAL,
            inst_holding REAL,
            atr REAL,
            stop_loss_atr REAL,
            max_qty_1l REAL,
            as_of_date TEXT,
            last_audited TIMESTAMP,
            updated_at TIMESTAMP,
            conviction_score REAL,
            conviction_boost REAL,
            institutional_interest INTEGER,
            super_investors TEXT,
            backtest_cagr REAL,
            backtest_win_rate REAL,
            backtest_max_dd REAL,
            backtest_sharpe REAL,
            high_52w REAL,
            low_52w REAL,
            pledge_pct REAL,
            piotroski_score INTEGER,
            CHECK(pe_ratio >= -100 AND pe_ratio <= 1000),
            CHECK(roe >= -500 AND roe <= 500),
            CHECK(score >= 0 AND score <= 100)
        )
    ''')
    # Institutional Auditing: Score History
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_score REAL,
            close_price REAL,
            pe_ratio REAL,
            FOREIGN KEY (symbol) REFERENCES multibaggers (symbol)
        )
    ''')

    # Institutional Auditing: Factor Penalties
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS factor_penalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            penalty_name TEXT,
            penalty_value REAL,
            FOREIGN KEY (symbol) REFERENCES multibaggers (symbol)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS valuation_metrics (
            symbol TEXT PRIMARY KEY,
            dcf_value REAL,
            graham_value REAL,
            epv_value REAL,
            intrinsic_value REAL,
            margin_of_safety REAL,
            verdict TEXT,
            confidence_score INTEGER,
            as_of_date TEXT,
            calculated_at TIMESTAMP,
            FOREIGN KEY (symbol) REFERENCES multibaggers (symbol)
        )
    ''')
    
    # Microcap Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS microcaps (
            symbol TEXT PRIMARY KEY,
            price REAL,
            score INTEGER,
            market_cap REAL,
            sales_growth REAL,
            promoter_holding REAL,
            buy_zone TEXT,
            stop_loss REAL,
            target_1 REAL,
            target_2 REAL,
            updated_at TIMESTAMP
        )
    ''')

    # Phase 50: Slippage Auto-Calibration
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            side TEXT,
            expected_price REAL,
            fill_price REAL,
            slippage_bps REAL,
            liquidity_tier TEXT,
            regime TEXT,
            vix REAL,
            timestamp TIMESTAMP,
            source TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS slippage_metrics (
            tier TEXT,
            time_window TEXT,
            regime TEXT,
            p50_bps REAL,
            p75_bps REAL,
            p95_bps REAL,
            count INTEGER,
            updated_at TIMESTAMP,
            PRIMARY KEY (tier, time_window, regime)
        )
    ''')

    # Phase 67: Point-in-time fundamentals snapshot table.
    _ensure_fundamentals_pit_table(conn)

    # Thesis Break Detection: buy_thesis table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buy_thesis (
            symbol TEXT PRIMARY KEY,
            buy_date TEXT,
            primary_driver TEXT,
            revenue_growth_min REAL,
            operating_margin_min REAL,
            score_at_buy REAL,
            checklist_passes_at_buy INTEGER,
            regime_at_buy TEXT,
            raw_thesis_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    _ensure_runtime_schema()
    _backfill_fundamentals_pit_from_multibaggers()
    prune_fundamentals_pit_retention()
    print(f"Database {DB_NAME} initialized.")

def save_multibaggers(df):
    """Save Multibagger Screener results to DB."""
    if df.empty: return
    conn_exists = get_connection()
    try:
        has_multibaggers = _table_exists(conn_exists, "multibaggers")
    finally:
        conn_exists.close()
    if not has_multibaggers:
        init_db()
    _ensure_runtime_schema()

    # Add timestamp
    df["updated_at"] = datetime.now()
    if "As_Of_Date" in df.columns:
        df["As_Of_Date"] = df["As_Of_Date"].apply(_normalize_as_of_date)
    else:
        df["As_Of_Date"] = _normalize_as_of_date()
    
    # Select cols matching schema
    cols = [
        "Symbol", "Price", "Sector", "Score", "F_Score", "Rating", 
        "Buy_Below", "Stop_Loss", "Target_1", 
        "Sales_Growth_TTM%", "ROE%", "PEG_Ratio", "Debt_Equity", 
        "RSI", "Smart_Money%", 
        "Market_Cap_Cr", "CFO_PAT_Ratio", "Sales_Growth_5Y%", "Avg_ROE_5Y%", 
        "PE_Ratio", "Down_From_52W_High%", "RS_Rating", "Earnings_Accel", "Sector_Leader",
        "Graham_Number", "Value_Gap%", "Technical_Signal",
        "Analyst_Rating", "Analyst_Upside%",
        "Promoter_Holding%", "Inst_Holding%",
        "ATR", "Stop_Loss_ATR", "Max_Qty_1L",
        "As_Of_Date",
        "updated_at",
        "Conviction_Score", "Conviction_Boost", "Institutional_Interest", "Super_Investors",
        "Data_Quality", "Data_Confidence", "F_Score_Method",
        "Backtest_CAGR", "Backtest_Win_Rate", "Backtest_Max_DD", "Backtest_Sharpe",
        "ML_Predicted_Return", "SHAP_Breakdown",
        "High_52W", "Low_52W", "Pledge_Pct", "Piotroski_Score",
        "ROCE_pct", "Median_PAT_Growth_5Y_pct", "ml_rank_score",
        "Ret_1M", "Ret_3M", "Ret_6M", "Vol_Breakout", "Dist_From_52W_High"
    ]
    
    available_cols = [c for c in cols if c in df.columns]
    print(f"DEBUG DB: Saving {len(df)} stocks. Available cols: {available_cols}")
    df_db = df[available_cols].copy()
    
    # Mapping to DB names
    mapping = {
        "Symbol": "symbol", "Price": "price", "Sector": "sector", "Score": "score", "F_Score": "f_score", "Rating": "rating", 
        "Buy_Below": "buy_below", "Stop_Loss": "stop_loss", "Target_1": "target_1", 
        "Sales_Growth_TTM%": "sales_growth", "ROE%": "roe", "PEG_Ratio": "peg_ratio", "Debt_Equity": "debt_equity", 
        "RSI": "rsi", "Smart_Money%": "smart_money", 
        "Market_Cap_Cr": "market_cap_cr", "CFO_PAT_Ratio": "cfo_pat_ratio", "Sales_Growth_5Y%": "sales_cagr_5y", "Avg_ROE_5Y%": "avg_roe_5y", 
        "PE_Ratio": "pe_ratio", "Down_From_52W_High%": "down_from_52w", "RS_Rating": "rs_rating", "Earnings_Accel": "earnings_accel", "Sector_Leader": "sector_leader",
        "Graham_Number": "graham_number", "Value_Gap%": "value_gap", "Technical_Signal": "technical_signal",
        "Analyst_Rating": "analyst_rating", "Analyst_Upside%": "analyst_upside",
        "Promoter_Holding%": "promoter_holding", "Inst_Holding%": "inst_holding",
        "ATR": "atr", "Stop_Loss_ATR": "stop_loss_atr", "Max_Qty_1L": "max_qty_1l",
        "As_Of_Date": "as_of_date",
        "updated_at": "updated_at",
        "Conviction_Score": "conviction_score",
        "Conviction_Boost": "conviction_boost",
        "Institutional_Interest": "institutional_interest",
        "Super_Investors": "super_investors",
        "Data_Quality": "data_quality",
        "Data_Confidence": "data_confidence",
        "F_Score_Method": "f_score_method",
        "Backtest_CAGR": "backtest_cagr",
        "Backtest_Win_Rate": "backtest_win_rate",
        "Backtest_Max_DD": "backtest_max_dd",
        "Backtest_Sharpe": "backtest_sharpe",
        "ML_Predicted_Return": "ml_predicted_return",
        "SHAP_Breakdown": "shap_breakdown",
        "High_52W": "high_52w",
        "Low_52W": "low_52w",
        "Pledge_Pct": "pledge_pct",
        "Piotroski_Score": "piotroski_score",
        "ROCE_pct": "roce",
        "Median_PAT_Growth_5Y_pct": "median_pat_growth",
        "ml_rank_score": "ml_rank_score",
        "Ret_1M": "ret_1m",
        "Ret_3M": "ret_3m",
        "Ret_6M": "ret_6m",
        "Vol_Breakout": "vol_breakout",
        "Dist_From_52W_High": "dist_from_52w_high"
    }
    
    df_db.rename(columns=mapping, inplace=True)
    
    # Preserve existing last_audited if merging is not already done above correctly (logic seems mixed)
    # The original code acted as a full refresh, so we do need to re-attach last_audited.
    # But wait, original code:
    # try: existing = pd.read_sql... merge... except...
    # df_db.to_sql(..., if_exists="replace")
    
    # NEW LOGIC:
    # 1. Fetch existing 'last_audited' timestamps to preserve them
    try:
        conn_read = get_connection()
        try:
            existing_audit = pd.read_sql(
                "SELECT symbol, last_audited FROM multibaggers", conn_read
            )
        finally:
            conn_read.close()
        # Merge to keep old audit timestamps if new data doesn't have it
        if "last_audited" not in df_db.columns:
             df_db = df_db.merge(existing_audit, on="symbol", how="left")
        else:
            if df_db['last_audited'].isnull().all():
                 df_db = df_db.drop(columns=['last_audited'])
                 df_db = df_db.merge(existing_audit, on="symbol", how="left")

    except Exception as e:
        print(f"Warning preserving audit logs: {e}")
        # traceback.print_exc() # Removed during strip but would be here
    
    print(f"DEBUG DB: Post-merge df_db columns: {df_db.columns.tolist()}")

    # Phase 3: Outlier Protection Capping
    if "pe_ratio" in df_db.columns:
        df_db["pe_ratio"] = df_db["pe_ratio"].clip(lower=-100, upper=1000)
    if "roe" in df_db.columns:
        df_db["roe"] = df_db["roe"].clip(lower=-500, upper=500)
    if "score" in df_db.columns:
        df_db["score"] = df_db["score"].clip(lower=0, upper=100)

    # 2. De-duplicate input DF just in case
    df_db = df_db.drop_duplicates(subset=['symbol'], keep='first')

    def _write_all():
        conn_write = get_connection()
        try:
            # 3. Clear only the stocks being updated to prevent duplicate PRIMARY KEY errors
            # instead of deleting the entire table. This enables consolidation.
            cursor = conn_write.cursor()
            symbols_to_update = df_db['symbol'].tolist()
            if symbols_to_update:
                placeholders = ', '.join(['?'] * len(symbols_to_update))
                cursor.execute(f"DELETE FROM multibaggers WHERE symbol IN ({placeholders})", symbols_to_update)
            
            conn_write.commit()
            # 4. Append new data.
            print(f"DEBUG DB: Writing {len(df_db)} rows to multibaggers...")
            df_db.to_sql("multibaggers", conn_write, if_exists="append", index=False)
            print("DEBUG DB: Write successful.")
            
            # Phase 1: Persist Score History
            print(f"DEBUG DB: checking score history. score in df_db: {'score' in df_db.columns}, symbol in df_db: {'symbol' in df_db.columns}")
            if "score" in df_db.columns and "symbol" in df_db.columns:
                history_records = []
                for _, row in df_db.iterrows():
                    history_records.append((
                        row["symbol"],
                        row.get("score"),
                        row.get("price"),
                        row.get("pe_ratio")
                    ))
                cursor.executemany('''
                    INSERT INTO score_history (symbol, total_score, close_price, pe_ratio)
                    VALUES (?, ?, ?, ?)
                ''', history_records)
                
            # Phase 1: Persist Factor Penalties
            print(f"DEBUG DB: checking factor_penalties in df. factor_penalties in cols: {'factor_penalties' in df.columns}, Symbol in cols: {'Symbol' in df.columns}")
            if "factor_penalties" in df.columns and "Symbol" in df.columns:
                import ast
                penalty_records = []
                for _, row in df.iterrows():
                    symbol = row["Symbol"]
                    penalties = row.get("factor_penalties", [])
                    
                    if isinstance(penalties, str):
                        try:
                            penalties = ast.literal_eval(penalties)
                        except:
                            penalties = []
                            
                    if isinstance(penalties, list):
                        for p in penalties:
                            penalty_records.append((
                                symbol, 
                                p.get("name"), 
                                p.get("value")
                            ))
                if penalty_records:
                    cursor.executemany('''
                        INSERT INTO factor_penalties (symbol, penalty_name, penalty_value)
                        VALUES (?, ?, ?)
                    ''', penalty_records)
            
            conn_write.commit()
        finally:
            conn_write.close()

    _run_sqlite_write_with_retry(_write_all, "save_multibaggers")
    _write_fundamentals_snapshot(df_db)
    try:
        prune_fundamentals_pit_retention()
    except Exception as exc:
        print(f"Warning: PIT retention prune skipped: {exc}")
    print("Saved Multibaggers to SQLite (Schema Preserved).")

def save_microcaps(df):
    """Save Microcap Screener results to DB."""
    if df.empty: return
    
    conn = get_connection()
    df["updated_at"] = datetime.now()
    
    cols = ["Symbol", "Price", "Score", "MarketCap_Cr", "Sales_Growth%", "Promoter_Hol%", "Buy_Zone", "Stop_Loss", "Target_1", "Target_2", "updated_at"]
    
    df_db = df[cols].copy()
    df_db.columns = ["symbol", "price", "score", "market_cap", "sales_growth", "promoter_holding", "buy_zone", "stop_loss", "target_1", "target_2", "updated_at"]
    
    df_db.to_sql("microcaps", conn, if_exists="replace", index=False)
    conn.close()
    print("Saved Microcaps to SQLite.")

if __name__ == "__main__":
    init_db()
