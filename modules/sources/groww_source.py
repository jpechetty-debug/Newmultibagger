import requests
import pandas as pd
from typing import Dict, List, Optional
from .base import DataSource
from modules.retry_utils import run_with_exponential_backoff

class GrowwSource(DataSource):
    """
    Adapter for Groww APIs.
    Based on reverse-engineered endpoints commonly used by community tools.
    """
    
    BASE_URL = "https://groww.in/v1/api"
    
    # Common headers used in 'groww-trader' or similar
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Content-Type": "application/json"
    }
    
    def fetch_fundamentals(self, symbol: str) -> Dict:
        # Groww uses its own internal ID system often, but search by symbol works.
        clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
        
        # 1. Search for the script to get groww contract id
        search_url = f"{self.BASE_URL}/search/v1/entity?app=false&page=0&q={clean_symbol}&size=1"
        try:
            search_res = requests.get(search_url, headers=self.HEADERS, timeout=10)
            if search_res.status_code != 200:
                raise Exception(f"Groww Search failed: {search_res.status_code}")
                
            search_data = search_res.json()
            if not search_data.get('content'):
                raise Exception("Symbol not found on Groww")
                
            entity_id = search_data['content'][0]['id']
            contract_id = search_data['content'][0].get('nseScriptCode') # or similar field
            
            # 2. Get details using entity_id
            # Endpoint: /stocks_data/v1/company/search_id/{entity_id}
            # Or /stocks_data/v1/stocks/{entity_id}
            details_url = f"{self.BASE_URL}/stocks_data/v1/stocks/{entity_id}"
            details_res = requests.get(details_url, headers=self.HEADERS, timeout=10)
            
            if details_res.status_code != 200:
                # Try company endpoint if stock endpoint fails
                details_url = f"{self.BASE_URL}/stocks_data/v1/company/search_id/{entity_id}"
                details_res = requests.get(details_url, headers=self.HEADERS, timeout=10)
            
            if details_res.status_code != 200:
                raise Exception(f"Groww Details failed: {details_res.status_code}")
                
            data = details_res.json()
            
            # Map to expected structure
            live_price = data.get('livePriceDto', {})
            stats = data.get('stats', {}) # might contain marketCap, pe, etc.
            
            mapped_info = {
                "longName": data.get("companyName"),
                "symbol": data.get("nseScriptCode"),
                "currentPrice": live_price.get("ltp"),
                "dayLow": live_price.get("low"),
                "dayHigh": live_price.get("high"),
                "marketCap": stats.get("marketCap"),
                "pb": stats.get("pbRatio"),
                "pe": stats.get("peRatio"),
                "bookValue": stats.get("bookValue"),
                "eps": stats.get("eps"),
                # Add more mapping as discovered
            }
            
            return {
                "info": mapped_info,
                "financials": pd.DataFrame(), # Financials usually require separate calls
                "balance_sheet": pd.DataFrame(),
                "cash_flow": pd.DataFrame()
            }
            
        except Exception as e:
            raise Exception(f"Groww fundamentals failed: {e}")

    def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        # Groww does not expose a public history API — return empty so manager falls through
        return pd.DataFrame()

    def fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        # Groww quarterly data not available via public API — return empty
        return []
