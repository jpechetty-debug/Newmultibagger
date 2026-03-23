import asyncio

import numpy as np
import pandas as pd
import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff


def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(data, slow=26, fast=12, signal=9):
    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line
    return macd, signal_line, hist


def calculate_bollinger_bands(data, window=20, num_std=2):
    rolling_mean = data.rolling(window=window).mean()
    rolling_std = data.rolling(window=window).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return upper_band, rolling_mean, lower_band


def calculate_atr(high, low, close, window=14):
    tr1 = pd.DataFrame(high - low)
    tr2 = pd.DataFrame(abs(high - close.shift(1)))
    tr3 = pd.DataFrame(abs(low - close.shift(1)))
    frames = [tr1, tr2, tr3]
    tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
    atr = tr.rolling(window).mean()
    return atr


async def get_technical_analysis(symbol):
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"

        ticker = yf.Ticker(symbol)
        df = await run_with_exponential_backoff(
            lambda: asyncio.to_thread(lambda: ticker.history(period="6mo")),
            context=f"yfinance technicals for {symbol}",
        )

        if df.empty or len(df) < 30:
            return {"error": "Insufficient historical data"}

        close = df["Close"]

        # RSI
        rsi_series = calculate_rsi(close)
        current_rsi = float(rsi_series.iloc[-1])

        # Moving averages
        sma_20 = float(close.rolling(window=20).mean().iloc[-1])
        sma_50 = float(close.rolling(window=50).mean().iloc[-1])
        sma_200 = (
            float(close.rolling(window=200).mean().iloc[-1]) if len(df) >= 200 else sma_50
        )
        current_price = float(close.iloc[-1])

        trend = "Neutral"
        if current_price > sma_50 > sma_200:
            trend = "Strong Bullish"
        elif current_price > sma_50:
            trend = "Bullish"
        elif current_price < sma_50 < sma_200:
            trend = "Strong Bearish"
        elif current_price < sma_50:
            trend = "Bearish"

        strength_score = 50
        if current_price > sma_50:
            strength_score += 15
        if current_price > sma_200:
            strength_score += 15
        if 40 < current_rsi < 70:
            strength_score += 20
        elif current_rsi > 70:
            strength_score += 10
        elif current_rsi < 30:
            strength_score -= 10

        def sanitize_val(value):
            try:
                parsed = float(value)
                if not np.isfinite(parsed):
                    return 0.0
                return parsed
            except Exception:
                return 0.0

        return {
            "symbol": symbol,
            "current_price": round(sanitize_val(current_price), 2),
            "rsi": round(sanitize_val(current_rsi), 2),
            "sma_50": round(sanitize_val(sma_50), 2),
            "sma_200": round(sanitize_val(sma_200), 2),
            "trend": trend,
            "strength_score": min(100, int(sanitize_val(strength_score))),
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_sma_200(close):
    try:
        return float(close.rolling(window=200).mean().iloc[-1])
    except Exception:
        return None


def calculate_momentum_features(df):
    """
    Calculates momentum and volume breakout features for ML ranking.
    """
    try:
        close = df["Close"]
        volume = df["Volume"]
        
        # 1. Price Momentum
        ret_1m = (close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else 0
        ret_3m = (close.iloc[-1] / close.iloc[-63] - 1) if len(close) > 63 else 0
        ret_6m = (close.iloc[-1] / close.iloc[-126] - 1) if len(close) > 126 else 0
        
        # 2. Volume Breakout
        avg_vol_20d = volume.rolling(window=20).mean().iloc[-1]
        current_vol = volume.iloc[-1]
        vol_ratio = (current_vol / avg_vol_20d) if avg_vol_20d > 0 else 1.0
        
        # 3. 52-Week High Proximity
        high_52w = close.rolling(window=252).max().iloc[-1] if len(close) >= 252 else close.max()
        dist_from_high = (high_52w - close.iloc[-1]) / high_52w if high_52w > 0 else 0
        
        return {
            "ret_1m": round(ret_1m, 4),
            "ret_3m": round(ret_3m, 4),
            "ret_6m": round(ret_6m, 4),
            "vol_breakout": round(vol_ratio, 2),
            "dist_from_52w_high": round(dist_from_high, 4)
        }
    except Exception:
        return {}
