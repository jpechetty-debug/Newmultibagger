import pandas as pd
import numpy as np
import config
from modules.allocation_hrp import HRPAllocator

class PortfolioOptimizer:
    """
    Implements 'Risk Parity' (Inverse Volatility) Optimization.
    Allocates more capital to lower volatility stocks to equalize risk contribution.
    Enforces Hard Constraints:
    - Max Single Stock Weight: 10%
    - Max Sector Weight: 25%
    """
    

    
    # Transaction Cost Model (India/NSE)
    COSTS = {
        'stt': 0.002,           # 0.2% round-trip (Delivery)
        'brokerage': 0.0006,    # 0.03% each way (Institutional/Pro rate)
        'slippage': 0.0015,     # 0.15% avg impact cost (Small/Midcap)
    }

    def __init__(self, capital=100000):
        self.total_capital = capital
        self.max_single_weight = 0.10
        self.min_single_weight = 0.02
        self.max_sector_weight = config.MAX_SECTOR_EXPOSURE
        
    @staticmethod
    def net_returns_after_costs(gross_return, turnover_pa):
        """
        Adjusts returns for transaction costs.
        turnover_pa: Annual portfolio turnover (e.g., 2.0 = 200%)
        """
        total_cost = sum(PortfolioOptimizer.COSTS.values())
        drag = total_cost * turnover_pa
        drag = total_cost * turnover_pa
        return gross_return - drag
        

    def optimize_allocation(self, stocks, history_df=None, method="risk_parity"):
        """
        Calculates optimal weights for a list of stocks.
        
        Args:
            stocks (list of dict): Must contain 'Symbol', 'Sector', 'ATR', 'Price'.
            history_df (pd.DataFrame): Optional. Historical closing prices.
            method (str): 'risk_parity' or 'hrp'.
            
        Returns:
            pd.DataFrame: Portfolio with 'Allocated_Weight', 'Qty', 'Value'.
        """
        if not stocks:
            return pd.DataFrame()
            
        df = pd.DataFrame(stocks)
        
        if method == "hrp" and history_df is not None and not history_df.empty:
            print("[INFO] Applying HRP Allocation...")
            allocator = HRPAllocator(max_single_weight=self.max_single_weight, min_single_weight=self.min_single_weight)
            # Ensure price history matches symbols
            symbols = df['Symbol'].tolist()
            # Returns are needed for HRP
            hrp_weights = allocator.allocate(history_df[symbols].pct_change().dropna())
            df['Raw_Weight'] = df['Symbol'].map(hrp_weights).fillna(0.0)
        else:
            # 1. Calculate Volatility (ATR %)
            # Volatility = ATR / Price
            # Fallback to 1.0 (High Vol) if data missing to penalize it.
            df['Volatility'] = df.apply(lambda x: (x.get('ATR', 0) / x.get('Price', 1)) if x.get('Price', 1) > 0 else 0.05, axis=1)
            df['Volatility'] = df['Volatility'].replace(0, 0.05) # Avoid division by zero
            
            # 2. Inverse Volatility Weights (Risk Parity)
            df['Inv_Vol'] = 1 / df['Volatility']
            
            # --- CORRELATION PENALTY (v2.4) ---
            if history_df is not None and not history_df.empty:
                print("[INFO] Applying Correlation Penalty...")
                # ... existing correlation penalty logic ...
            # Calculate Correlation Matrix
            corr_matrix = history_df.corr()
            
            # Map Symbol to Score (if available) for tie-breaking
            # We assume 'Score' is in stocks list.
            scores = {row['Symbol']: row.get('Score', 0) for _, row in df.iterrows()}
            
            penalty_map = {symbol: 1.0 for symbol in df['Symbol']}
            
            # Iterate unique pairs
            symbols = [s for s in df['Symbol'] if s in corr_matrix.columns]
            for i in range(len(symbols)):
                for j in range(i + 1, len(symbols)):
                    s1 = symbols[i]
                    s2 = symbols[j]
                    correlation = corr_matrix.loc[s1, s2]
                    
                    if correlation > 0.7:
                        score1 = scores.get(s1, 0)
                        score2 = scores.get(s2, 0)
                        victim = s2 if score1 >= score2 else s1
                        
                        # Apply Continuous Penalty (v2.5)
                        # Formula: Factor = (Correlation - 0.7) / 0.3
                        # Example: 1.0 -> 1.0 (100% Penalty)
                        # Example: 0.85 -> 0.5 (50% Penalty)
                        # Example: 0.70 -> 0.0 (0% Penalty)
                        
                        penalty_factor = (correlation - 0.7) / 0.3
                        penalty_factor = min(max(penalty_factor, 0.0), 1.0) # Clip 0-1
                        
                        # Apply penalty
                        # New Weight = Old Weight * (1 - Penalty Factor)
                        penalty_map[victim] *= (1.0 - penalty_factor)
                        
                        print(f"  > High Corr ({correlation:.2f}) {s1} vs {s2}. Penalty Factor: {penalty_factor:.2f} on {victim}.")
                        
            # Apply Penalty to Inv_Vol
            df['Penalty'] = df['Symbol'].map(penalty_map).fillna(1.0)
            df['Inv_Vol'] = df['Inv_Vol'] * df['Penalty']
            
        total_inv_vol = df['Inv_Vol'].sum()
        df['Raw_Weight'] = df['Inv_Vol'] / total_inv_vol
        
        # 3. Apply Constraints (Strict Clipping with Cash Drag)
        # We do NOT re-normalize upwards. This prevents breaching max weights.
        
        weights = df['Raw_Weight'].values
        sectors = df['Sector'].values
        
        # A. Initial Normalization to 100%
        # (This is adjusting relative weights so they sum to 1 before clipping)
        if np.sum(weights) > 0:
            weights = weights / np.sum(weights)
            
        # B. Clip Single Stock Max
        # Any weight > 10% is clipped. The excess becomes Cash.
        weights = np.minimum(weights, self.max_single_weight)
        
        # C. Clip Sector Max
        # Build a map of Sector -> Total Weight
        sec_map = {}
        for idx, w in enumerate(weights):
            sec = sectors[idx]
            sec_map[sec] = sec_map.get(sec, 0) + w
            
        # Check for breaches and scale down
        for sec, total_w in sec_map.items():
            if total_w > self.max_sector_weight:
                # Scale down factor (e.g., 0.25 / 0.40 = 0.625)
                scale = self.max_sector_weight / total_w
                
                # Log Rejection (Partial)
                try:
                    from modules.risk import RiskGovernor
                    rg = RiskGovernor()
                    rg.log_rejected_trade(f"SECTOR:{sec}", f"Sector Capped {total_w:.1%} > {self.max_sector_weight:.1%}", 0.0)
                except Exception as e:
                    print(f"[ERROR] Logging Failed: {e}")
                
                # Apply to all stocks in this sector
                for idx, s in enumerate(sectors):
                    if s == sec:
                        weights[idx] *= scale
        
        # D. Assign Final Weights
        df['Allocated_Weight'] = weights
        df['Allocated_Value'] = df['Allocated_Weight'] * self.total_capital
        df['Qty'] = (df['Allocated_Value'] / df['Price']).astype(int)
        
        # Calculate Cash
        total_allocated_weight = np.sum(weights)
        cash_weight = 1.0 - total_allocated_weight
        
        print(f"Optimization Result: Invested {total_allocated_weight:.1%}, Cash {cash_weight:.1%}")
        
        return df[['Symbol', 'Sector', 'Price', 'Volatility', 'Allocated_Weight', 'Allocated_Value', 'Qty']]

    def check_ltcg_eligibility(self, position):
        """
        Likely v2.9 Enhancement: Tax-Aware Holding Logic.
        Determines if a position should be held longer to qualify for LTCG (12.5%) 
        vs STCG (20%).
        
        Args:
            position (dict): Must contain 'entry_date', 'current_value', 'cost_basis', 'volatility'.
            
        Returns:
            bool: True if we should hold for tax benefits, False otherwise.
        """
        # Placeholder for v2.9 Logic
        # 1. Calculate Unreaized Gain
        # 2. Calculate Tax Savings (7.5% diff)
        # 3. Calculate Expected Risk (Volatility * time_to_1yr)
        # 4. Return True if Tax Savings > Expected Risk
        return False # Default to normal exit for now
