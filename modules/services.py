"""
Sovereign AI Trading Engine - Core Services Logic
Decomposes the god-file screener.py into manageable services.
"""

from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod
from modules.models import StockDataPayload, ScoringResult
import pandas as pd
import asyncio

class BaseService(ABC):
    """Base abstract class for core sovereign services."""
    def __init__(self, logger=None):
        from modules.structured_logger import logger as default_logger
        self.logger = logger or default_logger

class IngestionService(BaseService):
    """Handles raw data fetching, cleaning, and Pydantic validation."""
    
    def __init__(self, logger=None):
        super().__init__(logger)
        from modules.data_manager import data_manager
        self.data_manager = data_manager

    async def fetch_single_stock(self, symbol: str) -> Optional[StockDataPayload]:
        """Fetch and validate data for a single symbol using the fallback chain."""
        try:
            # 1. Fetch raw fundamental data via DataManager (PNSEA -> NSEPython -> yf)
            raw = await self.data_manager.async_fetch_fundamentals(symbol)
            if not raw or "error" in raw:
                self.logger.warning(f"Fetch failed for {symbol}", symbol=symbol, source=raw.get("source", "none"))
                return None

            # 2. Fetch technical history
            hist = await self.data_manager.fetch_history(symbol, period="1y")
            if hist.empty:
                self.logger.warning(f"No price history for {symbol}", symbol=symbol)
                return None

            # 3. Construct Payload (Normalized for Pydantic)
            raw_info = raw.get("info", {})
            payload_data = {
                "Symbol": symbol,
                "Price": hist['Close'].iloc[-1],
                "Data_Source": raw.get("source", "unknown"),
                "History_Bars_1Y": len(hist),
                "Sector": raw_info.get("sector", "Unknown"),
                "Industry": raw_info.get("industry", "Unknown"),
                "Market_Cap_Cr": raw_info.get("marketCap", 0) / 10000000,
                "PE_Ratio": raw_info.get("trailingPE", 0),
                "ROE%": raw_info.get("returnOnEquity", 0) * 100 if raw_info.get("returnOnEquity") else 0,
                "Debt_Equity": raw_info.get("debtToEquity", 0),
                "Sales_Growth_TTM%": raw_info.get("revenueGrowth", 0) * 100 if raw_info.get("revenueGrowth") else 0,
                # ... add other fields as needed for the 8-factor model
            }

            # 4. Strict Validation
            return StockDataPayload(**payload_data)

        except Exception as e:
            self.logger.error(f"Ingestion error for {symbol}", symbol=symbol, error=str(e))
            return None

    async def fetch_universe_data(self, symbols: List[str]) -> List[StockDataPayload]:
        """Fetch and validate data for a list of symbols with tiered concurrency."""
        tasks = [self.fetch_single_stock(s) for s in symbols]
        results = await asyncio.gather(*tasks)
        return [res for res in results if res is not None]


class ScoringService(BaseService):
    """Handles factor normalization, regime-aware scoring, and audit trails."""
    
    def calculate_single_score(self, payload: StockDataPayload, market_regime: str = "Balanced") -> ScoringResult:
        """Calculate a single institutional score using the 8-factor model."""
        from modules.scoring import calculate_institutional_score
        
        # 1. Adapt Pydantic payload to dict for current scoring engine
        data_dict = payload.model_dump(by_alias=True)
        
        # 2. Extract score
        raw_result = calculate_institutional_score(data_dict, market_regime=market_regime)
        
        # 3. Map to ScoringResult Pydantic model
        return ScoringResult(**raw_result)

    async def calculate_universe_scores(self, data_payloads: List[StockDataPayload], market_regime: str = "Balanced") -> List[ScoringResult]:
        """Calculate scores for an entire universe of stocks."""
        self.logger.info(f"Calculating scores for {len(data_payloads)} payloads")
        return [self.calculate_single_score(p, market_regime) for p in data_payloads]


