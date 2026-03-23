import csv
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
import database as database_module
import main
import modules.alpha_vantage as alpha_vantage_module
import modules.financials as financials_module
import modules.market_data as market_data_module
import modules.news as news_module
import modules.peer_analysis as peer_analysis_module
import modules.quarterly_results as quarterly_results_module
import modules.shareholding as shareholding_module
import modules.technicals as technicals_module
import modules.tracker as tracker_module
import modules.valuation as valuation_module
import report_generator


def test_stocks_endpoint_supports_as_of_date(monkeypatch):
    calls = []

    def fake_load_fundamentals_universe_as_of(as_of_date=None):
        calls.append(as_of_date)
        payload = pd.DataFrame(
            [
                {
                    "symbol": "AAA.NS",
                    "score": 88,
                    "as_of_date": "2026-02-10",
                    "sector": "Technology",
                }
            ]
        )
        return payload, "2026-02-10"

    monkeypatch.setattr(
        database_module,
        "load_fundamentals_universe_as_of",
        fake_load_fundamentals_universe_as_of,
    )

    with TestClient(main.app) as client:
        response = client.get("/api/stocks?as_of_date=2026-02-12")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["symbol"] == "AAA.NS"
    assert payload[0]["as_of_date"] == "2026-02-10"
    assert calls == ["2026-02-12"]


def test_reports_endpoint_appends_ns_suffix(monkeypatch):
    seen_symbols = []

    async def fake_generate_analyst_report(symbol: str):
        seen_symbols.append(symbol)
        return "mock report"

    monkeypatch.setattr(
        report_generator, "generate_analyst_report", fake_generate_analyst_report
    )

    with TestClient(main.app) as client:
        response = client.get("/api/reports/RELIANCE")

    assert response.status_code == 200
    assert response.json()["content"] == "mock report"
    assert seen_symbols == ["RELIANCE.NS"]


def test_forensic_file_endpoints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "liquidity.json").write_text(json.dumps({"ok": "liquidity"}), encoding="utf-8")
    (tmp_path / "recovery.json").write_text(json.dumps({"ok": "recovery"}), encoding="utf-8")
    (tmp_path / "thesis_break.json").write_text(
        json.dumps({"ok": "thesis_break"}), encoding="utf-8"
    )

    with TestClient(main.app) as client:
        liquidity = client.get("/api/liquidity")
        recovery = client.get("/api/recovery")
        thesis_break = client.get("/api/thesis_break")

    assert liquidity.status_code == 200
    assert recovery.status_code == 200
    assert thesis_break.status_code == 200
    assert liquidity.json() == {"ok": "liquidity"}
    assert recovery.json() == {"ok": "recovery"}
    assert thesis_break.json() == {"ok": "thesis_break"}


def test_rejections_endpoint_returns_last_20_reversed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "rejected_trades.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Symbol", "Reason", "Price_Context"])
        for i in range(25):
            writer.writerow([f"2026-02-14 12:{i:02d}:00", f"SYM{i}", "Rule", 100 + i])

    with TestClient(main.app) as client:
        response = client.get("/api/rejections")

    payload = response.json()
    assert response.status_code == 200
    assert len(payload) == 20
    assert payload[0]["Symbol"] == "SYM24"
    assert payload[-1]["Symbol"] == "SYM5"


def test_regime_status_and_force_regime(monkeypatch):
    original_forced_regime = config.FORCED_REGIME

    class FakeMarketDataProvider:
        def get_market_regime(self):
            return {
                "regime": "SIDEWAYS",
                "strategy_suggestion": "balanced",
                "details": {"vix": 17.8},
                "votes": {"bull": 1, "bear": 1, "sideways": 1},
            }

    monkeypatch.setattr(
        market_data_module, "MarketDataProvider", FakeMarketDataProvider
    )

    try:
        config.FORCED_REGIME = None
        with TestClient(main.app) as client:
            auto_status = client.get("/api/regime_status")
            force = client.post("/api/admin/force_regime?regime=BULL")
            forced_status = client.get("/api/regime_status")

        assert auto_status.status_code == 200
        assert auto_status.json()["regime"] == "SIDEWAYS"
        assert auto_status.json()["is_forced"] is False

        assert force.status_code == 200
        assert force.json() == {"status": "success", "regime": "BULL"}
        assert config.FORCED_REGIME == "BULL"

        assert forced_status.status_code == 200
        assert forced_status.json()["regime"] == "BULL"
        assert forced_status.json()["is_forced"] is True

        with TestClient(main.app) as client:
            reset = client.post("/api/admin/force_regime?regime=AUTO")

        assert reset.status_code == 200
        assert reset.json() == {"status": "success", "regime": "AUTO"}
        assert config.FORCED_REGIME is None
    finally:
        config.FORCED_REGIME = original_forced_regime


def test_performance_endpoint_shape():
    with TestClient(main.app) as client:
        response = client.get("/api/performance")

    payload = response.json()
    assert response.status_code == 200
    assert set(payload.keys()) == {"strategy", "benchmark", "alpha", "win_rate", "avg_hold"}


