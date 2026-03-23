import numpy as np
import pandas as pd
import yfinance as yf
from hmmlearn.hmm import GaussianHMM
from datetime import datetime, timedelta
import joblib
import os

MODEL_PATH = "market_regime_hmm.pkl"

class RegimeHMM:
    """
    Identifies market regimes (Bullish, Bearish, Volatile) using a Hidden Markov Model.
    """
    def __init__(self, model_path=MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self._load_model()
        
    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
            except Exception as e:
                print(f"Error loading HMM model: {e}")

    def fetch_index_data(self, ticker="^NSEI", years=5):
        """Fetches historical returns for an index."""
        start = (datetime.now() - timedelta(days=years*365)).strftime("%Y-%m-%d")
        data = yf.download(ticker, start=start, progress=False)
        if data.empty:
            return pd.Series()
        
        # Calculate daily log returns
        if isinstance(data.columns, pd.MultiIndex):
            close = data[('Close', ticker)]
        else:
            close = data['Close']
            
        returns = np.log(close / close.shift(1)).dropna()
        return returns

    def train(self, ticker="^NSEI", n_components=3):
        """Trains the Gaussian HMM on index returns."""
        returns = self.fetch_index_data(ticker)
        if len(returns) < 500:
            print("Insufficient data for HMM training.")
            return False
        
        # Reshape for hmmlearn
        X = returns.values.reshape(-1, 1)
        
        print(f"Training HMM with {n_components} states on {ticker}...")
        self.model = GaussianHMM(
            n_components=n_components, 
            covariance_type="full", 
            n_iter=1000,
            random_state=42
        )
        self.model.fit(X)
        
        # Save model
        joblib.dump(self.model, self.model_path)
        print(f"HMM Model saved to {self.model_path}")
        return True

    def predict_regime(self, ticker="^NSEI"):
        """
        Predicts the current regime for the index.
        Returns: String (BULLISH, BEARISH, VOLATILE)
        """
        if not self.model:
            # Try to train if model missing
            if not self.train(ticker):
                return "SIDEWAYS" # Default fallback
        
        # Fetch last 30 days to get current state
        start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        data = yf.download(ticker, start=start, progress=False)
        if data.empty:
            return "SIDEWAYS"
            
        if isinstance(data.columns, pd.MultiIndex):
            close = data[('Close', ticker)]
        else:
            close = data['Close']
            
        returns = np.log(close / close.shift(1)).dropna()
        X = returns.values.reshape(-1, 1)
        
        # Predict hidden states for the sequence
        hidden_states = self.model.predict(X)
        current_state = hidden_states[-1]
        
        # Map hidden states to human labels
        # We identify states by their mean (return) and variance (volatility)
        return self._map_state_to_regime(current_state)

    def _map_state_to_regime(self, state_idx):
        """
        Maps a hidden state index to a regime label.
        Regimes: 
        - Bullish: High mean, Low variance
        - Bearish: Low (negative) mean, High variance
        - Volatile/Sideways: Near-zero mean, High variance
        """
        means = self.model.means_.flatten()
        covars = self.model.covars_.flatten()
        
        state_mean = means[state_idx]
        state_var = covars[state_idx]
        
        # Sorting states by mean to identify Bull/Bear
        sorted_indices = np.argsort(means)
        
        if state_idx == sorted_indices[-1]:
            return "BULLISH"
        elif state_idx == sorted_indices[0]:
            return "BEARISH"
        else:
            return "VOLATILE"

if __name__ == "__main__":
    hmm = RegimeHMM()
    regime = hmm.predict_regime()
    print(f"Current Market Regime (HMM): {regime}")
