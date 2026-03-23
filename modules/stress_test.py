import pandas as pd


def _build_weights(portfolio_stocks, weights=None):
    if weights:
        return weights
    if not portfolio_stocks:
        return {}
    return {s["Symbol"]: 1.0 / len(portfolio_stocks) for s in portfolio_stocks}


def _estimate_portfolio_beta(portfolio_stocks, weights=None):
    if not portfolio_stocks:
        return 1.0

    use_weights = _build_weights(portfolio_stocks, weights)
    total_beta = 0.0
    total_weight = 0.0

    for stock in portfolio_stocks:
        sym = stock["Symbol"]
        wt = use_weights.get(sym, 0.0)

        beta = 1.0
        sec = stock.get("Sector", "Unknown")
        if sec in ["Technology", "Realty", "Metals"]:
            beta += 0.3
        if sec in ["FMCG", "Utilities", "Pharma"]:
            beta -= 0.2

        atr = stock.get("ATR", 0)
        price = stock.get("Price", 1)
        if price > 0:
            vol = atr / price
            if vol > 0.03:
                beta += 0.2
            if vol < 0.015:
                beta -= 0.1

        total_beta += beta * wt
        total_weight += wt

    return total_beta / total_weight if total_weight > 0 else 1.0


def run_stress_test(portfolio_stocks, weights=None):
    """
    Phase 20: Risks Management Stress Testing.
    Simulates how the portfolio would behave in historical crash scenarios.
    
    scenarios = {
        "2008 Global Financial Crisis": -0.55,
        "2020 Covid Crash": -0.38,
        "2022 Tech Bear Market": -0.22,
        "Standard Correction": -0.10
    }
    """
    print("\n" + "="*50)
    print("🌪️  PHASE 20: PORTFOLIO STRESS TEST (CRASH SIMULATION)")
    print("="*50)
    
    if not portfolio_stocks:
        print("Empty portfolio.")
        return

    # 1. Calculate Portfolio Beta
    # We estimate Beta based on Sector and Volatility (ATR)
    # High Beta (>1.2) = Aggressive
    # Low Beta (<0.8) = Defensive
    
    portfolio_beta = _estimate_portfolio_beta(portfolio_stocks, weights)
    
    print(f"Portfolio Beta (Estimated): {portfolio_beta:.2f}")
    if portfolio_beta > 1.3:
        print("⚠️  Risk Profile: AGGRESSIVE (High Volatility)")
    elif portfolio_beta < 0.8:
        print("🛡️  Risk Profile: DEFENSIVE (Low Volatility)")
    else:
        print("⚖️  Risk Profile: BALANCED")
        
    print("-" * 50)
    print(f"{'Scenario':<30} | {'Market Drop':<12} | {'Est. Portfolio Impact':<20}")
    print("-" * 50)
    
    scenarios = [
        ("Correction (Standard)", -0.10),
        ("2022 Inflation Bear", -0.22),
        ("2020 Covid Flash Crash", -0.38),
        ("2008 Financial Crisis", -0.55)
    ]
    
    for name, drop in scenarios:
        # Impact = Beta * Market Drop
        # But we add a 'Alpha Cushion'? No, in a crash, correlation goes to 1.
        # Often High Beta falls MORE than Beta implies during panic.
        
        impact = drop * portfolio_beta
        
        # formatting
        mkt_lbl = f"{drop*100:.0f}%"
        port_lbl = f"{impact*100:.1f}%"
        
        # Color code (text based)
        emoji = "🩸" if impact < -0.3 else ("🔻" if impact < -0.15 else "📉")
        
        print(f"{name:<30} | {mkt_lbl:<12} | {port_lbl:<20} {emoji}")
        
    print("="*50 + "\n")


def run_adversarial_scenario_replay(portfolio_stocks, weights=None, base_vix=20.0):
    """
    Phase 66: Adversarial scenario replay pipeline.

    Covers:
    - regime flip (BULL -> BEAR)
    - gap-down shock
    - slippage expansion
    - correlation spike
    - vix shock
    """
    if not portfolio_stocks:
        return {
            "base_vix": float(base_vix),
            "portfolio_beta": 1.0,
            "scenarios": [],
            "worst_case": None,
            "message": "Empty portfolio",
        }

    portfolio_beta = _estimate_portfolio_beta(portfolio_stocks, weights)

    scenarios = [
        {
            "name": "Regime Flip + VIX Shock",
            "regime": "BEAR",
            "vix": max(float(base_vix), 32.0),
            "gap_down_pct": -0.04,
            "slippage_bps": 25,
            "correlation_spike": 0.72,
        },
        {
            "name": "Gap-Down Cascade",
            "regime": "BEAR",
            "vix": max(float(base_vix), 36.0),
            "gap_down_pct": -0.08,
            "slippage_bps": 40,
            "correlation_spike": 0.80,
        },
        {
            "name": "Liquidity Freeze",
            "regime": "BEAR",
            "vix": max(float(base_vix), 45.0),
            "gap_down_pct": -0.12,
            "slippage_bps": 70,
            "correlation_spike": 0.90,
        },
    ]

    replay = []
    for scenario in scenarios:
        gap_component = abs(float(scenario["gap_down_pct"]))
        slippage_component = float(scenario["slippage_bps"]) / 10000.0
        correlation_component = max(0.0, float(scenario["correlation_spike"]) - 0.60)
        vix_component = max(0.0, (float(scenario["vix"]) - float(base_vix)) / 100.0)

        total_shock = gap_component + slippage_component + correlation_component + vix_component
        estimated_drawdown = min(0.95, total_shock * max(0.6, portfolio_beta))

        replay.append(
            {
                **scenario,
                "estimated_drawdown_pct": round(estimated_drawdown * 100, 2),
                "shock_score": round(total_shock, 4),
            }
        )

    worst_case = max(replay, key=lambda item: item["estimated_drawdown_pct"])

    return {
        "base_vix": float(base_vix),
        "portfolio_beta": round(float(portfolio_beta), 3),
        "scenarios": replay,
        "worst_case": worst_case,
    }
