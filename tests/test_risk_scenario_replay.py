import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.stress_test import run_adversarial_scenario_replay


def _sample_portfolio():
    return [
        {"Symbol": "AAA", "Sector": "Technology", "Price": 100.0, "ATR": 4.0},
        {"Symbol": "BBB", "Sector": "Financial", "Price": 200.0, "ATR": 5.0},
        {"Symbol": "CCC", "Sector": "Metals", "Price": 50.0, "ATR": 2.0},
    ]


def test_adversarial_replay_structure():
    replay = run_adversarial_scenario_replay(_sample_portfolio(), base_vix=18.0)

    assert replay["base_vix"] == 18.0
    assert replay["portfolio_beta"] > 0
    assert isinstance(replay["scenarios"], list)
    assert len(replay["scenarios"]) == 3
    assert replay["worst_case"] is not None

    for scenario in replay["scenarios"]:
        assert "gap_down_pct" in scenario
        assert "slippage_bps" in scenario
        assert "correlation_spike" in scenario
        assert "vix" in scenario
        assert "estimated_drawdown_pct" in scenario


def test_adversarial_replay_worst_case_is_liquidity_freeze():
    replay = run_adversarial_scenario_replay(_sample_portfolio(), base_vix=20.0)
    assert replay["worst_case"]["name"] == "Liquidity Freeze"
    assert replay["worst_case"]["estimated_drawdown_pct"] > 0

