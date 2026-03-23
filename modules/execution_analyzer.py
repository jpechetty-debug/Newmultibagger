
import sqlite3
import pandas as pd
import numpy as np
import os
from datetime import datetime
try:
    import config
except ImportError:
    # If running standalone, config might not be importable directly
    pass

DB_NAME = "stocks.db"

class ExecutionAnalyzer:
    """
    Phase 50: Execution Calibration Layer.
    Ingests trade fills, calculates slippage, and updates risk models.
    """
    
    def __init__(self, db_path=None):
        self.db_path = db_path if db_path else DB_NAME
        self.conn = None

    def _get_conn(self):
        if self.conn is None:
             self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self.conn

    def ingest_fills(self, df):
        """
        Ingest a DataFrame of trade fills.
        Expected Columns: symbol, side, fill_price, expected_price (optional), timestamp
        """
        print(f"📥 Ingesting {len(df)} fills...")
        
        # Normalize Columns
        df.columns = [c.strip().lower().replace(" ", "_").replace("symbol", "symbol").replace("scrip", "symbol") for c in df.columns]
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        records = []
        for _, row in df.iterrows():
            symbol = row.get('symbol', 'UNKNOWN')
            side = row.get('side', 'BUY').upper()
            fill_price = float(row.get('fill_price', 0))
            expected_price = float(row.get('expected_price', 0))
            
            # Slippage Calculation
            slippage_bps = 0.0
            if expected_price > 0:
                if side == 'BUY':
                    slippage = (fill_price - expected_price) / expected_price
                else: # SELL
                    slippage = (expected_price - fill_price) / expected_price
                
                slippage_bps = slippage * 10000
            
            # Context Lookup (for this MVP phase, we approximate)
            # Fetch Tier from DB
            tier = "UNKNOWN"
            try:
                # We need a separate connection or reuse carefully if threading
                # Simple lookup:
                curr = conn.cursor()
                curr.execute("SELECT market_cap_cr FROM multibaggers WHERE symbol = ?", (symbol,))
                res = curr.fetchone()
                if res:
                    mc = res[0]
                    if mc > 50000: tier = "LARGE_CAP"
                    elif mc > 15000: tier = "MID_CAP"
                    elif mc > 5000: tier = "SMALL_CAP"
                    else: tier = "MICRO_CAP"
            except Exception as e:
                print(f"Tier lookup failed: {e}")

            regime = "UNKNOWN" # Placeholder
            vix = 15.0 # Placeholder
            timestamp = row.get('timestamp', datetime.now().isoformat())
            
            records.append((
                symbol, side, expected_price, fill_price, slippage_bps,
                tier, regime, vix, timestamp, "CSV_IMPORT"
            ))

        if not records:
            print("⚠️ No valid records to insert.")
            return

        cursor.executemany('''
            INSERT INTO executions (symbol, side, expected_price, fill_price, slippage_bps, liquidity_tier, regime, vix, timestamp, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', records)
        conn.commit()
        print(f"✅ Ingested {len(records)} fill records.")
        
        # Trigger Recalibration
        self.update_metrics()

    def update_metrics(self):
        """
        Recalculate rolling 30-day slippage statistics.
        """
        print("🔄 Recalibrating Slippage Models...")
        
        conn = self._get_conn()
        
        # We need to compute stats grouped by Tier
        # Use pandas for easier quantile calcs
        try:
            df = pd.read_sql("SELECT liquidity_tier, slippage_bps FROM executions", conn)
        except Exception as e:
            print(f"Error reading executions: {e}")
            return
            
        if df.empty:
            print("No execution data found.")
            return

        cursor = conn.cursor()
        
        # Group by Tier
        for tier, group in df.groupby('liquidity_tier'):
            if tier == "UNKNOWN": continue
            
            p50 = group['slippage_bps'].median()
            p75 = group['slippage_bps'].quantile(0.75)
            p95 = group['slippage_bps'].quantile(0.95)
            count = len(group)
            
            # Upsert
            cursor.execute('''
                DELETE FROM slippage_metrics WHERE tier = ? AND regime = 'ALL' AND time_window = '30D'
            ''', (tier,))
            
            cursor.execute('''
                INSERT INTO slippage_metrics (tier, time_window, regime, p50_bps, p75_bps, p95_bps, count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tier, "30D", "ALL", float(p50), float(p75), float(p95), int(count), datetime.now()))
            
        conn.commit()
        print("✅ Slippage metrics updated.")

    def get_calibrated_slippage(self, tier):
        """
        Returns the p95 slippage in BPS for the given Tier.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p95_bps FROM slippage_metrics 
            WHERE tier = ? AND regime = 'ALL'
        ''', (tier,))
        row = cursor.fetchone()
        
        if row:
            return row[0]
        return None 

if __name__ == "__main__":
    # Test
    analyzer = ExecutionAnalyzer()
    # Dummy data
    data = {
        'symbol': ['RELIANCE.NS', 'TCS.NS'],
        'side': ['BUY', 'BUY'],
        'fill_price': [2505, 3510],
        'expected_price': [2500, 3500]
    }
    df = pd.DataFrame(data)
    analyzer.ingest_fills(df)
    print(analyzer.get_calibrated_slippage("LARGE_CAP"))
