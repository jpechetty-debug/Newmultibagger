
"""
Pre-Market Governance Scanner
-----------------------------
Runs at 08:00 AM.
Scans all Portfolio Stocks + Watchlist for Governance Red Flags using NewsGate.
Generates a 'KILL LIST' if any critical keywords are found.

Usage:
    python brain/pre_market_scan.py
"""

import sys
import os
import asyncio
import pandas as pd
from datetime import datetime

# Add project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.news_gate import NewsGate
from modules.news import get_stock_news
import database

class PreMarketScanner:
    def __init__(self):
        self.gate = NewsGate()
        self.conn = database.get_connection()

    def get_monitored_stocks(self):
        """
        Returns list of symbols to monitor (Portfolio + Watchlist).
        For now, we scan everything in 'multibaggers' table that has a score > 0 
        or is in our portfolio (mocked logic for portfolio).
        """
        try:
            # In real system, join with 'portfolio' table.
            # Here we scan the active universe.
            query = "SELECT symbol FROM multibaggers WHERE score > 50" 
            df = pd.read_sql(query, self.conn)
            return df['symbol'].tolist()
        except Exception as e:
            print(f"DB Error: {e}")
            return []
        finally:
            self.conn.close()

    async def scan(self):
        print(f"\n🚫 PRE-MARKET GOVERNANCE SCAN ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
        print("=" * 60)
        
        symbols = self.get_monitored_stocks()
        if not symbols:
            print("No stocks to scan.")
            return

        print(f"Scanning {len(symbols)} stocks for News Red Flags...")
        
        # Batch fetch news
        tasks = [get_stock_news(sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        kill_list = []
        
        for sym, news_items in zip(symbols, results):
            if isinstance(news_items, list) and news_items:
                is_clean, reason = self.gate.validate_news(sym, news_items)
                if not is_clean:
                    kill_list.append({"Symbol": sym, "Reason": reason})
                    print(f"💀 KILL SIGNAL: {sym} -> {reason}")
            elif isinstance(news_items, Exception):
                print(f"⚠️ Fetch Error {sym}: {news_items}")

        print("-" * 60)
        if kill_list:
            print(f"❌ FOUND {len(kill_list)} GOVERNANCE RISKS!")
            print("ACTION: IMMEDIATE PRE-MARKET EXIT.")
            # In production, this would generate an 'exits.csv' for the broker.
        else:
            print("✅ All Clean. No Governance Red Flags detected.")
        print("=" * 60)

if __name__ == "__main__":
    scanner = PreMarketScanner()
    asyncio.run(scanner.scan())
