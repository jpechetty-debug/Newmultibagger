
"""
Growth Monitor
--------------
Detects growth deceleration in portfolio stocks.
Acts as an early warning system to exit "Growth" stocks that are becoming "Value" traps.

Signal Triggers:
1. Sales Growth < 15%
2. Profit Growth < 15%
3. PEG > 3.0 (Growth pricing without growth)
"""

class GrowthMonitor:
    def __init__(self):
        self.MIN_SALES_GROWTH = 15.0
        self.MIN_PROFIT_GROWTH = 12.0 # Slightly lower tolerance
        self.MAX_PEG = 3.0

    def check_deceleration(self, stock_data):
        """
        Checks if a stock is decelerating.
        Returns: (is_decelerating, reason)
        """
        symbol = stock_data.get("Symbol", "Unknown")
        
        # 1. Sales Deceleration
        sales_5y = stock_data.get("Sales_Growth_5Y%", 0)
        sales_ttm = stock_data.get("Sales_Growth_TTM%", 0)
        
        # If TTM Sales growth drops significantly below 5Y average or below absolute limit
        if sales_ttm < self.MIN_SALES_GROWTH:
             # Check if it's a massive drop
             if sales_ttm < (sales_5y * 0.5):
                 return True, f"Severe Sales Deceleration: TTM {sales_ttm}% vs 5Y {sales_5y}%"
             elif sales_ttm < 10:
                 return True, f"Sales Growth Collapsed to {sales_ttm}%"

        # 2. Profit Deceleration
        # (Assuming EPS Growth is available)
        eps_growth = stock_data.get("EPS_Growth%", 0)
        if eps_growth < self.MIN_PROFIT_GROWTH:
            return True, f"Profit Growth Stalled: {eps_growth}%"

        # 3. Valuation Mismatch (The PEG Trap)
        peg = stock_data.get("PEG_Ratio", 0)
        if peg > self.MAX_PEG:
            return True, f"Growth Priced for Perfection (PEG {peg}) but Reality Disconnect"

        return False, "Growth Intact"
