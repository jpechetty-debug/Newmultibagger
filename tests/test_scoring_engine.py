"""
tests/test_scoring_engine.py
────────────────────────────
Pytest unit tests for modules/scoring.py — calculate_institutional_score().

Run:
    pytest tests/test_scoring_engine.py -v
    pytest tests/test_scoring_engine.py -v --tb=short --cov=modules.scoring

All external-API modules are mocked so these tests run offline in CI.
"""

from __future__ import annotations

import sys
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Project root on path ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Stub every module that touches external APIs ────────────────────────────
_prom_stub = MagicMock()
_prom_stub.calculate_promoter_score.return_value = {
    "is_disqualified": False, "score_adjustment": 0
}
sys.modules.setdefault("modules.promoter_intel", _prom_stub)

_est_stub = MagicMock()
_est_stub.get_estimate_data.return_value = {
    "momentum": {"is_disqualified": False, "score_cap": None, "score_adjustment": 0}
}
sys.modules.setdefault("modules.estimates", _est_stub)

# Conviction engine stub
_conv_stub = MagicMock()
_conv_stub.calculate_conviction_score.return_value = {
    "conviction_score": 50, "conviction_boost": 0,
    "institutional_interest": False, "investors": [],
}
sys.modules.setdefault("research.conviction_engine", _conv_stub)

# Now import the module under test
from modules.scoring import calculate_institutional_score, normalize_metric


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def perfect_stock() -> dict:
    """A stock that passes all 12 checklist criteria."""
    return {
        "Symbol": "PERFECT.NS",
        "Market_Cap_Cr": 5000,
        "PE_Ratio": 18,
        "Avg_ROE_5Y%": 25,
        "ROE%": 22,
        "Debt_Equity": 0.3,
        "CFO_PAT_Ratio": 1.4,
        "Down_From_52W_High%": 8,
        "Sales_Growth_5Y%": 22,
        "Sales_Growth_TTM%": 18,
        "EPS_Growth%": 20,
        "Promoter_Holding%": 65,
        "Inst_Holding%": 25,
        "F_Score": 8,
        "Earnings_Inflection_Score": 4,
        "Sector": "Technology",
        "Value_Gap%": 30,
        "Technical_Signal": "Bullish",
        "Analyst_Rating": "Strong Buy",
        "Analyst_Upside%": 25,
        "ATR": 30,
        "Price": 1000,
        "Profit_Margin%": 18,
    }


@pytest.fixture
def distressed_stock() -> dict:
    """A stock that fails most checklist criteria."""
    return {
        "Symbol": "WRECK.NS",
        "Market_Cap_Cr": 50,
        "PE_Ratio": 120,
        "Avg_ROE_5Y%": -5,
        "ROE%": -8,
        "Debt_Equity": 4.5,
        "CFO_PAT_Ratio": -0.5,
        "Down_From_52W_High%": 70,
        "Sales_Growth_5Y%": -10,
        "Sales_Growth_TTM%": -12,
        "EPS_Growth%": -20,
        "Promoter_Holding%": 15,
        "Inst_Holding%": 2,
        "F_Score": 2,
        "Earnings_Inflection_Score": 0,
        "Sector": "Real Estate",
        "Value_Gap%": -60,
        "Technical_Signal": "Bearish",
        "Analyst_Rating": "Sell",
        "Analyst_Upside%": -15,
        "ATR": 200,
        "Price": 100,
        "Profit_Margin%": -5,
    }


# ═══════════════════════════════════════════════════════════════════════════
# normalize_metric
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeMetric:

    def test_mid_value_returns_near_fifty(self):
        score = normalize_metric(15, 0, 30)
        assert 45 <= score <= 55

    def test_at_max_returns_near_hundred(self):
        score = normalize_metric(30, 0, 30)
        assert score > 90

    def test_at_min_returns_near_zero(self):
        score = normalize_metric(0, 0, 30)
        assert score < 10

    def test_invert_flag(self):
        normal  = normalize_metric(5, 0, 10)
        inverted = normalize_metric(5, 0, 10, invert=True)
        assert abs(normal + inverted - 100) < 1

    def test_none_value_returns_zero(self):
        assert normalize_metric(None, 0, 100) == 0

    def test_nan_returns_zero(self):
        assert normalize_metric(float("nan"), 0, 100) == 0

    def test_inf_returns_zero(self):
        assert normalize_metric(float("inf"), 0, 100) == 0

    def test_zero_span_does_not_crash(self):
        score = normalize_metric(5, 5, 5)
        assert 0 <= score <= 100


# ═══════════════════════════════════════════════════════════════════════════
# calculate_institutional_score — output contract
# ═══════════════════════════════════════════════════════════════════════════

