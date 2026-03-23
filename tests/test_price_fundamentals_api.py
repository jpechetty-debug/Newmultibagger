import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient

import main
import modules.price_fundamentals as price_fundamentals


def test_price_fundamentals_endpoint_returns_payload(monkeypatch):
    calls = []

    async def fake_get_price_vs_fundamentals(symbol: str, years: int):
        calls.append((symbol, years))
        return {
            "symbol": symbol,
            "company_name": "Demo Co",
            "data": [
                {
                    "date": "2024-03-31",
                    "fiscal_year": "FY24",
                    "price": 100.0,
                    "eps": 10.0,
                    "sales_per_share": 50.0,
                    "book_value": 40.0,
                    "pe": 10.0,
                    "ps": 2.0,
                    "pb": 2.5,
                }
            ],
            "divergence": {"alert_level": "NONE", "price_cagr": 0.0, "eps_cagr": 0.0},
            "ratios_trend": {"pe_trend": "STABLE"},
            "timestamp": "2026-02-14T12:00:00",
        }

    monkeypatch.setattr(price_fundamentals, "get_price_vs_fundamentals", fake_get_price_vs_fundamentals)

    with TestClient(main.app) as client:
        response = client.get("/api/price-fundamentals/RELIANCE.NS?years=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "RELIANCE.NS"
    assert "data" in payload
    assert "divergence" in payload
    assert "ratios_trend" in payload
    assert calls == [("RELIANCE.NS", 5)]


def test_price_fundamentals_endpoint_clamps_years(monkeypatch):
    seen_years = []

    async def fake_get_price_vs_fundamentals(symbol: str, years: int):
        seen_years.append(years)
        return {
            "symbol": symbol,
            "company_name": "Demo Co",
            "data": [],
            "divergence": {},
            "ratios_trend": {},
            "timestamp": "2026-02-14T12:00:00",
        }

    monkeypatch.setattr(price_fundamentals, "get_price_vs_fundamentals", fake_get_price_vs_fundamentals)

    with TestClient(main.app) as client:
        response_high = client.get("/api/price-fundamentals/TCS.NS?years=99")
        response_low = client.get("/api/price-fundamentals/TCS.NS?years=1")

    assert response_high.status_code == 200
    assert response_low.status_code == 200
    assert seen_years == [10, 3]


def test_price_fundamentals_endpoint_returns_500_on_failure(monkeypatch):
    async def fake_get_price_vs_fundamentals(symbol: str, years: int):
        raise RuntimeError("boom")

    monkeypatch.setattr(price_fundamentals, "get_price_vs_fundamentals", fake_get_price_vs_fundamentals)

    with TestClient(main.app) as client:
        response = client.get("/api/price-fundamentals/TCS.NS?years=5")

    assert response.status_code == 500
    payload = response.json()
    assert payload["detail"].startswith("Failed to fetch price vs fundamentals:")
    assert "boom" in payload["detail"]
