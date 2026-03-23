import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database


def _sample_universe():
    return pd.DataFrame(
        [
            {
                "Symbol": "AAA.NS",
                "Price": 100.0,
                "Sector": "Technology",
                "Score": 82,
                "Sales_Growth_5Y%": 14.0,
                "Avg_ROE_5Y%": 19.0,
                "PE_Ratio": 22.0,
                "Debt_Equity": 0.2,
                "Market_Cap_Cr": 1200.0,
                "CFO_PAT_Ratio": 1.4,
            },
            {
                "Symbol": "BBB.NS",
                "Price": 200.0,
                "Sector": "Financial",
                "Score": 78,
                "Sales_Growth_5Y%": 11.5,
                "Avg_ROE_5Y%": 17.5,
                "PE_Ratio": 16.0,
                "Debt_Equity": 0.4,
                "Market_Cap_Cr": 2200.0,
                "CFO_PAT_Ratio": 1.1,
            },
        ]
    )


def test_save_multibaggers_writes_pit_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    database.save_multibaggers(_sample_universe())

    conn = database.get_connection()
    try:
        multibaggers = pd.read_sql(
            "SELECT symbol, as_of_date FROM multibaggers ORDER BY symbol",
            conn,
        )
        pit = pd.read_sql(
            """
            SELECT symbol, as_of_date, sales_cagr_5y, avg_roe_5y
            FROM fundamentals_pit
            ORDER BY symbol
            """,
            conn,
        )
    finally:
        conn.close()

    assert len(multibaggers) == 2
    assert len(pit) == 2
    assert all(isinstance(v, str) and len(v) == 10 for v in multibaggers["as_of_date"])
    assert list(pit["symbol"]) == ["AAA.NS", "BBB.NS"]


def test_load_fundamentals_universe_as_of_returns_latest_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67_lookup.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    conn = database.get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (symbol, as_of_date, score, sales_cagr_5y, avg_roe_5y)
            VALUES
            ('AAA.NS', '2026-01-01', 70, 10.0, 15.0),
            ('AAA.NS', '2026-01-15', 80, 12.0, 18.0),
            ('BBB.NS', '2026-01-15', 75, 11.0, 16.0)
            """
        )
        conn.commit()
    finally:
        conn.close()

    df_old, snap_old = database.load_fundamentals_universe_as_of("2026-01-10")
    df_new, snap_new = database.load_fundamentals_universe_as_of("2026-01-31")

    assert snap_old == "2026-01-01"
    assert len(df_old) == 1
    assert df_old.iloc[0]["symbol"] == "AAA.NS"

    assert snap_new == "2026-01-15"
    assert set(df_new["symbol"].tolist()) == {"AAA.NS", "BBB.NS"}


def test_pit_retention_prunes_old_snapshots(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67_retention.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    conn = database.get_connection()
    try:
        today = datetime.now().date().isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (symbol, as_of_date, score)
            VALUES
            ('OLD.NS', '2000-01-01', 50),
            ('NEW.NS', ?, 90)
            """,
            (today,),
        )
        conn.commit()
    finally:
        conn.close()

    deleted = database.prune_fundamentals_pit_retention(keep_days=30)

    conn = database.get_connection()
    try:
        remaining = pd.read_sql(
            "SELECT symbol, as_of_date FROM fundamentals_pit ORDER BY symbol",
            conn,
        )
    finally:
        conn.close()

    assert deleted == 1
    assert len(remaining) == 1
    assert remaining.iloc[0]["symbol"] == "NEW.NS"