def test_news_endpoint_merges_sentiment(monkeypatch):
    async def fake_get_stock_news(symbol: str):
        return [
            {"title": "Strong earnings for RELIANCE", "source": "Mock Wire"},
            {"title": "Sector roundup", "source": "Mock Wire"},
        ]

    class FakeAlphaVantageProvider:
        def get_stock_sentiment(self, symbol: str):
            return {
                "Strong earnings for RELIANCE": {
                    "label": "Bullish",
                    "score": 0.9,
                }
            }

    monkeypatch.setattr(news_module, "get_stock_news", fake_get_stock_news)
    monkeypatch.setattr(
        alpha_vantage_module, "AlphaVantageProvider", FakeAlphaVantageProvider
    )

    with TestClient(main.app) as client:
        response = client.get("/api/news/RELIANCE.NS")

    payload = response.json()
    assert response.status_code == 200
    assert isinstance(payload, list)
    assert payload[0]["sentiment"]["label"] == "Bullish"
    assert payload[0]["sentiment"]["score"] == 0.9
    assert "sentiment" not in payload[1]


def test_market_movers_endpoint(monkeypatch):
    class FakeAlphaVantageProvider:
        def get_market_movers(self):
            return {
                "gainers": [{"ticker": "AAA", "change_percentage": "+9.1%"}],
                "losers": [{"ticker": "BBB", "change_percentage": "-6.2%"}],
                "active": [{"ticker": "CCC", "volume": "1000000"}],
            }

    monkeypatch.setattr(
        alpha_vantage_module, "AlphaVantageProvider", FakeAlphaVantageProvider
    )

    with TestClient(main.app) as client:
        response = client.get("/api/market_movers")

    payload = response.json()
    assert response.status_code == 200
    assert payload["gainers"][0]["ticker"] == "AAA"
    assert payload["losers"][0]["ticker"] == "BBB"
    assert payload["active"][0]["ticker"] == "CCC"


def test_peers_financials_technicals_shareholding_endpoints(monkeypatch):
    async def fake_peers(symbol: str):
        return {"symbol": symbol, "peers": [{"symbol": "TCS.NS"}]}

    def fake_financials(symbol: str):
        return {"symbol": symbol, "timeline": [{"date": "Dec '25", "revenue": 1000.0}]}

    async def fake_technicals(symbol: str):
        return {"symbol": symbol, "trend": "Bullish", "strength_score": 82}

    async def fake_shareholding(symbol: str):
        return {"symbol": symbol, "pattern": {"promoters": 52.1, "institutions": 31.0, "public": 16.9}}

    monkeypatch.setattr(peer_analysis_module, "get_peer_comparison", fake_peers)
    monkeypatch.setattr(financials_module, "get_quarterly_results", fake_financials)
    monkeypatch.setattr(technicals_module, "get_technical_analysis", fake_technicals)
    monkeypatch.setattr(shareholding_module, "get_shareholding_pattern", fake_shareholding)

    with TestClient(main.app) as client:
        peers_resp = client.get("/api/peers/INFY.NS")
        fin_resp = client.get("/api/financials/INFY.NS")
        tech_resp = client.get("/api/technicals/INFY.NS")
        share_resp = client.get("/api/shareholding/INFY.NS")

    assert peers_resp.status_code == 200
    assert fin_resp.status_code == 200
    assert tech_resp.status_code == 200
    assert share_resp.status_code == 200
    assert peers_resp.json()["peers"][0]["symbol"] == "TCS.NS"
    assert fin_resp.json()["timeline"][0]["revenue"] == 1000.0
    assert tech_resp.json()["trend"] == "Bullish"
    assert share_resp.json()["pattern"]["promoters"] == 52.1


def test_quarterly_results_endpoint_success_and_error(monkeypatch):
    calls = []

    async def fake_quarterly(symbol: str, quarters: int):
        calls.append((symbol, quarters))
        return {"symbol": symbol, "quarters": [{"quarter": "Q1FY26"}], "alerts": []}

    monkeypatch.setattr(
        quarterly_results_module, "get_quarterly_timeline", fake_quarterly
    )

    with TestClient(main.app) as client:
        ok_response = client.get("/api/quarterly-results/INFY.NS?quarters=8")

    assert ok_response.status_code == 200
    assert ok_response.json()["symbol"] == "INFY.NS"
    assert calls == [("INFY.NS", 8)]

    async def fake_quarterly_error(symbol: str, quarters: int):
        raise RuntimeError("quarterly failed")

    monkeypatch.setattr(
        quarterly_results_module, "get_quarterly_timeline", fake_quarterly_error
    )

    with TestClient(main.app) as client:
        fail_response = client.get("/api/quarterly-results/INFY.NS?quarters=8")

    assert fail_response.status_code == 500
    assert "Failed to fetch quarterly results:" in fail_response.json()["detail"]
    assert "quarterly failed" in fail_response.json()["detail"]


