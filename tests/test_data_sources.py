import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from modules.data_manager import DataSourceManager
from modules.sources.yfinance_source import YFinanceSource
from modules.sources.nse_source import NSESource
from modules.sources.groww_source import GrowwSource

class TestDataSourceManager(unittest.TestCase):

    def setUp(self):
        self.manager = DataSourceManager()

    def test_fetch_fundamentals_yfinance_success(self):
        # Mock YFinanceSource to succeed
        with patch.object(YFinanceSource, 'fetch_fundamentals') as mock_yf:
            mock_yf.return_value = {"info": {"symbol": "RELIANCE.NS"}, "financials": pd.DataFrame()}
            
            data = self.manager.fetch_fundamentals("RELIANCE.NS")
            self.assertEqual(data["info"]["symbol"], "RELIANCE.NS")
            mock_yf.assert_called_once()

    def test_fetch_fundamentals_fallback_to_nse(self):
        # Mock YFinance to fail, NSE to succeed
        with patch.object(YFinanceSource, 'fetch_fundamentals') as mock_yf, \
             patch.object(NSESource, 'fetch_fundamentals') as mock_nse:
            
            mock_yf.side_effect = Exception("YF Failed")
            mock_nse.return_value = {"info": {"symbol": "RELIANCE"}, "financials": pd.DataFrame()}
            
            data = self.manager.fetch_fundamentals("RELIANCE.NS")
            self.assertEqual(data["info"]["symbol"], "RELIANCE")
            mock_yf.assert_called_once()
            mock_nse.assert_called_once()

    def test_fetch_fundamentals_all_fail(self):
        # Mock all to fail
        with patch.object(YFinanceSource, 'fetch_fundamentals', side_effect=Exception("Fail")), \
             patch.object(NSESource, 'fetch_fundamentals', side_effect=Exception("Fail")), \
             patch.object(GrowwSource, 'fetch_fundamentals', side_effect=Exception("Fail")):
            
            data = self.manager.fetch_fundamentals("RELIANCE.NS")
            self.assertIn("error", data)
            self.assertEqual(data["error"], "All sources failed")

if __name__ == '__main__':
    unittest.main()
