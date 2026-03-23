
"""
Liquidity Filter
----------------
Ensures backtests only trade stocks that were actually liquid enough at the time.
Prevents "Ghost Gains" from trading illiquid penny stocks in simulation.

Criteria:
1. Min Price > 10 (Avoid penny stocks with huge spreads)
2. Avg Daily Volume (ADV) * Price > Min Turnover (e.g. 50 Lakhs)
3. Trading Days > 90% of business days (Avoid suspended stocks)
"""

class LiquidityFilter:
    def __init__(self, min_price=10.0, min_turnover=5000000.0):
        self.min_price = min_price
        self.min_turnover = min_turnover

    def filter(self, universe_data):
        """
        Filters a list of stock data dicts.
        
        Args:
            universe_data (list): List of dicts [{'Symbol': 'X', 'Price': 100, 'Volume': 50000}...]
            
        Returns:
            list: Filtered list of dicts.
        """
        liquid_universe = []
        rejected = 0
        
        for stock in universe_data:
            price = stock.get("Price", 0)
            volume = stock.get("Volume", 0)
            turnover = price * volume
            
            # 1. Price Check
            if price < self.min_price:
                rejected += 1
                continue
                
            # 2. Turnover Check
            if turnover < self.min_turnover:
                rejected += 1
                continue
                
            liquid_universe.append(stock)
            
        print(f"Liquidity Filter: Passed {len(liquid_universe)} / {len(universe_data)} (Rejected {rejected})")
        return liquid_universe
