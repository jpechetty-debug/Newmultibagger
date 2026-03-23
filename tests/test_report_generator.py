import asyncio
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import report_generator


def _sig_path(path: Path) -> Path:
    return Path(str(path) + ".sha256")


async def _passthrough_backoff(operation, **_kwargs):
    result = operation()
    if asyncio.iscoroutine(result):
        return await result
    return result


def _build_info():
    return {
        "longName": "Mock Industries",
        "currentPrice": 100.0,
        "marketCap": 20_000_000_000,
        "trailingPE": 18.5,
        "returnOnEquity": 0.2,
        "debtToEquity": 0.25,
        "operatingCashflow": 500_000_000,
        "netIncomeToCommon": 300_000_000,
        "fiftyTwoWeekHigh": 120.0,
        "numberOfAnalystOpinions": 12,
        "recommendationKey": "buy",
        "targetMeanPrice": 130.0,
        "profitMargins": 0.14,
        "quickRatio": 1.4,
        "currentRatio": 1.8,
        "heldPercentInsiders": 0.5,
        "heldPercentInstitutions": 0.3,
    }


def test_generate_analyst_report_returns_verified_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(report_generator, "CACHE_DIR", str(cache_dir), raising=False)

    symbol = "RELIANCE.NS"
    cached_report = "# Cached report body"
    cache_path = cache_dir / f"{report_generator._cache_key(symbol)}.md"
    cache_path.write_text(cached_report, encoding="utf-8")
    _sig_path(cache_path).write_text(
        hashlib.sha256(cached_report.encode("utf-8")).hexdigest(),
        encoding="utf-8",
    )

    class ExplodingTicker:
        def __init__(self, _symbol):
            raise AssertionError("Cache hit should bypass yfinance fetch")

    monkeypatch.setattr(report_generator.yf, "Ticker", ExplodingTicker)

    output = asyncio.run(report_generator.generate_analyst_report(symbol))
    assert output == cached_report


def test_generate_analyst_report_rebuilds_on_signature_mismatch(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(report_generator, "CACHE_DIR", str(cache_dir), raising=False)

    symbol = "INFY.NS"
    cache_path = cache_dir / f"{report_generator._cache_key(symbol)}.md"
    cache_path.write_text("tampered", encoding="utf-8")
    _sig_path(cache_path).write_text("wrong-signature", encoding="utf-8")

    class FakeTicker:
        @property
        def info(self):
            return _build_info()

    monkeypatch.setattr(report_generator, "run_with_exponential_backoff", _passthrough_backoff)
    monkeypatch.setattr(report_generator.yf, "Ticker", lambda _symbol: FakeTicker())

    generated = asyncio.run(report_generator.generate_analyst_report(symbol))

    stored_report = cache_path.read_text(encoding="utf-8")
    stored_sig = _sig_path(cache_path).read_text(encoding="utf-8").strip()

    assert generated == stored_report
    assert symbol in generated
    assert stored_sig == hashlib.sha256(stored_report.encode("utf-8")).hexdigest()
