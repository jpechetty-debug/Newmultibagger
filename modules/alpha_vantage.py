import json
import os
import time
from datetime import date

import requests

from config import ALPHA_VANTAGE_API_KEY as API_KEY

# Persistent rate limiting tracker across instances.
_last_call_time = 0.0

# --- Daily Budget Tracker ---
# Alpha Vantage free tier: 25 requests per day.
_BUDGET_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "av_budget.json")
_DAILY_LIMIT = 25


def _load_budget():
    """Load today's call count from disk."""
    try:
        with open(_BUDGET_FILE, "r") as f:
            data = json.load(f)
        if data.get("date") == str(date.today()):
            return data.get("calls", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return 0


def _save_budget(count):
    """Save today's call count to disk."""
    try:
        os.makedirs(os.path.dirname(_BUDGET_FILE), exist_ok=True)
        with open(_BUDGET_FILE, "w") as f:
            json.dump({"date": str(date.today()), "calls": count}, f)
    except Exception:
        pass


def _check_budget():
    """Returns True if calls remain in today's budget."""
    return _load_budget() < _DAILY_LIMIT


def _increment_budget():
    """Increment today's call counter."""
    current = _load_budget()
    _save_budget(current + 1)


def get_remaining_budget():
    """Returns number of AV calls remaining today."""
    return max(0, _DAILY_LIMIT - _load_budget())


class AlphaVantageProvider:
    def __init__(self):
        self.base_url = "https://www.alphavantage.co/query"

    def _rate_limit_wait(self):
        """Alpha Vantage free tier: 5 calls per minute (12s spacing)."""
        global _last_call_time
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < 12:
            wait_time = max(1, 12 - elapsed)
            print(f"   Alpha Vantage rate pacing: {wait_time:.0f}s")
            time.sleep(wait_time)
        _last_call_time = time.time()

    def _call_api(self, params):
        """Centralized API caller with rate-limit + budget management."""
        if not _check_budget():
            remaining = get_remaining_budget()
            print(f"    Alpha Vantage daily quota exhausted ({_DAILY_LIMIT} calls). {remaining} remaining.")
            return None

        self._rate_limit_wait()
        try:
            response = requests.get(self.base_url, params=params, timeout=15)
            data = response.json()

            if "Note" in data:
                print("    Alpha Vantage rate limit hit (per-minute).")
                return None
            if "Error Message" in data:
                print(f"    Alpha Vantage error: {data['Error Message']}")
                return None

            _increment_budget()
            remaining = get_remaining_budget()
            print(f"   AV call OK. Budget remaining: {remaining}/{_DAILY_LIMIT}")
            return data
        except Exception as exc:
            print(f"   Alpha Vantage request failed: {exc}")
            return None

    # ----------------------------------------------------------------
    # 1. Market Movers (existing)
    # ----------------------------------------------------------------
    def get_market_movers(self):
        """Fetch global top gainers, losers, and most active."""
        data = self._call_api({"function": "TOP_GAINERS_LOSERS", "apikey": API_KEY})
        if not data:
            return None
        return {
            "gainers": data.get("top_gainers", [])[:5],
            "losers": data.get("top_losers", [])[:5],
            "active": data.get("most_actively_traded", [])[:5],
        }

    # ----------------------------------------------------------------
    # 2. News Sentiment (existing, improved)
    # ----------------------------------------------------------------
    def get_stock_sentiment(self, symbol):
        """
        Fetch news sentiment for a symbol.

        Returns dict with:
        - title-keyed sentiment entries for article-level matching
        - __symbol__ aggregate sentiment for symbol-level fallback
        """
        av_symbol = symbol.split(".")[0].upper()

        data = self._call_api({
            "function": "NEWS_SENTIMENT",
            "tickers": av_symbol,
            "limit": 50,
            "apikey": API_KEY,
        })
        if not data:
            return {}

        feed = data.get("feed", [])
        sentiment_map = {}
        symbol_scores = []

        for item in feed:
            title = item.get("title")
            score = float(item.get("overall_sentiment_score", 0) or 0)
            label = item.get("overall_sentiment_label", "Neutral")

            if title:
                sentiment_map[title] = {"score": score, "label": label}

            ticker_sentiment = item.get("ticker_sentiment") or []
            matched = False
            for ticker_item in ticker_sentiment:
                ticker = str(ticker_item.get("ticker", "")).upper()
                if ticker == av_symbol:
                    rel_score = float(
                        ticker_item.get("ticker_sentiment_score", score) or score
                    )
                    symbol_scores.append(rel_score)
                    matched = True
            if not matched and not ticker_sentiment:
                symbol_scores.append(score)

        if symbol_scores:
            avg_score = sum(symbol_scores) / len(symbol_scores)
            if avg_score > 0.35:
                agg_label = "Bullish"
            elif avg_score < -0.35:
                agg_label = "Bearish"
            else:
                agg_label = "Neutral"
            sentiment_map["__symbol__"] = {
                "score": round(avg_score, 4),
                "label": agg_label,
            }

        return sentiment_map

    # ----------------------------------------------------------------
    # 3. Company Overview (NEW)
    # ----------------------------------------------------------------
    def get_company_overview(self, symbol):
        """
        Fetch comprehensive company fundamentals.
        Returns PE, EPS, BookValue, DividendYield, 52WeekHigh/Low, MarketCap, etc.

        Note: Alpha Vantage uses BSE symbols for Indian stocks (e.g., TCS.BSE).
        For NSE-listed stocks, we try the bare symbol (e.g., TCS).
        """
        # Convert .NS to bare symbol for AV lookup
        av_symbol = symbol.replace(".NS", "").replace(".BO", "")

        data = self._call_api({
            "function": "OVERVIEW",
            "symbol": f"{av_symbol}.BSE",
            "apikey": API_KEY,
        })

        if not data or len(data) < 5:
            # Retry with bare symbol (works for some Indian stocks)
            data = self._call_api({
                "function": "OVERVIEW",
                "symbol": av_symbol,
                "apikey": API_KEY,
            })

        if not data or len(data) < 5:
            return None

        def _safe_float(val, default=None):
            try:
                if val in (None, "None", "-", ""):
                    return default
                return float(val)
            except (ValueError, TypeError):
                return default

        return {
            "name": data.get("Name"),
            "description": data.get("Description"),
            "sector": data.get("Sector"),
            "industry": data.get("Industry"),
            "market_cap": _safe_float(data.get("MarketCapitalization")),
            "pe_ratio": _safe_float(data.get("PERatio")),
            "peg_ratio": _safe_float(data.get("PEGRatio")),
            "book_value": _safe_float(data.get("BookValue")),
            "dividend_yield": _safe_float(data.get("DividendYield")),
            "eps": _safe_float(data.get("EPS")),
            "roe": _safe_float(data.get("ReturnOnEquityTTM")),
            "revenue_per_share": _safe_float(data.get("RevenuePerShareTTM")),
            "profit_margin": _safe_float(data.get("ProfitMargin")),
            "operating_margin": _safe_float(data.get("OperatingMarginTTM")),
            "week_52_high": _safe_float(data.get("52WeekHigh")),
            "week_52_low": _safe_float(data.get("52WeekLow")),
            "beta": _safe_float(data.get("Beta")),
            "forward_pe": _safe_float(data.get("ForwardPE")),
            "ev_to_ebitda": _safe_float(data.get("EVToEBITDA")),
            "analyst_target_price": _safe_float(data.get("AnalystTargetPrice")),
            "source": "alpha_vantage",
        }

    # ----------------------------------------------------------------
    # 4. Earnings Calendar (NEW)
    # ----------------------------------------------------------------
    def get_earnings_calendar(self, symbol):
        """
        Fetch upcoming and recent earnings data.
        Returns list of earnings entries with date, EPS estimate, actual, and surprise.
        """
        av_symbol = symbol.replace(".NS", "").replace(".BO", "")

        data = self._call_api({
            "function": "EARNINGS",
            "symbol": f"{av_symbol}.BSE",
            "apikey": API_KEY,
        })

        if not data:
            # Retry with bare symbol
            data = self._call_api({
                "function": "EARNINGS",
                "symbol": av_symbol,
                "apikey": API_KEY,
            })

        if not data:
            return None

        def _safe_float(val, default=None):
            try:
                if val in (None, "None", "-", ""):
                    return default
                return float(val)
            except (ValueError, TypeError):
                return default

        quarterly = data.get("quarterlyEarnings", [])
        annual = data.get("annualEarnings", [])

        result = {
            "quarterly": [],
            "annual": [],
        }

        for q in quarterly[:8]:  # Last 8 quarters
            result["quarterly"].append({
                "date": q.get("fiscalDateEnding"),
                "reported_date": q.get("reportedDate"),
                "estimated_eps": _safe_float(q.get("estimatedEPS")),
                "reported_eps": _safe_float(q.get("reportedEPS")),
                "surprise": _safe_float(q.get("surprise")),
                "surprise_pct": _safe_float(q.get("surprisePercentage")),
            })

        for a in annual[:5]:  # Last 5 years
            result["annual"].append({
                "date": a.get("fiscalDateEnding"),
                "reported_eps": _safe_float(a.get("reportedEPS")),
            })

        return result
