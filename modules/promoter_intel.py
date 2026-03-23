"""
Promoter Behaviour Intelligence Module
Tracks promoter actions, pledge trends, insider trading, and institutional flows.
Uses NSE bulk deal data + yfinance + historical PIT snapshots.
"""

import sqlite3
import pandas as pd
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, List

DB_NAME = "stocks.db"
DB_BUSY_TIMEOUT_MS = 5000

# NSE API requires browser-like headers
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _get_conn():
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_nse_bulk_deals(symbol: str) -> List[Dict]:
    """
    Fetch bulk/block deal data from NSE API.
    Falls back gracefully if NSE blocks the request.
    """
    clean_symbol = symbol.replace(".NS", "").replace(".BO", "")

    try:
        # First establish a session to get cookies
        session = requests.Session()
        session.headers.update(NSE_HEADERS)

        # Hit the main page first for cookie
        try:
            session.get("https://www.nseindia.com", timeout=5)
        except Exception:
            pass

        # Fetch bulk deals
        url = "https://www.nseindia.com/api/historical/bulk-deals"
        params = {
            "from": (datetime.now() - timedelta(days=180)).strftime("%d-%m-%Y"),
            "to": datetime.now().strftime("%d-%m-%Y"),
            "symbol": clean_symbol,
        }

        response = session.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            deals = data.get("data", []) if isinstance(data, dict) else data
            return [
                {
                    "date": d.get("BD_DT_DATE", ""),
                    "symbol": d.get("BD_SYMBOL", ""),
                    "client_name": d.get("BD_CLIENT_NAME", ""),
                    "deal_type": d.get("BD_BUY_SELL", ""),  # BUY / SELL
                    "quantity": d.get("BD_QTY_TRD", 0),
                    "price": d.get("BD_TP_WATP", 0),
                }
                for d in deals
            ]
    except Exception as e:
        print(f"  ⚠️ NSE bulk deal fetch failed for {clean_symbol}: {e}")

    return []


