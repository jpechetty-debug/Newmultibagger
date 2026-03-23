from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import pandas as pd

class DataSource(ABC):
    """
    Abstract base class for data sources.
    All sources must implement these methods to be compatible with DataSourceManager.
    """
    
    @abstractmethod
    def fetch_fundamentals(self, symbol: str) -> Dict:
        """
        Fetch fundamental data for a given symbol.
        Expected keys in return dict:
        - info: Dict
        - financials: pd.DataFrame
        - balance_sheet: pd.DataFrame
        - cash_flow: pd.DataFrame (optional)
        """
        pass

    @abstractmethod
    def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """
        Fetch historical price data.
        Returns DataFrame with columns: Open, High, Low, Close, Volume
        """
        pass
    
    @abstractmethod
    def fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        """
        Fetch quarterly financial results (Revenue, Net Income) for UI timeline.
        Returns list of dicts:
        [
            {"date": "Jun '23", "revenue": 100.0, "profit": 10.0, "growth": 5.2},
            ...
        ]
        """
        pass

    # Optional async versions. Implementations can override these to provide native async,
    # otherwise the manager will wrap the synchronous ones.
    async def async_fetch_fundamentals(self, symbol: str) -> Dict:
        import asyncio
        return await asyncio.to_thread(self.fetch_fundamentals, symbol)

    async def async_fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        import asyncio
        return await asyncio.to_thread(self.fetch_history, symbol, period)

    async def async_fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        import asyncio
        return await asyncio.to_thread(self.fetch_quarterly_results, symbol)
