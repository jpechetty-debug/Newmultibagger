import unittest
import os
import csv
import sys

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.risk import RiskGovernor
from modules.optimizer import PortfolioOptimizer

class TestBlackBoxRecorder(unittest.TestCase):
    """
    Validates Phase 7: Black Box Recorder.
    Ensures rejected trades lead to entries in 'rejected_trades.csv'.
    """
    
    def setUp(self):
        # Clean up previous log
        if os.path.exists('rejected_trades.csv'):
            os.remove('rejected_trades.csv')
            
        self.risk = RiskGovernor()
        self.optimizer = PortfolioOptimizer()
        
    def tearDown(self):
        # Clean up after test to avoid polluting dashboard/logs
        if os.path.exists('rejected_trades.csv'):
            os.remove('rejected_trades.csv')

    def test_risk_rejection_logging(self):
        print("\n[TEST] Testing Risk Rejection Logging...")
        
        # 1. Trigger Kill Switch
        # Dynamic Threshold 15, current 20 -> Should Log
        self.risk.check_kill_switch(20.0, dynamic_threshold=15.0)
        
        # 2. Trigger Hard Kill Drawdown
        # DD 20%, VIX 35, Bear -> Should Log
        self.risk.calculate_max_capital_at_risk(100000, 20, {'vix': 35, 'regime': 'BEAR'})
        
        # 3. Trigger Crisis Correlation
        # Corr 0.8 -> Should Log
        self.risk.validate_correlation_risk(0.80)
        
        # Verify Log File
        self.assertTrue(os.path.exists('rejected_trades.csv'), "Log file not created")
        
        with open('rejected_trades.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
            
        print(f"   Rows Found: {len(rows)}")
        # Header + 3 entries = 4 rows
        self.assertEqual(len(rows), 4, "Expected Header + 3 Risk Logs")
        self.assertEqual(rows[0], ['Timestamp', 'Symbol', 'Reason', 'Price_Context'])
        self.assertIn('Kill Switch Active', rows[1][2])

    def test_optimizer_sector_logging(self):
        print("\n[TEST] Testing Optimizer Sector Logging...")
        
        # Create a portfolio heavily concentrated in one sector
        stocks = [
             {'Symbol': 'A', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0},
             {'Symbol': 'B', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0},
             {'Symbol': 'C', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0},
             {'Symbol': 'D', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0}
        ]
        
        # Force Sector Cap to be very low for this test instance
        self.optimizer.max_sector_weight = 0.2 # 20%
        # With 4 stocks, inv vol is equal.
        # Each gets 10% (capped by single stock). Total Tech = 40%.
        # 40% > 20%. Constraint should kick in and Log.
        
        self.optimizer.optimize_allocation(stocks)
        
        # Read Log again (append mode)
        with open('rejected_trades.csv', 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        found = False
        for line in lines:
            if "SECTOR:Tech" in line and "Sector Capped" in line:
                found = True
                print(f"   ✅ Found Optim Log: {line.strip()}")
                break
                
        self.assertTrue(found, "Sector Cap log entry not found")

if __name__ == '__main__':
    unittest.main()
