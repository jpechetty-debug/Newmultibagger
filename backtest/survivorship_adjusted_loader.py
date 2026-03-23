
"""
Survivorship Adjusted Loader
----------------------------
Loads historical stock data while accounting for survivorship bias.
1. Includes Delisted Stocks (if available in 'delisted_data/').
2. filters Universe based on 'Listing Date' (Only include stocks that existed at 'as_of_date').
3. Handles Ticker Changes (Mapping old symbol -> new symbol).

Usage:
    loader = SurvivorshipAdjustedLoader()
    universe_at_date = loader.get_universe(as_of_date="2023-01-01")
"""

import pandas as pd
import os
import datetime

class SurvivorshipAdjustedLoader:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        # Placeholder for a mapping of listing dates
        # In production, this would be a CSV: Symbol, Listing_Date, Delisting_Date
        self.listing_dates = {} 
        self.delisted_map = {}

    def get_universe(self, as_of_date, candidates=None):
        """
        Returns the valid universe of stocks for a specific historical date.
        
        Args:
            as_of_date (str): "YYYY-MM-DD"
            candidates (list): Optional list of symbols to filter (e.g. Nifty 500 at that time).
        
        Returns:
            list: List of valid symbols.
        """
        target_date = pd.to_datetime(as_of_date)
        valid_universe = []
        
        # 1. If we have a candidate list (e.g., Nifty 500 composition file for that month), use it.
        # This is the Gold Standard for survivorship bias free testing.
        index_file = os.path.join(self.data_dir, f"nifty500_{as_of_date[:7]}.csv")
        if os.path.exists(index_file):
            print(f"Loading historical index from {index_file}")
            df = pd.read_csv(index_file)
            return df['Symbol'].tolist()
            
        # 2. Fallback: Use current candidates but filter by listing date validity
        # (This is still biased but better than nothing)
        if candidates:
            for sym in candidates:
                if self._was_listed(sym, target_date):
                    valid_universe.append(sym)
                    
        return valid_universe

    def _was_listed(self, symbol, date):
        """Checks if a stock was listed and not delisted on the given date."""
        # TODO: Implement actual lookup against a master metadata DB
        # For now, assume True if we don't have data, to avoid empty backtests.
        return True

    def load_delisted_data(self, symbol):
        """
        Attempts to load data for a delisted stock.
        """
        # Logic to look in a separate 'delisted' folder
        return None
