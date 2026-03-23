import pandas as pd
import unittest
from unittest.mock import MagicMock, patch
from modules.market_data import MarketDataProvider
from modules.risk import RiskGovernor

class TestV29Refinements(unittest.TestCase):
    
    def setUp(self):
        self.mdp = MarketDataProvider()
        self.risk = RiskGovernor()
        
    @patch('modules.market_data.yf.download')
    @patch('modules.market_data.MarketDataProvider.get_batch_history')
    @patch('modules.market_data.MarketDataProvider.get_vix_threshold')
    def test_regime_concensus_bull(self, mock_vix, mock_batch, mock_index):
        print("\n🧪 Testing 3-Factor Regime Consensus (BULL Case)...")
        
        # 1. Mock VIX (Low Volatility -> BULL)
        mock_vix.return_value = (15.0, 12.0) # Threshold 15, Current 12
        
        # 2. Mock Breadth (Strong -> BULL)
        # Return DF with 30 columns, 20 > SMA50
        dates = pd.date_range(start='2024-01-01', periods=60)
        data = {}
        for i in range(20):
            # Price (110) > SMA50 (approx 100)
            data[f"Stock_{i}"] = [100]*59 + [110]
        for i in range(10):
            # Price (90) < SMA50 (approx 100)
            data[f"Loser_{i}"] = [100]*59 + [90]
            
        mock_batch.return_value = pd.DataFrame(data, index=dates)
        
        # 3. Mock Trend (Nifty > 200DMA -> BULL)
        # 200 days of 100, then 105
        prices = [100]*199 + [105]
        mock_index.return_value = pd.DataFrame({'Close': prices}, index=pd.date_range('2024-01-01', periods=200))

        regime = self.mdp.get_market_regime()
        print(f"   👉 Regime Result: {regime}")
        
        self.assertEqual(regime['regime'], 'BULL')
        self.assertEqual(regime['votes']['BULL'], 3)

    def test_risk_governor_graduated_response(self):
        print("\n🧪 Testing Risk Governor Graduated Response...")
        
        # Case 1: Hard Kill (Crash)
        cap = self.risk.calculate_max_capital_at_risk(100000, 16, {'regime': 'BEAR', 'vix': 35})
        print(f"   👉 Case 1 (Crash): Allocated {cap} (Expected 0.0)")
        self.assertEqual(cap, 0.0)
        
        # Case 2: Soft Kill (Normal Drawdown)
        cap = self.risk.calculate_max_capital_at_risk(100000, 16, {'regime': 'BULL', 'vix': 20})
        print(f"   👉 Case 2 (Soft Kill): Allocated {cap} (Expected 50000.0)")
        self.assertEqual(cap, 50000.0)
        
        # Case 3: Warning
        cap = self.risk.calculate_max_capital_at_risk(100000, 12, {'regime': 'BULL', 'vix': 20})
        print(f"   👉 Case 3 (Warning): Allocated {cap} (Expected 75000.0)")
        self.assertEqual(cap, 75000.0)

    def test_risk_correlation(self):
        print("\n🧪 Testing Dynamic Correlation Penalty...")
        
        # Case 1: Crisis Correlation
        factor = self.risk.validate_correlation_risk(0.80)
        print(f"   👉 Case 1 (0.80 avg corr): Factor {factor} (Expected 0.8)")
        self.assertEqual(factor, 0.8)
        
        # Case 2: Safe Correlation
        factor = self.risk.validate_correlation_risk(0.50)
        print(f"   👉 Case 2 (0.50 avg corr): Factor {factor} (Expected 1.0)")
        self.assertEqual(factor, 1.0)

if __name__ == '__main__':
    unittest.main()
