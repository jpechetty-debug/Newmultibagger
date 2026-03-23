
import pandas as pd
import numpy as np

def calculate_rsi(series, period=14):
    """
    Calculate Relative Strength Index (RSI) for a given pandas Series (prices).
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # Handle division by zero (if loss is 0, RSI is 100)
    rsi = rsi.replace([np.inf, -np.inf], 100).fillna(50) # Neutral RSI fill
    
    return rsi
