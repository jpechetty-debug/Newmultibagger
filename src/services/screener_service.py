import asyncio
import pandas as pd
from typing import List, Optional
from src.core.config import get_settings
from src.core.logging_config import get_logger
from src.data.yfinance_adapter import yfinance_adapter
from src.data.database import db_manager
from src.data.ticker_list import TICKERS

settings = get_settings()
logger = get_logger(__name__)

class ScreenerService:
    async def analyze_stock(self, symbol: str) -> Optional[dict]:
        """Analyze a single stock for Microcap Gems criteria."""
        try:
            info = await yfinance_adapter.get_ticker_info_async(symbol)
            if not info:
                return None

            # --- 1. Market Cap Check ---
            market_cap = info.get('marketCap', 0) or 0
            market_cap_cr = market_cap / 10000000 
            
            # --- 2. Promoter Holding ---
            promoter_holding = info.get('heldPercentInsiders', 0) or 0
            
            # --- 3. Growth ---
            sales_growth = info.get('revenueGrowth', 0) or 0
            profit_margin = info.get('profitMargins', 0) or 0
            
            # --- 4. Valuation ---
            peg_ratio = info.get('pegRatio', 0)
            if peg_ratio is None: peg_ratio = 100
            
            # --- 5. Technical Trend ---
            hist = await yfinance_adapter.get_ticker_history_async(symbol)
            if hist is None or hist.empty:
                return None
                
            current_price = hist['Close'].iloc[-1]
            year_high = hist['Close'].max()
            pct_from_high = (current_price - year_high) / year_high 
            
            data = {
                "Symbol": symbol,
                "Price": round(current_price, 2),
                "MarketCap_Cr": round(market_cap_cr, 0),
                "Promoter_Hol%": round(promoter_holding * 100, 2),
                "Sales_Growth%": round(sales_growth * 100, 2),
                "Profit_Margin%": round(profit_margin * 100, 2),
                "PEG": peg_ratio,
                "Pct_From_High": round(pct_from_high * 100, 2)
            }
            
            return self.score_candidate(data)

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return None

    def score_candidate(self, data: dict) -> Optional[dict]:
        """Apply SpringPad Framework Logic."""
        # 1. Microcap Filter
        is_microcap = settings.MIN_MARKET_CAP_CR <= data["MarketCap_Cr"] <= settings.MAX_MARKET_CAP_CR
        
        if not is_microcap:
            return None
            
        final_score = 0
        # 2. Skin in the Game
        if data["Promoter_Hol%"] > settings.MIN_PROMOTER_HOLDING: final_score += 1
        # 3. Growth
        if data["Sales_Growth%"] > settings.MIN_SALES_GROWTH: final_score += 1
        if data["Sales_Growth%"] > 20: final_score += 1 
        # 4. Quality
        if data["Profit_Margin%"] > 12: final_score += 1 
        # 5. Technical
        if data["Pct_From_High"] > -20: final_score += 1 
        
        cmp = data["Price"]
        data["Buy_Zone"] = f"{round(cmp * 0.98, 1)} - {cmp}"
        data["Stop_Loss"] = round(cmp * 0.92, 1) 
        data["Target_1"] = round(cmp * 1.20, 1) 
        data["Target_2"] = round(cmp * 1.40, 1) 
        
        data["Score"] = final_score
        return data

    async def run_screener(self):
        """Run the screener across all tickers."""
        logger.info(f"Starting Microcap Screener for {len(TICKERS)} stocks...")
        
        tasks = [self.analyze_stock(symbol) for symbol in TICKERS]
        results = await asyncio.gather(*tasks)
        
        # Filter None and keep valid results
        valid_results = [r for r in results if r is not None]
        
        df = pd.DataFrame(valid_results)
        if df.empty:
            logger.info("No stocks found matching criteria.")
            return []
            
        # Filter score >= 4
        candidates = df[df["Score"] >= 4].sort_values(by="Score", ascending=False)
        
        # Save to DB
        db_manager.save_dataframe(candidates, "microcaps")
        return candidates.to_dict(orient="records")

screener_service = ScreenerService()
