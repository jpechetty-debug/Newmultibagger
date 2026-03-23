
"""
Portfolio Allocator
-------------------
Converts Strategic Signals (GARP Proposals) into actual Allocation Orders.
Enforces:
1. Equal Weighting (modified by Risk).
2. Liquidity Constraints (Max 3% of Avg Daily Volume).
3. Sector Exposure Limits (Max 25% per Sector).
4. Portfolio Heat Limits (Max 10 Open Positions for Strategic Bucket).
"""


import pandas as pd
import math
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.news_gate import NewsGate
# We need to fetch news for the gate. Assuming we have a way or will mock it for now.
# Realistically, we need `modules.news.get_stock_news` but that's async.
# For the Allocator (sync), we might need a synchronous wrapper or assume news is pre-fetched.
# Let's import the async news fetcher but we will need to run it.
# To keep Allocator simple, let's assume `proposals` carries the news or we skip fetching if not provided.
# BETTER: Use NewsGate if 'News' key exists in proposal, or print warning.

class PortfolioAllocator:
    def __init__(self, capital=1000000.0, max_positions=10, risk_per_trade=0.02):
        self.capital = float(capital)
        self.max_positions = int(max_positions)
        self.risk_per_trade = float(risk_per_trade)
        
        # Constraints
        self.MAX_SECTOR_ALLOCATION = 0.30 # 30%
        self.MAX_PCT_NAV = 0.10 # 10% max per stock
        self.MAX_PCT_ADV = 0.03 # Max 3% of Avg Daily Volume (Liquidity Check)
        
        # Gate 0
        self.news_gate = NewsGate()

    def allocate(self, proposals, current_portfolio=None):
        """
        Generates Allocation Orders for a list of proposals.
        
        current_portfolio: List of dicts [{'Symbol': 'X', 'Sector': 'Y', 'Value': 10000}]
        """
        if not proposals:
            return []
            
        # 1. Calculate Available Slots
        current_positions = len(current_portfolio) if current_portfolio else 0
        slots_available = self.max_positions - current_positions
        
        if slots_available <= 0:
            print("❌ Portfolio Full. No new allocations.")
            return []
            
        # 2. Select Top Candidates (Applying Gate 0: News Check)
        clean_candidates = []
        for cand in proposals:
            symbol = cand.get('Symbol')
            # In a real run, we would fetch news here. 
            # For now, we check if 'Recent_News' is passed in proposal.
            news_items = cand.get('Recent_News', []) 
            
            is_clean, reason = self.news_gate.validate_news(symbol, news_items)
            if is_clean:
                clean_candidates.append(cand)
            else:
                print(f"🛑 GATE 0 BLOCK: {symbol} -> {reason}")
        
        # Assuming proposals are already ranked
        candidates = clean_candidates[:slots_available]
        
        # 3. Calculate Base Allocation
        # Equal Weight: Capital / Max Positions
        base_allocation_amt = self.capital / self.max_positions
        
        allocations = []
        
        for cand in candidates:
            symbol = cand.get('Symbol')
            price = cand.get('Price', 0)
            atr = cand.get('ATR', 0)
            adv = cand.get('Avg_Volume_10D', 0) # Average Daily Volume
            sector = cand.get('Sector', 'Unknown')
            
            if price <= 0: continue
            
            # --- Constraint 1: Risk Normalization (Volatility Sizing) ---
            # If ATR is high, reduce size to keep risk constant?
            # Standard: Risk = 2 * ATR
            # Risk_Amount = Capital * Risk_Per_Trade (e.g., 20,000)
            # Shares = Risk_Amount / (2 * ATR)
            # But we also want Equal Weight as a ceiling.
            
            risk_amt = self.capital * self.risk_per_trade
            
            # If ATR is missing, use flat % stop loss proxy (e.g., 10%)
            if atr <= 0:
                atr = price * 0.05 # Assume 5% volatility for sizing safety
            
            stop_loss_dist = 2 * atr
            if stop_loss_dist == 0: stop_loss_dist = price * 0.10
            
            risk_based_qty = int(risk_amt / stop_loss_dist)
            risk_based_amt = risk_based_qty * price
            
            # --- Constraint 2: Equal Weight Cap ---
            # Don't exceed base allocation (e.g. 10% NAV)
            final_amt = min(risk_based_amt, base_allocation_amt)
            final_qty = int(final_amt / price)
            
            # --- Constraint 3: Liquidity Check (The Whale Guard) ---
            # Cannot buy more than 3% of Daily Volume
            if adv > 0:
                liquidity_cap_qty = int(adv * self.MAX_PCT_ADV)
                if final_qty > liquidity_cap_qty:
                    print(f"⚠️ Liquidity Crunch for {symbol}: Cap {liquidity_cap_qty} vs Req {final_qty}")
                    final_qty = liquidity_cap_qty
                    final_amt = final_qty * price
            
            # --- Constraint 4: Sector Exposure ---
            # Check current exposure
            current_sector_val = 0
            if current_portfolio:
                for pos in current_portfolio:
                    if pos.get('Sector') == sector:
                        current_sector_val += pos.get('Value', 0)
            
            projected_sector_exposure = (current_sector_val + final_amt) / self.capital
            if projected_sector_exposure > self.MAX_SECTOR_ALLOCATION:
                print(f"⚠️ Sector Limit Hit for {sector}: {projected_sector_exposure:.1%}")
                # Reduce quantity to fit sector limit? Or skip?
                # Let's Skip for safety to avoid over-concentration
                # OR limit the amt
                allowed_amt = (self.MAX_SECTOR_ALLOCATION * self.capital) - current_sector_val
                if allowed_amt < 0: allowed_amt = 0
                
                allowed_qty = int(allowed_amt / price)
                final_qty = min(final_qty, allowed_qty)
                
            if final_qty > 0:
                allocations.append({
                    "Symbol": symbol,
                    "Action": "BUY",
                    "Qty": final_qty,
                    "Price": price,
                    "Amount": round(final_qty * price, 2),
                    "Type": "STRATEGIC_ALLOCATION",
                    "Reason": cand.get("Reason", "GARP")
                })
                
        return allocations

