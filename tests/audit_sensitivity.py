import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from modules.risk import RiskGovernor
from modules.optimizer import PortfolioOptimizer

class TestAuditSensitivity(unittest.TestCase):
    """
    Independent Audit: Parameter Sensitivity & Robustness Check.
    Objective: ensure small parameter changes don't cause chaotic output changes.
    """

    def setUp(self):
        self.risk = RiskGovernor()
        self.optimizer = PortfolioOptimizer()

    def test_drawdown_limit_sensitivity(self):
        """
        Audit Item: Graduated Drawdown Thresholds.
        Test boundaries: 10% (Warning), 15% (Action), 20% (Deep).
        Expectation: Linear/Gradual reduction in capital, not binary cliffs (except at hard stops).
        """
        print("\n📊 Sensitivity Test: Drawdown Thresholds")
        capital = 100000.0
        
        # Test range of drawdowns from 5% to 25%
        drawdowns = [5, 10, 12, 15, 16, 20, 25]
        allocations = []
        
        for dd in drawdowns:
            # Assume Normal Regime (VIX=20, Bull/Sideways)
            cap_limit = self.risk.calculate_max_capital_at_risk(capital, dd, {'vix': 20, 'regime': 'BULL'})
            allocations.append(cap_limit)
            print(f"   DD -{dd}% -> Cap Allowed: {cap_limit:,.0f} ({(cap_limit/capital)*100:.0f}%)")

        # Validation Logic
        # 1. < 10% DD should be 100% cap
        self.assertEqual(allocations[0], capital, "5% DD should not penalize.")
        
        # 2. > 15% DD should be 50% cap (Soft Kill)
        self.assertEqual(allocations[4], capital * 0.5, "16% DD should trigger 50% Soft Cap.")
        
        # 3. > 15% DD + Crash VIX should be 0% (Hard Kill) -> Separate check
        crash_cap = self.risk.calculate_max_capital_at_risk(capital, 16, {'vix': 35, 'regime': 'BEAR'})
        self.assertEqual(crash_cap, 0.0, "16% DD + Crash VIX should trigger Hard Kill.")

    def test_correlation_penalty_sensitivity(self):
        """
        Audit Item: Correlation Thresholds.
        Test boundaries: 0.5 (Low), 0.7 (Warning), 0.75 (Critical), 0.9 (Lockstep).
        """
        print("\n📊 Sensitivity Test: Correlation Penalties")
        
        # Test 1: Portfolio Level Exposure Cut
        correlations = [0.5, 0.65, 0.71, 0.76, 0.90]
        for corr in correlations:
            factor = self.risk.validate_correlation_risk(corr)
            print(f"   Avg Corr {corr:.2f} -> Exposure Factor: {factor:.2f}")
            
            if corr > self.risk.corr_liquidate_threshold:
                self.assertEqual(factor, 0.0, "Lockstep Correlation should trigger full de-risk.")
            elif corr > self.risk.corr_reduce_threshold:
                # Expect 0.8 factor (20% cut)
                self.assertEqual(factor, 0.8, "Critical Correlation should cut exposure by 20%")
            elif corr > 0.70:
                self.assertEqual(factor, 1.0, "High Correlation warning (no portfolio cut yet)")
            else:
                self.assertEqual(factor, 1.0, "Normal Correlation should have no penalty")

    def test_optimizer_concentration_sensitivity(self):
        """
        Audit Item: Portfolio Optimizer Stability.
        Check if small volatility changes cause massive weight shifts.
        """
        print("\n📊 Sensitivity Test: Optimizer Weights")
        
        # Relax constraints for this test to specific isolate Volatility Logic
        self.optimizer.max_single_weight = 1.0
        self.optimizer.max_sector_weight = 1.0
        
        # Base Case: 2 Stocks, Equal Price, Diff Volatility
        base_stocks = [
            {'Symbol': 'STABLE', 'Sector': 'Fin', 'Price': 100, 'ATR': 2.0}, # 2% Vol
            {'Symbol': 'VOLATILE', 'Sector': 'Tech', 'Price': 100, 'ATR': 4.0} # 4% Vol
        ]
        
        # Run Optimizer
        df = self.optimizer.optimize_allocation(base_stocks)
        # Avoid error if DF is empty
        if df.empty:
            self.fail("Optimizer returned empty dataframe")
            
        w_stable = df[df['Symbol']=='STABLE']['Allocated_Weight'].iloc[0]
        w_volatile = df[df['Symbol']=='VOLATILE']['Allocated_Weight'].iloc[0]
        
        print(f"   Base: Stable {w_stable:.2f} vs Volatile {w_volatile:.2f}")
        
        # Expect Stable to have 2x weight of Volatile (Inverse Volatility)
        # Vol1 = 0.02, Inv1 = 50
        # Vol2 = 0.04, Inv2 = 25
        # Total = 75. W1 = 50/75 = 0.66, W2 = 25/75 = 0.33
        self.assertAlmostEqual(w_stable, 0.66, delta=0.08) # Allowing slight diff for int rounding or implementation details
        
        # Perturbation: Increase Volatile ATR slightly (4.0 -> 4.2)
        perturb_stocks = [
            {'Symbol': 'STABLE', 'Sector': 'Fin', 'Price': 100, 'ATR': 2.0}, 
            {'Symbol': 'VOLATILE', 'Sector': 'Tech', 'Price': 100, 'ATR': 4.2}
        ]
        df_p = self.optimizer.optimize_allocation(perturb_stocks)
        w_volatile_new = df_p[df_p['Symbol']=='VOLATILE']['Allocated_Weight'].iloc[0]
        
        print(f"   Perturbed: Volatile ATR 4.0->4.2, Weight {w_volatile:.3f}->{w_volatile_new:.3f}")
        
        # Check for stability (should not drop drastically)
        change = abs(w_volatile - w_volatile_new)
        self.assertLess(change, 0.05, "Optimizer is too sensitive to small ATR changes.")

if __name__ == '__main__':
    unittest.main()