class TestScoreOutputContract:

    def test_returns_dict_with_required_keys(self, perfect_stock):
        result = calculate_institutional_score(perfect_stock)
        required = {
            "total_score", "raw_score", "checklist_score",
            "data_confidence", "conviction_score", "scoring_strategy",
            "factor_breakdown",
        }
        assert required.issubset(result.keys())

    def test_total_score_in_range(self, perfect_stock, distressed_stock):
        for stock in (perfect_stock, distressed_stock):
            result = calculate_institutional_score(stock)
            assert 0 <= result["total_score"] <= 100, (
                f"Score out of range: {result['total_score']} for {stock['Symbol']}"
            )

    def test_score_is_finite(self, perfect_stock):
        result = calculate_institutional_score(perfect_stock)
        assert math.isfinite(result["total_score"])

    def test_checklist_format(self, perfect_stock):
        result = calculate_institutional_score(perfect_stock)
        parts = result["checklist_score"].split("/")
        assert len(parts) == 2
        passes, total = int(parts[0]), int(parts[1])
        assert 0 <= passes <= total == 12

    def test_factor_breakdown_keys(self, perfect_stock):
        result = calculate_institutional_score(perfect_stock)
        fb = result["factor_breakdown"]
        assert all(k in fb for k in ("Fundamentals", "Value", "Risk", "Momentum"))


# ═══════════════════════════════════════════════════════════════════════════
# Score ordering — high quality > low quality
# ═══════════════════════════════════════════════════════════════════════════

class TestScoreOrdering:

    def test_perfect_beats_distressed(self, perfect_stock, distressed_stock):
        good = calculate_institutional_score(perfect_stock)["total_score"]
        bad  = calculate_institutional_score(distressed_stock)["total_score"]
        assert good > bad, f"Expected {good} > {bad}"

    def test_high_roe_beats_low_roe(self, perfect_stock):
        high = perfect_stock.copy()
        low  = perfect_stock.copy()
        high["Avg_ROE_5Y%"] = 35
        low["Avg_ROE_5Y%"]  = 5

        s_high = calculate_institutional_score(high)["total_score"]
        s_low  = calculate_institutional_score(low)["total_score"]
        assert s_high >= s_low

    def test_high_fscore_beats_low_fscore(self, perfect_stock):
        high = {**perfect_stock, "F_Score": 9}
        low  = {**perfect_stock, "F_Score": 2}

        s_high = calculate_institutional_score(high)["total_score"]
        s_low  = calculate_institutional_score(low)["total_score"]
        assert s_high > s_low

    def test_value_gap_positive_beats_negative(self, perfect_stock):
        cheap     = {**perfect_stock, "Value_Gap%": 40}
        expensive = {**perfect_stock, "Value_Gap%": -50}

        s_cheap = calculate_institutional_score(cheap)["total_score"]
        s_exp   = calculate_institutional_score(expensive)["total_score"]
        assert s_cheap > s_exp


# ═══════════════════════════════════════════════════════════════════════════
# Regime weighting
# ═══════════════════════════════════════════════════════════════════════════

class TestRegimeWeighting:

    def test_momentum_regime_rewards_momentum_stock(self, perfect_stock):
        """A high-EPS stock should score higher in BULL/momentum regime."""
        high_mom = {**perfect_stock, "EPS_Growth%": 50, "Sales_Growth_5Y%": 30}
        s_bull     = calculate_institutional_score(high_mom, market_regime="Momentum")["total_score"]
        s_value    = calculate_institutional_score(high_mom, market_regime="Value")["total_score"]
        # Momentum regime heavily weights EPS — score must be >= value mode
        assert s_bull >= s_value

    def test_value_regime_penalises_high_pe(self, perfect_stock):
        overpriced = {**perfect_stock, "PE_Ratio": 90, "Value_Gap%": -60}
        s_value   = calculate_institutional_score(overpriced, market_regime="Value")["total_score"]
        s_momentum = calculate_institutional_score(overpriced, market_regime="Momentum")["total_score"]
        # Value mode weights valuation heavily — overpriced stock should score worse
        assert s_value <= s_momentum

    def test_unknown_regime_falls_back_to_balanced(self, perfect_stock):
        s_unknown  = calculate_institutional_score(perfect_stock, market_regime="XYZZY")["total_score"]
        s_balanced = calculate_institutional_score(perfect_stock, market_regime="Balanced")["total_score"]
        assert abs(s_unknown - s_balanced) < 0.1


# ═══════════════════════════════════════════════════════════════════════════
# No cliff jumps — checklist spline smoothness
# ═══════════════════════════════════════════════════════════════════════════

