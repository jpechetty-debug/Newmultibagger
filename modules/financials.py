import pandas as pd
import numpy as np
from modules.data_manager import data_manager

def get_quarterly_results(symbol):
    """
    Fetches the last 8 quarters of Revenue and Net Income.
    Returns a list of dictionaries for UI consumption.
    """
    try:
        # yfinance expects .NS for NSE stocks
        if not symbol.endswith('.NS') and not symbol.endswith('.BO'):
            symbol += '.NS'
            
        timeline = data_manager.fetch_quarterly_results(symbol)
        
        if not timeline:
             return {"error": "No quarterly data found"}
             
        # DataSourceManager already returns the list of dicts in correct format
        # {"date": ..., "revenue": ..., "profit": ..., "growth": ...}
        
        return {
            "symbol": symbol,
            "timeline": timeline
        }

    except Exception as e:
        return {"error": str(e)}