def test_valuation_endpoint_uses_db_and_returns_metrics(tmp_path, monkeypatch):
    db_path = tmp_path / "valuation_test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE valuation_metrics (
            symbol TEXT PRIMARY KEY,
            dcf_value REAL,
            graham_value REAL,
            epv_value REAL,
            intrinsic_value REAL,
            margin_of_safety REAL,
            verdict TEXT,
            confidence_score REAL,
            calculated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(main, "DB_PATH", str(db_path), raising=False)

    class FakeTicker:
        @property
        def info(self):
            return {
                "currentPrice": 100.0,
                "trailingEps": 8.5,
                "bookValue": 42.0,
                "operatingCashflow": 1_000_000,
                "capitalExpenditures": -200_000,
                "sharesOutstanding": 10_000,
                "earningsGrowth": 0.12,
                "beta": 1.1,
            }

    class FakeValuationEngine:
        def __init__(self, data):
            self.data = data

        def get_intrinsic_value(self):
            return {
                "intrinsic_value": 140.0,
                "margin_of_safety": 28.6,
                "components": {"dcf": 150.0, "graham": 130.0, "epv": 120.0},
                "verdict": "UNDERVALUED",
            }

    monkeypatch.setattr(main.yf, "Ticker", lambda _symbol: FakeTicker())
    monkeypatch.setattr(valuation_module, "ValuationEngine", FakeValuationEngine)

    with TestClient(main.app) as client:
        response = client.get("/api/valuation/RELIANCE.NS")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intrinsic_value"] == 140.0
    assert payload["components"]["dcf"] == 150.0
    assert payload["verdict"] == "UNDERVALUED"

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT symbol, intrinsic_value, verdict FROM valuation_metrics WHERE symbol = ?",
        ("RELIANCE.NS",),
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "RELIANCE.NS"
    assert row[1] == 140.0
    assert row[2] == "UNDERVALUED"


def test_valuation_endpoint_cached_payload_shape(tmp_path, monkeypatch):
    db_path = tmp_path / "valuation_cached.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE valuation_metrics (
            symbol TEXT PRIMARY KEY,
            dcf_value REAL,
            graham_value REAL,
            epv_value REAL,
            intrinsic_value REAL,
            margin_of_safety REAL,
            verdict TEXT,
            confidence_score REAL,
            as_of_date TEXT,
            calculated_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO valuation_metrics
        (symbol, dcf_value, graham_value, epv_value, intrinsic_value, margin_of_safety, verdict, confidence_score, as_of_date, calculated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "RELIANCE.NS",
            150.0,
            130.0,
            120.0,
            140.0,
            28.6,
            "UNDERVALUED",
            85.0,
            "2026-02-14",
            "2026-02-14 10:00:00",
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(main, "DB_PATH", str(db_path), raising=False)

    class ExplodingTicker:
        @property
        def info(self):
            raise AssertionError("Should not hit yfinance when cached row exists")

    monkeypatch.setattr(main.yf, "Ticker", lambda _symbol: ExplodingTicker())

    with TestClient(main.app) as client:
        response = client.get("/api/valuation/RELIANCE.NS")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "RELIANCE.NS"
    assert payload["intrinsic_value"] == 140.0
    assert payload["components"]["dcf"] == 150.0
    assert payload["components"]["graham"] == 130.0
    assert payload["components"]["epv"] == 120.0


def test_order_lifecycle_endpoints(tmp_path, monkeypatch):
    tracker_db = tmp_path / "portfolio_history_test.db"
    monkeypatch.setattr(
        main, "portfolio_tracker", tracker_module.PortfolioTracker(str(tracker_db)), raising=False
    )

    class FakeRiskGovernor:
        def check_kill_switch(
            self, current_vix, dynamic_threshold=None, drawdown_rate_weekly=None
        ):
            return True, "Market conditions safe"

        def validate_var_budget(self, projected_var_pct, max_var_pct):
            return True, "VaR within budget"

        def validate_correlation_risk(self, portfolio_avg_corr):
            return 1.0

        def log_rejected_trade(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(main, "risk_governor", FakeRiskGovernor(), raising=False)

    with TestClient(main.app) as client:
        buy_response = client.post(
            "/api/order",
            json={
                "symbol": "INFY",
                "side": "BUY",
                "quantity": 5,
                "price": 1000.0,
                "score": 84.2,
                "current_vix": 17.5,
            },
        )
        open_positions = client.get("/api/trades/open")
        sell_response = client.post(
            "/api/order",
            json={
                "symbol": "INFY",
                "side": "SELL",
                "quantity": 5,
                "price": 1050.0,
                "reason": "TARGET",
            },
        )
        trade_history = client.get("/api/trades/history")

    assert buy_response.status_code == 200
    assert buy_response.json()["status"] == "accepted"
    assert buy_response.json()["symbol"] == "INFY.NS"

    assert open_positions.status_code == 200
    open_payload = open_positions.json()
    assert len(open_payload) == 1
    assert open_payload[0]["symbol"] == "INFY.NS"

    assert sell_response.status_code == 200
    assert sell_response.json()["status"] == "accepted"
    assert sell_response.json()["symbol"] == "INFY.NS"

    assert trade_history.status_code == 200
    history_payload = trade_history.json()
    assert len(history_payload) == 1
    assert history_payload[0]["symbol"] == "INFY.NS"
    assert history_payload[0]["exit_reason"] == "TARGET"