class TestNoCliffJumps:

    MAX_ALLOWED_JUMP = 15  # points — any jump larger than this is a cliff

    def _score_with_n_passes(self, n: int) -> float:
        """Build a stock that passes exactly n checklist criteria."""
        data = {
            "Symbol": f"CL{n}.NS",
            "Market_Cap_Cr": 2000 if n >= 1 else 50,
            "PE_Ratio": 20 if n >= 2 else 200,
            "Avg_ROE_5Y%": 20 if n >= 3 else -5,
            "Debt_Equity": 0.5 if n >= 4 else 6,
            "CFO_PAT_Ratio": 1.2 if n >= 5 else -1,
            "Down_From_52W_High%": 10 if n >= 6 else 90,
            "Sales_Growth_5Y%": 20 if n >= 7 else -15,
            "EPS_Growth%": 15 if n >= 8 else -20,
            "Promoter_Holding%": 55 if n >= 9 else 10,
            "F_Score": 7 if n >= 10 else 1,
            "Value_Gap%": 15 if n >= 11 else -70,
            "Sector": "Technology",
            "Technical_Signal": "Neutral",
        }
        return calculate_institutional_score(data)["total_score"]

    def test_no_cliff_across_checklist_passes(self):
        scores = [(n, self._score_with_n_passes(n)) for n in range(13)]
        scores.sort()
        jumps = []
        for i in range(1, len(scores)):
            diff = abs(scores[i][1] - scores[i - 1][1])
            if diff > self.MAX_ALLOWED_JUMP:
                jumps.append((scores[i - 1][0], scores[i][0], diff))

        assert not jumps, (
            f"Score cliff(s) detected (>{self.MAX_ALLOWED_JUMP}pt jump): {jumps}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Deterministic tie-breaker
# ═══════════════════════════════════════════════════════════════════════════

class TestTieBreaker:

    def test_different_symbols_produce_distinct_scores(self, perfect_stock):
        s1 = calculate_institutional_score({**perfect_stock, "Symbol": "ALPHA.NS"})["total_score"]
        s2 = calculate_institutional_score({**perfect_stock, "Symbol": "BETA.NS"})["total_score"]
        assert s1 != s2, "Tie-breaker epsilon should make scores distinct"

    def test_same_symbol_is_deterministic(self, perfect_stock):
        s1 = calculate_institutional_score(perfect_stock)["total_score"]
        s2 = calculate_institutional_score(perfect_stock)["total_score"]
        assert s1 == s2, "Same inputs must always produce the same score"

    def test_epsilon_does_not_dominate(self, perfect_stock):
        """The epsilon must be tiny — it must not flip the ranking of two stocks
        where one is genuinely better than the other."""
        better = {**perfect_stock, "Symbol": "OMEGA.NS", "Avg_ROE_5Y%": 40}
        worse  = {**perfect_stock, "Symbol": "ALPHA.NS", "Avg_ROE_5Y%": 10}

        s_better = calculate_institutional_score(better)["total_score"]
        s_worse  = calculate_institutional_score(worse)["total_score"]
        assert s_better > s_worse, "Epsilon must never flip a genuine quality gap"


# ═══════════════════════════════════════════════════════════════════════════
# Disqualifier ceiling tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDisqualifiers:

    def test_negative_roe_caps_score(self, perfect_stock):
        neg_roe = {**perfect_stock, "Avg_ROE_5Y%": -20, "ROE%": -20}
        result = calculate_institutional_score(neg_roe)
        assert result["total_score"] <= 60, (
            f"Negative ROE should cap score ≤60, got {result['total_score']}"
        )

    def test_extreme_overvaluation_caps_score(self, perfect_stock):
        overval = {**perfect_stock, "PE_Ratio": 200, "Value_Gap%": -80}
        result = calculate_institutional_score(overval)
        assert result["total_score"] <= 75

    def test_very_low_fscore_caps_score(self, perfect_stock):
        low_f = {**perfect_stock, "F_Score": 1}
        result = calculate_institutional_score(low_f)
        assert result["total_score"] <= 71, (
            f"F-Score=1 should produce a ceiling ≤71, got {result['total_score']}"
        )

    def test_declining_revenue_penalised(self, perfect_stock):
        declining = {
            **perfect_stock,
            "Sales_Growth_5Y%": -12,
            "Sales_Growth_TTM%": -8,
        }
        base   = calculate_institutional_score(perfect_stock)["total_score"]
        result = calculate_institutional_score(declining)["total_score"]
        assert result < base, "Declining revenue must reduce score vs baseline"


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases — should never raise, always return valid dict
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    @pytest.mark.parametrize("data", [
        {},                                         # completely empty
        {"Symbol": "NULL.NS"},                      # symbol only
        {"Symbol": "NEG.NS", "PE_Ratio": -1},      # negative PE
        {"Symbol": "INF.NS", "Avg_ROE_5Y%": 1e9},  # absurd ROE
        {"Symbol": "ZERO.NS", "Price": 0},          # zero price
        {"Symbol": "NONES.NS", "F_Score": None},   # None values
    ])
    def test_does_not_raise(self, data):
        try:
            result = calculate_institutional_score(data)
            assert isinstance(result, dict)
            assert 0 <= result["total_score"] <= 100
        except Exception as exc:
            pytest.fail(f"calculate_institutional_score raised with data={data!r}: {exc}")

    def test_missing_symbol_uses_empty_string(self):
        result = calculate_institutional_score({"Avg_ROE_5Y%": 20})
        assert "total_score" in result