class DataStoreService(BaseService):
    """Handles tiered caching and persistence (Sqlite, Memory)."""
    
    def __init__(self, logger=None):
        super().__init__(logger)
        from modules.data_manager import PersistentCache
        self._memory_cache = {}
        self._db_cache = PersistentCache(db_path="data_cache.db")
        
    async def get_cached_fundamental(self, symbol: str) -> Optional[StockDataPayload]:
        """Tier 1: Memory -> Tier 2: data_cache.db -> Tier 3: None"""
        import time
        # 1. Tier 1 (Memory)
        if symbol in self._memory_cache:
            entry = self._memory_cache[symbol]
            if time.time() < entry["expires"]:
                return entry["data"]
        
        # 2. Tier 2 (Sqlite)
        cached = self._db_cache.get(f"fund_{symbol}")
        if cached:
            try:
                # The cached blob might be a dict from DataManager.
                # We normalize it to StockDataPayload.
                if "info" in cached:
                    # Logic similar to IngestionService normalization
                    pass 
                
                payload = StockDataPayload(**cached)
                # Side-load into memory
                self._memory_cache[symbol] = {"data": payload, "expires": time.time() + 300} # 5 min mem TTL
                return payload
            except Exception:
                return None
                
        return None

    async def update_cache(self, symbol: str, data: StockDataPayload, ttl: int = 3600):
        """Update both memory and persistent cache."""
        import time
        # Update Memory
        self._memory_cache[symbol] = {"data": data, "expires": time.time() + 300}
        # Update Persistence
        self._db_cache.set(f"fund_{symbol}", data.model_dump())


class TaskQueueCoordinator(BaseService):
    """Orchestrates large-scale universe scans using Ingestion and Scoring services."""
    
    def __init__(self, logger=None):
        super().__init__(logger)
        self.ingestion = IngestionService(logger)
        self.scoring = ScoringService(logger)
        self.storage = DataStoreService(logger)
        self._queue = asyncio.Queue()
        self._results = []

    async def run_universe_scan(self, symbols: List[str], market_regime: str = "Balanced"):
        """Run a full universe scan with background task orchestration."""
        self._results = []
        self.logger.info(f"Starting coordinated scan for {len(symbols)} symbols", regime=market_regime)
        
        # 1. Batch symbols to avoid queue overload
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            
            # 2. Ingest batch (Concurrent via asyncio.gather inside IngestionService)
            payloads = await self.ingestion.fetch_universe_data(batch)
            
            # 3. Score batch (CPU bound, but small enough for sync list comp)
            scores = await self.scoring.calculate_universe_scores(payloads, market_regime)
            
            # 4. Store results & update cache
            for p, s in zip(payloads, scores):
                await self.storage.update_cache(p.Symbol, p)
                self._results.append({"symbol": p.Symbol, "score": s.total_score, "payload": p, "result": s})

        self.logger.info(f"Scan complete. Found {len(self._results)} valid results.")
        return self._results


class MLOpsService(BaseService):
    """Handles automated ML model retraining, monitoring, and batch prediction updates."""
    
    def __init__(self, logger=None):
        super().__init__(logger)
        from modules.ml_ops import initialize_ml_metadata
        initialize_ml_metadata()

    def check_and_retrain(self, force: bool = False):
        """Monitor data growth and trigger retraining if thresholds are met."""
        from modules.ml_ops import check_retraining_trigger, run_automated_training
        
        should_retrain = force or check_retraining_trigger()
        if should_retrain:
            self.logger.info("ML Ops: Retraining trigger activated.")
            success = run_automated_training()
            return success
        else:
            self.logger.info("ML Ops: No retraining needed (record count threshold not met).")
            return False

    async def update_all_predictions(self):
        """Batch update all stock predictions with the current model."""
        from modules.ml_ops import batch_update_multibaggers_ml
        await batch_update_multibaggers_ml()


class ReporterService(BaseService):
    """Generates professional PDF/HTML reports for investors."""
    
    def generate_investor_report(self, portfolio_data: list, output_path: str):
        """Generate a summary report of the top picks."""
        from modules.html_report import generate_audit_report
        # Reuse existing report logic but tailored for investors
        # For now, we'll just trigger the audit report logic as a proxy
        self.logger.info(f"Generating investor report to {output_path}")
        # In a real implementation, this would use a specific template
        pass
