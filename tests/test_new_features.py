import sys
import os
import json
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
from unittest.mock import MagicMock, patch

from modules.thesis_monitor import record_buy_thesis, check_thesis, check_all_thesis_breaks
from modules.promoter_intel import calculate_promoter_score
from modules.estimates import analyze_estimate_momentum, compute_own_estimate

class TestNewFeatures(unittest.TestCase):
    
    def setUp(self):
        # Set up a temporary test database
        self.test_db = "test_stocks.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
            
        # Patch the DB_NAME in the modules to use the test database
        self.patcher1 = patch("modules.thesis_monitor.DB_NAME", self.test_db)
        self.patcher2 = patch("modules.promoter_intel.DB_NAME", self.test_db)
        self.patcher1.start()
        self.patcher2.start()
        
        # Initialize the test database schema
        conn = sqlite3.connect(self.test_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS buy_thesis (
                symbol TEXT PRIMARY KEY,
                buy_date TEXT,
                primary_driver TEXT,
                revenue_growth_min REAL,
                operating_margin_min REAL,
                score_at_buy REAL,
                checklist_passes_at_buy INTEGER,
                regime_at_buy TEXT,
                raw_thesis_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS multibaggers (
                symbol TEXT PRIMARY KEY,
                price REAL,
                score REAL,
                sales_growth REAL,
                roe REAL,
                f_score INTEGER,
                debt_equity REAL,
                promoter_holding REAL,
                inst_holding REAL
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_feature_a_thesis_recording_and_check(self):
        """Test recording a thesis and then checking it for breaks."""
        symbol = "TEST.NS"
        stock_data = {
            "Symbol": symbol,
            "Price": 100,
            "Sales_Growth_TTM%": 20,
            "Profit_Margin%": 15,
            "Sector": "Technology",
            "Industry": "Software",
            "Avg_ROE_5Y%": 25,
            "F_Score": 8,
            "Value_Gap%": 30,
            "Promoter_Holding%": 70,
            "EPS_Growth%": 20
        }
        
        # 1. Record Thesis
        record_buy_thesis(symbol, stock_data, score=85, checklist_passes=10, regime="BULL")
        
        # Verify it's in the DB
        conn = sqlite3.connect(self.test_db)
        row = conn.execute("SELECT * FROM buy_thesis WHERE symbol = ?", (symbol,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], symbol)
        self.assertEqual(row[3], 20 * 0.8) # revenue_growth_min
        
        # 2. Check Thesis (Intact)
        # Insert "current" data into multibaggers table
        conn = sqlite3.connect(self.test_db)
        conn.execute("""
            INSERT INTO multibaggers (symbol, price, score, sales_growth, roe, f_score, debt_equity, promoter_holding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, 110, 85, 20, 25, 8, 0.2, 70))
        conn.commit()
        conn.close()
        
        status = check_thesis(symbol)
        self.assertEqual(status.status, "INTACT")
        self.assertEqual(status.badge_color, "green")
        
        # 3. Check Thesis (Break - Revenue Collapse)
        conn = sqlite3.connect(self.test_db)
        conn.execute("UPDATE multibaggers SET sales_growth = 5 WHERE symbol = ?", (symbol,))
        conn.commit()
        conn.close()
        
        status = check_thesis(symbol)
        self.assertEqual(status.status, "WARNING") # 1 break is warning
        self.assertEqual(len(status.breaks), 1)
        self.assertIn("Revenue Growth", status.breaks[0]["metric"])
        
        # 4. Check Thesis (Total Break - Revenue + Score Collapse)
        conn = sqlite3.connect(self.test_db)
        conn.execute("UPDATE multibaggers SET score = 50 WHERE symbol = ?", (symbol,))
        conn.commit()
        conn.close()
        
        status = check_thesis(symbol)
        self.assertEqual(status.status, "THESIS_BREAK") # 2 breaks
        self.assertEqual(status.badge_color, "red")
        self.assertEqual(len(status.breaks), 2)

    def test_feature_b_promoter_score(self):
        """Test promoter behavior scoring."""
        base_trend = {
            "symbol": "TEST.NS",
            "promoter_holding_current": 50,
            "pledge_current": 0,
            "pledge_direction": "STABLE",
            "insider_net_action": "NEUTRAL",
            "insider_buy_count": 0,
            "insider_sell_count": 0,
            "insider_deals": [],
            "institutional_holding_current": 10,
            "promoter_change_direction": "STABLE",
            "data_sources": ["test"]
        }

        # Case 1: Neutral
        with patch("modules.promoter_intel.get_promoter_trend") as mock_trend:
            mock_trend.return_value = base_trend.copy()
            score = calculate_promoter_score("TEST.NS")
            self.assertEqual(score["score_adjustment"], 0)
            self.assertFalse(score["is_disqualified"])
            self.assertEqual(score["signal"], "🟢") # Green by default for 0

        # Case 2: Promoter Buying (Bonus)
        with patch("modules.promoter_intel.get_promoter_trend") as mock_trend:
            trend = base_trend.copy()
            trend["insider_net_action"] = "NET_BUYER"
            mock_trend.return_value = trend
            score = calculate_promoter_score("TEST.NS")
            self.assertEqual(score["score_adjustment"], 4)
            self.assertIn("Promoter accumulating", score["signal_text"])

        # Case 3: Insider Dumping (Disqualified D15)
        with patch("modules.promoter_intel.get_promoter_trend") as mock_trend:
            trend = base_trend.copy()
            trend["insider_buy_count"] = 0
            trend["insider_sell_count"] = 5
            trend["insider_net_action"] = "NET_SELLER"
            mock_trend.return_value = trend
            score = calculate_promoter_score("TEST.NS")
            self.assertTrue(score["is_disqualified"])
            self.assertEqual(score["score_adjustment"], -8)
            self.assertIn("Heavy insider dumping", score["signal_text"])

    def test_feature_c_estimate_momentum(self):
        """Test earnings estimate momentum analysis."""
        # Mock AV earnings data
        earnings_data = {
            "quarterly": [
                {"date": "2023-12-31", "estimated_eps": "100", "reported_eps": "110", "surprise_pct": "10"}, # Most recent beat
                {"date": "2023-09-30", "estimated_eps": "90", "reported_eps": "95", "surprise_pct": "5"}, # Beat
                {"date": "2023-06-30", "estimated_eps": "80", "reported_eps": "85", "surprise_pct": "6"}, # Beat
                {"date": "2023-03-31", "estimated_eps": "70", "reported_eps": "75", "surprise_pct": "7"}, # Beat (4Q beat streak)
            ]
        }
        
        # Test 4Q Beat Streak
        momentum = analyze_estimate_momentum(earnings_data)
        self.assertEqual(momentum["momentum_signal"], "STRONG_UP") # because QoQ estimates are rising (100 > 90 > 80 > 70)
        self.assertEqual(momentum["score_adjustment"], 8) # 5 (upgrades) + 3 (beat streak)
        self.assertIn("4Q consecutive earnings beat", momentum["display_text"])
        
        # Test Estimate Upgrades (3Q consecutive)
        earnings_data["quarterly"] = [
            {"date": "Q1", "estimated_eps": "120", "reported_eps": "120"}, # 120
            {"date": "Q2", "estimated_eps": "110", "reported_eps": "110"}, # 110
            {"date": "Q3", "estimated_eps": "100", "reported_eps": "100"}, # 100
            {"date": "Q4", "estimated_eps": "90", "reported_eps": "90"},  # 90
        ]
        # Estimates: 120 > 110 > 100 > 90 (3 consecutive upgrades)
        momentum = analyze_estimate_momentum(earnings_data)
        self.assertEqual(momentum["momentum_signal"], "STRONG_UP")
        self.assertEqual(momentum["score_adjustment"], 5) # +5 for 3 upgrades
        
        # Test Estimate Downgrades (3Q consecutive - D16)
        earnings_data["quarterly"] = [
            {"date": "Q1", "estimated_eps": "80", "reported_eps": "80"}, 
            {"date": "Q2", "estimated_eps": "90", "reported_eps": "90"}, 
            {"date": "Q3", "estimated_eps": "100", "reported_eps": "100"}, 
            {"date": "Q4", "estimated_eps": "110", "reported_eps": "110"}, 
        ]
        # Estimates: 80 < 90 < 100 < 110 (3 consecutive downgrades)
        momentum = analyze_estimate_momentum(earnings_data)
        self.assertTrue(momentum["is_disqualified"])
        self.assertEqual(momentum["score_adjustment"], -5)

    def test_compute_own_estimate(self):
        """Test fallback EPS estimate computation."""
        info = {
            "trailingEps": 10,
            "earningsGrowth": 0.20,
            "revenueGrowth": 0.15
        }
        est = compute_own_estimate(info)
        # 10 * (1 + (0.2 + 0.02)) = 10 * 1.22 = 12.2
        self.assertEqual(est["current_fy_eps_estimate"], 12.2)
        self.assertEqual(est["next_fy_eps_estimate"], round(12.2 * 1.22, 2))

if __name__ == "__main__":
    unittest.main()
