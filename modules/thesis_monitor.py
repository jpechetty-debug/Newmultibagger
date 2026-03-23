"""
Thesis Break Detection Module
Records buy thesis at purchase and monitors for thesis breaks per stock.
Hedge-fund-grade investment thesis monitoring.
"""

import json
import sqlite3
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

DB_NAME = "stocks.db"
DB_BUSY_TIMEOUT_MS = 5000


def _get_conn():
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_thesis_table():
    """Create buy_thesis table if it doesn't exist."""
    conn = _get_conn()
    try:
        conn.execute("""
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
        """)
        conn.commit()
    finally:
        conn.close()


@dataclass
class ThesisBreak:
    metric: str
    threshold: float
    current_value: float
    message: str


@dataclass
class ThesisStatus:
    symbol: str
    status: str  # "INTACT", "WARNING", "THESIS_BREAK"
    breaks: List[Dict] = field(default_factory=list)
    thesis_age_days: int = 0
    score_at_buy: float = 0.0
    score_now: float = 0.0
    primary_driver: str = ""
    regime_at_buy: str = ""
    badge_color: str = "green"  # green, yellow, red

    def to_dict(self):
        return asdict(self)


def record_buy_thesis(symbol: str, stock_data: dict, score: float,
                      checklist_passes: int = 0, regime: str = "SIDEWAYS"):
    """
    Record the investment thesis at time of purchase.
    Called automatically when a BUY order is placed.

    Args:
        symbol: Stock symbol (e.g., "TCS.NS")
        stock_data: Dict with fundamental data from screener
        score: Composite score at time of buy
        checklist_passes: Number of checklist items passed
        regime: Market regime at time of buy
    """
    ensure_thesis_table()

    # Extract key metrics for thesis thresholds
    # Revenue growth: use 80% of current as minimum threshold
    rev_growth = stock_data.get("Sales_Growth_TTM%", 0) or stock_data.get("Sales_Growth_5Y%", 0) or 0
    revenue_growth_min = round(rev_growth * 0.8, 1) if rev_growth > 0 else 0

    # Operating margin: use current profit margin as baseline
    profit_margin = stock_data.get("Profit_Margin%", 0) or 0
    operating_margin_min = round(profit_margin * 0.8, 1) if profit_margin > 0 else 0

    # Build primary driver description
    sector = stock_data.get("Sector", "Unknown")
    industry = stock_data.get("Industry", "Unknown")

    drivers = []
    if rev_growth > 15:
        drivers.append("strong revenue growth")
    if stock_data.get("Avg_ROE_5Y%", 0) > 20:
        drivers.append("high ROE")
    if stock_data.get("F_Score", 0) >= 7:
        drivers.append("financial fortress")
    if stock_data.get("Value_Gap%", 0) > 20:
        drivers.append("undervalued")
    if stock_data.get("Promoter_Holding%", 0) > 60:
        drivers.append("owner-operator")
    if stock_data.get("EPS_Growth%", 0) > 15:
        drivers.append("earnings acceleration")

    primary_driver = f"{industry}: {', '.join(drivers)}" if drivers else f"{industry} play"

    # Build full thesis JSON
    raw_thesis = {
        "symbol": symbol,
        "buy_thesis": {
            "primary_driver": primary_driver,
            "sector": sector,
            "industry": industry,
            "key_metrics_to_watch": {
                "revenue_growth_min": revenue_growth_min,
                "operating_margin_min": operating_margin_min,
            },
            "snapshot_at_buy": {
                "price": stock_data.get("Price", 0),
                "pe_ratio": stock_data.get("PE_Ratio", 0),
                "roe": stock_data.get("ROE%", 0),
                "avg_roe_5y": stock_data.get("Avg_ROE_5Y%", 0),
                "sales_growth_ttm": stock_data.get("Sales_Growth_TTM%", 0),
                "sales_growth_5y": stock_data.get("Sales_Growth_5Y%", 0),
                "debt_equity": stock_data.get("Debt_Equity", 0),
                "f_score": stock_data.get("F_Score", 0),
                "cfo_pat_ratio": stock_data.get("CFO_PAT_Ratio", 0),
                "promoter_holding": stock_data.get("Promoter_Holding%", 0),
                "rs_rating": stock_data.get("RS_Rating", 0),
            },
            "checklist_passes_at_buy": checklist_passes,
            "score_at_buy": score,
            "regime_at_buy": regime,
        },
    }

    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO buy_thesis
            (symbol, buy_date, primary_driver, revenue_growth_min,
             operating_margin_min, score_at_buy,
             checklist_passes_at_buy, regime_at_buy, raw_thesis_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                datetime.now().date().isoformat(),
                primary_driver,
                revenue_growth_min,
                operating_margin_min,
                score,
                checklist_passes,
                regime,
                json.dumps(raw_thesis, indent=2),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        print(f"  📋 Thesis recorded for {symbol}: {primary_driver}")
    finally:
        conn.close()


def check_thesis(symbol: str) -> ThesisStatus:
    """
    Check if the investment thesis still holds for a stock.
    Compares current fundamentals against recorded buy thesis thresholds.

    Returns ThesisStatus with status, breaks, and badge color.
    """
    ensure_thesis_table()

    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM buy_thesis WHERE symbol = ?", (symbol,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return ThesisStatus(
            symbol=symbol,
            status="NO_THESIS",
            badge_color="gray",
        )

    # Load thesis data
    buy_date_str = row["buy_date"] or datetime.now().date().isoformat()
    try:
        buy_date = datetime.fromisoformat(buy_date_str).date()
    except (ValueError, TypeError):
        buy_date = datetime.now().date()
    thesis_age = (datetime.now().date() - buy_date).days

    score_at_buy = row["score_at_buy"] or 0
    revenue_growth_min = row["revenue_growth_min"] or 0
    operating_margin_min = row["operating_margin_min"] or 0
    primary_driver = row["primary_driver"] or ""
    regime_at_buy = row["regime_at_buy"] or ""
    checklist_at_buy = row["checklist_passes_at_buy"] or 0

    # Fetch current fundamentals from multibaggers table
    conn = _get_conn()
    try:
        current = conn.execute(
            "SELECT * FROM multibaggers WHERE symbol = ?", (symbol,)
        ).fetchone()
    finally:
        conn.close()

    if not current:
        return ThesisStatus(
            symbol=symbol,
            status="NO_DATA",
            thesis_age_days=thesis_age,
            score_at_buy=score_at_buy,
            primary_driver=primary_driver,
            regime_at_buy=regime_at_buy,
            badge_color="gray",
        )

    score_now = current["score"] or 0
    breaks = []

    # --- THESIS BREAK CHECKS ---

    # 1. Revenue Growth Check
    current_sales_growth = current["sales_growth"] or 0
    if revenue_growth_min > 0 and current_sales_growth < revenue_growth_min:
        breaks.append({
            "metric": "Revenue Growth",
            "threshold": revenue_growth_min,
            "current_value": current_sales_growth,
            "message": f"THESIS BREAK: Growth deceleration detected "
                       f"({current_sales_growth:.1f}% < min {revenue_growth_min:.1f}%)",
        })

    # 2. Operating Margin Check
    # We don't have operating margin directly in multibaggers, approximate with ROE trend
    # Load raw thesis for snapshot comparison
    raw_thesis = {}
    try:
        raw_thesis = json.loads(row["raw_thesis_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        pass

    snapshot = raw_thesis.get("buy_thesis", {}).get("snapshot_at_buy", {})

    # 3. Score Deterioration
    if score_at_buy > 0 and score_now < score_at_buy * 0.7:
        breaks.append({
            "metric": "Composite Score",
            "threshold": round(score_at_buy * 0.7, 1),
            "current_value": score_now,
            "message": f"THESIS BREAK: Score collapsed from {score_at_buy:.1f} to {score_now:.1f} "
                       f"(>{30}% drop)",
        })

    # 4. ROE Deterioration
    roe_at_buy = snapshot.get("avg_roe_5y", 0) or snapshot.get("roe", 0)
    current_roe = current["roe"] or 0
    if roe_at_buy > 15 and current_roe < roe_at_buy * 0.6:
        breaks.append({
            "metric": "ROE",
            "threshold": round(roe_at_buy * 0.6, 1),
            "current_value": current_roe,
            "message": f"THESIS BREAK: Profitability collapse "
                       f"(ROE {current_roe:.1f}% vs buy {roe_at_buy:.1f}%)",
        })

    # 5. F-Score Deterioration
    f_score_at_buy = snapshot.get("f_score", 0)
    current_f_score = current["f_score"] or 0
    if f_score_at_buy >= 6 and current_f_score <= 3:
        breaks.append({
            "metric": "F-Score",
            "threshold": 4,
            "current_value": current_f_score,
            "message": f"THESIS BREAK: Financial quality collapsed "
                       f"(F-Score {current_f_score} vs buy {f_score_at_buy})",
        })

    # 6. Debt Spike
    de_at_buy = snapshot.get("debt_equity", 0)
    current_de = current["debt_equity"] or 0
    if de_at_buy < 0.5 and current_de > 1.0:
        breaks.append({
            "metric": "Debt/Equity",
            "threshold": 1.0,
            "current_value": current_de,
            "message": f"THESIS BREAK: Leverage spike "
                       f"(D/E {current_de:.2f} vs buy {de_at_buy:.2f})",
        })

    # 7. Promoter Exit
    prom_at_buy = snapshot.get("promoter_holding", 0)
    current_prom = current["promoter_holding"] or 0
    if prom_at_buy > 50 and current_prom < prom_at_buy * 0.8:
        breaks.append({
            "metric": "Promoter Holding",
            "threshold": round(prom_at_buy * 0.8, 1),
            "current_value": current_prom,
            "message": f"THESIS BREAK: Promoter reducing stake "
                       f"({current_prom:.1f}% vs buy {prom_at_buy:.1f}%)",
        })

    # Determine status
    if len(breaks) >= 2:
        status = "THESIS_BREAK"
        badge_color = "red"
    elif len(breaks) == 1:
        status = "WARNING"
        badge_color = "yellow"
    else:
        status = "INTACT"
        badge_color = "green"

    return ThesisStatus(
        symbol=symbol,
        status=status,
        breaks=breaks,
        thesis_age_days=thesis_age,
        score_at_buy=score_at_buy,
        score_now=score_now,
        primary_driver=primary_driver,
        regime_at_buy=regime_at_buy,
        badge_color=badge_color,
    )


def check_all_thesis_breaks() -> List[Dict]:
    """
    Check thesis status for ALL stocks with recorded thesis.
    Returns list of thesis statuses, sorted by severity.
    """
    ensure_thesis_table()

    conn = _get_conn()
    try:
        rows = conn.execute("SELECT symbol FROM buy_thesis").fetchall()
    finally:
        conn.close()

    results = []
    for row in rows:
        status = check_thesis(row["symbol"])
        results.append(status.to_dict())

    # Sort: THESIS_BREAK first, then WARNING, then INTACT
    priority = {"THESIS_BREAK": 0, "WARNING": 1, "INTACT": 2, "NO_DATA": 3, "NO_THESIS": 4}
    results.sort(key=lambda x: priority.get(x["status"], 5))

    return results


def get_thesis_summary(symbol: str) -> Optional[Dict]:
    """Get the raw thesis JSON for a symbol."""
    ensure_thesis_table()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT raw_thesis_json FROM buy_thesis WHERE symbol = ?", (symbol,)
        ).fetchone()
    finally:
        conn.close()

    if row and row["raw_thesis_json"]:
        try:
            return json.loads(row["raw_thesis_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return None