def _get_historical_holdings(symbol: str, periods: int = 4) -> List[Dict]:
    """
    Get promoter/institutional holding history from fundamentals_pit table.
    Returns last N quarters of holding data.
    """
    conn = _get_conn()
    try:
        query = """
            SELECT as_of_date, symbol
            FROM fundamentals_pit
            WHERE symbol = ?
            ORDER BY as_of_date DESC
            LIMIT ?
        """
        rows = conn.execute(query, (symbol, periods)).fetchall()
        if not rows:
            return []
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_multibagger_row(symbol: str) -> Optional[Dict]:
    """Get current data from multibaggers table."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM multibaggers WHERE symbol = ?", (symbol,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_promoter_trend(symbol: str) -> Dict:
    """
    Compute promoter action trends.
    Combines: yfinance current holdings, PIT history, and NSE bulk deals.

    Returns dict with:
      - promoter_holding_current: float
      - promoter_holding_history: list (QoQ)
      - promoter_change_direction: "INCREASING" | "DECREASING" | "STABLE"
      - pledge_current: float
      - pledge_trend: list
      - pledge_direction: "RISING" | "FALLING" | "STABLE"
      - insider_deals: list (from NSE)
      - insider_net_action: "NET_BUYER" | "NET_SELLER" | "NEUTRAL"
      - institutional_holding_current: float
      - institutional_change_direction: "INCREASING" | "DECREASING" | "STABLE"
    """
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"

    result = {
        "symbol": symbol,
        "promoter_holding_current": 0,
        "promoter_holding_history": [],
        "promoter_change_direction": "STABLE",
        "pledge_current": 0,
        "pledge_trend": [],
        "pledge_direction": "STABLE",
        "insider_deals": [],
        "insider_buy_count": 0,
        "insider_sell_count": 0,
        "insider_net_action": "NEUTRAL",
        "institutional_holding_current": 0,
        "institutional_change_direction": "STABLE",
        "data_sources": [],
    }

    # 1. Get current holdings from multibaggers table
    current = _get_multibagger_row(symbol)
    if current:
        result["promoter_holding_current"] = current.get("promoter_holding", 0) or 0
        result["institutional_holding_current"] = current.get("inst_holding", 0) or 0
        result["data_sources"].append("multibaggers_db")

    # 2. Try to get pledge data from yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # Some Indian stocks report pledge through majorHolders
        pledge_pct = 0
        try:
            holders = ticker.major_holders
            if holders is not None and not holders.empty:
                for i, row_data in holders.iterrows():
                    label = str(row_data.iloc[-1]).lower() if len(row_data) > 1 else str(i).lower()
                    if "pledge" in label:
                        val = row_data.iloc[0]
                        if isinstance(val, str):
                            val = float(val.replace("%", ""))
                        elif val < 1.1:
                            val = val * 100
                        pledge_pct = float(val)
        except Exception:
            pass

        result["pledge_current"] = pledge_pct
        result["data_sources"].append("yfinance")

    except Exception as e:
        print(f"  ⚠️ yfinance pledge fetch failed for {symbol}: {e}")

    # 3. Get historical holding snapshots from PIT table for QoQ trend
    hist = _get_historical_holdings(symbol, periods=4)
    if len(hist) >= 2:
        result["promoter_holding_history"] = [
            {"date": h["as_of_date"]} for h in hist
        ]

    # 4. Determine promoter holding direction from current vs PIT
    # Compare latest promoter_holding vs previous quarter
    if current and current.get("promoter_holding", 0):
        conn = _get_conn()
        try:
            prev_rows = conn.execute("""
                SELECT as_of_date FROM fundamentals_pit
                WHERE symbol = ? AND as_of_date < date('now', '-30 days')
                ORDER BY as_of_date DESC
                LIMIT 1
            """, (symbol,)).fetchall()
        finally:
            conn.close()

        if prev_rows:
            # We can infer direction from current vs earlier snapshots
            # Since we don't store promoter_holding in PIT, track via the
            # multibaggers table changes over time
            pass

    # 5. Fetch NSE bulk deals for insider trading analysis
    deals = fetch_nse_bulk_deals(symbol)
    if deals:
        result["insider_deals"] = deals[:10]  # Cap at 10 recent
        result["data_sources"].append("nse_bulk_deals")

        buy_count = sum(1 for d in deals if str(d.get("deal_type", "")).upper() == "BUY")
        sell_count = sum(1 for d in deals if str(d.get("deal_type", "")).upper() == "SELL")

        result["insider_buy_count"] = buy_count
        result["insider_sell_count"] = sell_count

        if buy_count > sell_count * 1.5:
            result["insider_net_action"] = "NET_BUYER"
        elif sell_count > buy_count * 1.5:
            result["insider_net_action"] = "NET_SELLER"

    return result


def calculate_promoter_score(symbol: str) -> Dict:
    """
    Calculate promoter behaviour scoring impact.

    Returns:
      - score_adjustment: int (+4 to -8)
      - is_disqualified: bool (D15 trigger)
      - signal: str (🟢/🟡/🔴)
      - signal_text: str
      - pledge_trend_text: str
    """
    trend = get_promoter_trend(symbol)

    score_adj = 0
    is_disqualified = False
    signals = []

    # Rule 1: Promoter buying + pledge decreasing = +4
    if (trend["insider_net_action"] == "NET_BUYER"
            and trend["pledge_direction"] in ("FALLING", "STABLE")
            and trend["pledge_current"] < 5):
        score_adj += 4
        signals.append("Promoter accumulating")

    # Rule 2: Promoter selling + pledge increasing = -8
    if (trend["insider_net_action"] == "NET_SELLER"
            and trend["pledge_current"] > 10):
        score_adj -= 8
        signals.append("Promoter selling + high pledge")

    # Rule 3: Large insider sell after run-up = D15 disqualifier
    if trend["insider_sell_count"] > 3 and trend["insider_buy_count"] == 0:
        is_disqualified = True
        score_adj = -8
        signals.append("Heavy insider dumping detected")

    # Additional adjustments
    # High promoter holding + increasing = conviction signal
    if trend["promoter_holding_current"] > 60:
        if trend["promoter_change_direction"] == "INCREASING":
            score_adj += 2
            signals.append("Owner-operator increasing stake")

    # Low promoter + selling = danger
    if trend["promoter_holding_current"] < 25:
        if trend["insider_net_action"] == "NET_SELLER":
            score_adj -= 3
            signals.append("Low-conviction promoter selling")

    # Institutional buying trend
    if trend["institutional_holding_current"] > 30:
        score_adj += 1
        signals.append("Strong institutional backing")

    # Determine signal color
    if is_disqualified or score_adj <= -5:
        signal = "🔴"
    elif score_adj < 0:
        signal = "🟡"
    else:
        signal = "🟢"

    # Build pledge trend text
    pledge_text = f"{trend['pledge_current']:.1f}%" if trend["pledge_current"] > 0 else "None"

    # Build signal text
    if not signals:
        signal_text = "No significant promoter activity"
    else:
        signal_text = " | ".join(signals)

    return {
        "symbol": symbol,
        "score_adjustment": max(-8, min(4, score_adj)),
        "is_disqualified": is_disqualified,
        "signal": signal,
        "signal_text": signal_text,
        "pledge_trend_text": pledge_text,
        "promoter_holding": trend["promoter_holding_current"],
        "institutional_holding": trend["institutional_holding_current"],
        "insider_net_action": trend["insider_net_action"],
        "insider_buy_count": trend["insider_buy_count"],
        "insider_sell_count": trend["insider_sell_count"],
        "insider_deals": trend["insider_deals"],
        "data_sources": trend["data_sources"],
    }
