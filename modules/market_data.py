import yfinance as yf
import pandas as pd
import datetime
import logging
from modules.regime_hmm import RegimeHMM

logger = logging.getLogger(__name__)

class MarketDataProvider:
    """
    Fetches market data for macro-risk analysis.
    """
    
    def __init__(self):
        self.vix_ticker = "^INDIAVIX" # or "^VIX" if US, but assuming India based on context
        
    def get_vix_threshold(self, lookback_days=365, percentile=0.75):
        """
        Fetches historical VIX and calculates the dynamic high-stress threshold.
        
        Args:
            lookback_days (int): History to analyze (default 1 year).
            percentile (float): Percentile defining 'High Stress' (default 75th).
            
        Returns:
            float: The VIX threshold (e.g., 18.5).
        """
        try:
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=lookback_days + 10) # Buffer
            
            # Fetch Data
            # Note: yfinance might fail on some corporate firewalls or if ticker invalid.
            # We add a fallback just in case.
            data = yf.download(self.vix_ticker, start=start_date, end=end_date, progress=False)
            
            if data.empty:
                print(f"⚠️ Warning: Could not fetch VIX data for {self.vix_ticker}. Using Fallback.")
                return 30.0 # Standard fallback
                
            # Calculate Percentile
            # 'Close' column might be multi-level if yf download structure changes, ensuring robust access.
            if isinstance(data.columns, pd.MultiIndex):
                vix_series = data[('Close', self.vix_ticker)]
            else:
                vix_series = data['Close']
                
            threshold = vix_series.quantile(percentile)
            current_vix = vix_series.iloc[-1]
            
            print(f"📊 Market Regime: VIX 75th Percentile = {threshold:.2f} (Current: {current_vix:.2f})")
            return float(threshold), float(current_vix)
            
        except Exception as e:
            logger.warning("Market data: VIX fetch failed: %s", e)
            return 30.0, 0.0

    def get_market_breadth(self):
        """
        Calculates Market Breadth using Nifty 50 constituents.
        Proxy: Ratio of stocks trading above their 50-day SMA.
        Returns:
            float: Breadth Ratio (0.0 to 1.0)
            int: Count of stocks > SMA50
        """
        # Representative Nifty 50 List (Top Weights)
        nifty_50_tickers = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", 
            "BHARTIARTL.NS", "ITC.NS", "SBIN.NS", "LICI.NS", "HINDUNILVR.NS",
            "LT.NS", "BAJFINANCE.NS", "MARUTI.NS", "HCLTECH.NS", "SUNPHARMA.NS",
            "TATAMOTORS.NS", "ULTRACEMCO.NS", "AXISBANK.NS", "NTPC.NS", "TITAN.NS",
            "ADANIENT.NS", "ONGC.NS", "KOTAKBANK.NS", "POWERGRID.NS", "WIPRO.NS",
            "M&M.NS", "BAJAJFINSV.NS", "COALINDIA.NS", "ASIANPAINT.NS", "JSWSTEEL.NS"
        ] # Top 30 is sufficient proxy
        
        try:
            print("📊 Checking Market Breadth (Nifty 30 Proxy)...")
            data = self.get_batch_history(nifty_50_tickers, period="3mo")
            if data.empty:
                return 0.5, 15 # Neutral fallback
            
            above_sma = 0
            valid_tickers = 0
            
            # Calculate SMA50 for each
            for ticker in data.columns:
                series = data[ticker].dropna()
                if len(series) > 50:
                    sma50 = series.rolling(window=50).mean().iloc[-1]
                    current = series.iloc[-1]
                    if current > sma50:
                        above_sma += 1
                    valid_tickers += 1
            
            if valid_tickers == 0:
                return 0.5, 0
                
            ratio = above_sma / valid_tickers
            print(f"   👉 Breadth: {above_sma}/{valid_tickers} ({ratio:.1%}) stocks > SMA50")
            return ratio, above_sma
            
        except Exception as e:
            logger.warning("Market data: breadth calculation failed: %s", e)
            return 0.5, 0

    def get_market_regime(self, index_ticker="^NSEI"):
        """
        Determines Market Regime using high-fidelity 3-Factor Voting.
        
        Factors:
        1. Trend: Nifty 50 vs 200DMA
        2. Volatility: VIX Percentile
        3. Breadth: Stocks > SMA50
        
        Returns: Dict with regime details.
        """

        votes = {'BULL': 0, 'BEAR': 0, 'SIDEWAYS': 0}
        details = {}
        
        try:
            # --- FACTOR 1: TREND (Nifty 50 vs 200DMA) ---
            data = yf.download(index_ticker, period="1y", progress=False)
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    prices = data[('Close', index_ticker)]
                else:
                    prices = data['Close']
                
                current_price = prices.iloc[-1]
                dma200 = prices.rolling(window=200).mean().iloc[-1]
                
                offset = (current_price - dma200) / dma200
                details['trend_offset'] = offset
                
                if offset > 0.02:
                    votes['BULL'] += 1
                    details['trend_vote'] = 'BULL'
                elif offset < -0.02:
                    votes['BEAR'] += 1
                    details['trend_vote'] = 'BEAR'
                else:
                    votes['SIDEWAYS'] += 1
                    details['trend_vote'] = 'SIDEWAYS'
            
            # --- FACTOR 2: VOLATILITY (VIX Percentile) ---
            vix_threshold, current_vix = self.get_vix_threshold(lookback_days=90)
            # Standard logic: Low VIX = Bull/Sideways, High VIX = Bear/Panic
            # User specified: pct < 30 (Bull), > 70 (Bear)
            # Let's map roughly: < 13 Bull, > 18 Bear
            
            details['vix'] = current_vix
            if current_vix < 13.5: # Approx 30th percentile
                votes['BULL'] += 1
                details['vix_vote'] = 'BULL'
            elif current_vix > 18.0: # Approx 70th percentile
                votes['BEAR'] += 1
                details['vix_vote'] = 'BEAR'
            else:
                votes['SIDEWAYS'] += 1
                details['vix_vote'] = 'SIDEWAYS'

            # --- FACTOR 3: BREADTH (Nifty > SMA50) ---
            # User: > 1.5 ratio (60/40) -> Bull, < 0.67 (40/60) -> Bear
            breadth_ratio, _ = self.get_market_breadth()
            details['breadth_ratio'] = breadth_ratio
            
            if breadth_ratio > 0.60:
                votes['BULL'] += 1
                details['breadth_vote'] = 'BULL'
            elif breadth_ratio < 0.40:
                votes['BEAR'] += 1
                details['breadth_vote'] = 'BEAR'
            else:
                votes['SIDEWAYS'] += 1
                details['breadth_vote'] = 'SIDEWAYS'
            
            # --- FACTOR 4: HMM REGIME (Hidden Markov Model) ---
            try:
                hmm = RegimeHMM()
                # Use Nifty 50 for HMM
                hmm_regime = hmm.predict_regime(ticker="^NSEI")
                details['hmm_regime'] = hmm_regime
                
                if hmm_regime == "BULLISH":
                    votes['BULL'] += 1
                    details['hmm_vote'] = 'BULL'
                elif hmm_regime == "BEARISH":
                    votes['BEAR'] += 1
                    details['hmm_vote'] = 'BEAR'
                elif hmm_regime == "VOLATILE":
                    votes['SIDEWAYS'] += 1 # Volatile in HMM often maps to sideways/high-risk
                    details['hmm_vote'] = 'SIDEWAYS'
            except Exception as hmm_err:
                logger.warning("Market data: HMM factor error: %s", hmm_err)
            
            # --- CONSENSUS ---
            # Winner takes all
            winner = max(votes, key=votes.get)
            
            # --- PHASE 63: HARDENED OVERRIDES ---
            # 1. VIX Auto-Override (Panic Shield)
            # If VIX > 25, we force BEAR regardless of other factors to preserve capital.
            if current_vix > 25:
                print(f"🚨 Panic Shield: VIX {current_vix:.2f} > 25. Forcing BEAR regime.")
                winner = 'BEAR'
            
            # Strategy Mapping
            strategy_map = {
                'BULL': 'MOMENTUM',
                'BEAR': 'QUALITY',
                'SIDEWAYS': 'VALUE'
            }
            
            print(f"🗳️ Regime Votes: {votes} -> Winner: {winner}")

            
            return {
                "regime": winner,
                "strategy_suggestion": strategy_map.get(winner, "BALANCED"),
                "details": details,
                "votes": votes
            }
            
        except Exception as e:
            logger.warning("Market data: regime detection failed: %s", e)
            return {"regime": "SIDEWAYS", "strategy_suggestion": "BALANCED", "details": {}, "votes": {"BULL": 0, "BEAR": 0, "SIDEWAYS": 0}}

    def get_batch_history(self, tickers, period="6mo"):
        """
        Fetches historical closing prices for a list of tickers.
        Efficiently downloads in batch.
        
        Args:
            tickers (list): List of symbols (e.g., ['RELIANCE.NS', 'TCS.NS']).
            period (str): '1mo', '3mo', '6mo', '1y'.
            
        Returns:
            pd.DataFrame: Columns are Tickers, Index is Date. Values are Close Prices.
        """
        if not tickers:
            return pd.DataFrame()
            
        try:
            # yfinance expects space-separated string for batch
            tickers_str = " ".join(tickers)
            print(f"📥 Fetching history for {len(tickers)} stocks...")
            
            data = yf.download(tickers_str, period=period, progress=False)
            
            if data.empty:
                return pd.DataFrame()
                
            # Extract Adjusted Close or Close
            if 'Adj Close' in data:
                closes = data['Adj Close']
            elif 'Close' in data:
                closes = data['Close']
            else:
                # Fallback if structure is flat (single ticker)
                closes = data
                
            return closes
            
        except Exception as e:
            logger.warning("Market data: batch history fetch failed: %s", e)
            return pd.DataFrame()

