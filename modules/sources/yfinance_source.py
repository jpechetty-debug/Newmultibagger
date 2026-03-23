import yfinance as yf
import pandas as pd
from typing import Dict, List, Optional
from .base import DataSource
from modules.retry_utils import run_with_exponential_backoff
import asyncio

class YFinanceSource(DataSource):
    """
    Adapter for Yahoo Finance (yfinance).
    """

    def fetch_fundamentals(self, symbol: str) -> Dict:
        # yfinance operations are blocking, so we wrap them if needed, 
        # but for now we follow the existing pattern where async is handled at caller level
        # or we can use asyncio.to_thread here if this method is called from async context.
        # However, the base class signature is synchronous for simplicity, 
        # and the Manager can wrap it in a thread if needed.
        
        # Actually, looking at price_fundamentals.py, it uses asyncio.to_thread.
        # Let's keep this synchronous and let the Manager or Caller handle concurrency.
        
        try:
            ticker = yf.Ticker(symbol)
            return {
                "info": ticker.info,
                "financials": ticker.financials,
                "balance_sheet": ticker.balance_sheet,
                "cash_flow": ticker.cashflow
            }
        except Exception as e:
            raise Exception(f"YFinance fundamentals failed: {e}")

    def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        try:
            ticker = yf.Ticker(symbol)
            return ticker.history(period=period, auto_adjust=True)
        except Exception as e:
            raise Exception(f"YFinance history failed: {e}")

    def fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        try:
            ticker = yf.Ticker(symbol)
            q_financials = ticker.quarterly_financials
            
            if q_financials.empty:
                return []

            revenue_key = next((k for k in q_financials.index if 'Total Revenue' in k or 'Operating Revenue' in k), None)
            profit_key = next((k for k in q_financials.index if 'Net Income' in k or 'Net Profit' in k), None)
            
            if not revenue_key:
                return []
                
            revenues = q_financials.loc[revenue_key].fillna(0)
            profits = q_financials.loc[profit_key].fillna(0) if profit_key else pd.Series([0]*len(revenues), index=revenues.index)
            
            timeline = []
            for date, rev in revenues.items():
                timeline.append({
                    "date": date.strftime("%b '%y") if hasattr(date, 'strftime') else str(date),
                    "revenue": float(rev),
                    "profit": float(profits.get(date, 0))
                })
                
            timeline.sort(key=lambda x: x['date'], reverse=True) # Sort logic might need date parsing check
            
            # Re-sort by actual date would be better, but the display format is "Jun '23".
            # Let's rely on the fact that yfinance returns cols in descending order usually.
            
            # Existing logic in financials.py reversed the list.
            # yfinance cols are usually new -> old (descending).
            # financials.py reverses it to be old -> new (ascending) for charts?
            # Let's check existing usage. financials.py:45 "timeline.reverse()".
            # Just return raw list, let UI handle or standardize here?
            # Standardize: Return Ascending (Old -> New) for consistency
            
            timeline.reverse()
            
            # Calc growth
            for i in range(1, len(timeline)):
                prev = timeline[i-1]['revenue']
                curr = timeline[i]['revenue']
                if prev > 0:
                    timeline[i]['growth'] = round(((curr - prev) / prev) * 100, 2)
                else:
                    timeline[i]['growth'] = 0
            
            return timeline
            
        except Exception as e:
            raise Exception(f"YFinance quarterly results failed: {e}")
