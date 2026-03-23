import vectorbt as vbt
import yfinance as yf
import pandas as pd
import numpy as np

class VectorBTEngine:
    def __init__(self, period="5y"):
        self.period = period

    @staticmethod
    def _sanitize_metric(value, default=0.0):
        """Convert metric to finite float with fallback."""
        try:
            val = float(value)
        except (TypeError, ValueError):
            return float(default)
        if np.isnan(val) or np.isinf(val):
            return float(default)
        return float(val)

    @staticmethod
    def _metric_for_symbol(metric, symbol):
        """Handle scalar/Series outputs consistently."""
        if isinstance(metric, pd.Series):
            return metric.get(symbol, np.nan)
        return metric
        
    def run_momentum_backtest(self, symbol: str) -> dict:
        """ Legacy single symbol run """
        result = self.run_batch_momentum_backtest([symbol])
        if symbol in result:
            return result[symbol]
        sym_ns = symbol if symbol.endswith(".NS") or symbol.endswith(".BO") else symbol + ".NS"
        return result.get(sym_ns, {
            "symbol": symbol, "cagr": 0.0, "win_rate": 0.0, 
            "max_drawdown": 0.0, "sharpe_ratio": 0.0, "status": "ERROR"
        })
        
    def run_batch_momentum_backtest(self, symbols: list) -> dict:
        """
        Runs a fully vectorized backtest on a batch of symbols simultaneously 
        using a Fast/Slow SMA crossover strategy to avoid yfinance rate limits.
        Returns a dictionary mapping symbols to their backtest results.
        """
        try:
            # Parse symbols
            clean_symbols = []
            for s in symbols:
                if not isinstance(s, str) or not s.strip():
                    continue
                if not s.endswith('.NS') and not s.endswith('.BO'):
                    clean_symbols.append(s + '.NS')
                else:
                    clean_symbols.append(s)

            if not clean_symbols:
                return {}

            # Fetch historical data in one giant batch
            print(f"[VectorBT] Downloading data for {len(clean_symbols)} tickers...")
            df = yf.download(clean_symbols, period=self.period, interval="1d", progress=False, group_by='ticker')
            
            if df.empty:
                return {s: {"symbol": s, "status": "NO_DATA"} for s in clean_symbols}

            results = {}
            
            # Helper to extract Close price series safely depending on yfinance structure
            def get_close_series(sym):
                if isinstance(df.columns, pd.MultiIndex):
                    if (sym, "Close") in df.columns:
                        return df[(sym, "Close")]
                    if ("Close", sym) in df.columns:
                        return df[("Close", sym)]
                    if sym in df and isinstance(df[sym], pd.DataFrame) and "Close" in df[sym]:
                        return df[sym]["Close"]
                elif 'Close' in df:
                    return df['Close']
                return pd.Series(dtype=float)

            close_prices = {}
            for sym in clean_symbols:
                s_close = get_close_series(sym).dropna()
                if not s_close.empty and len(s_close) >= 200:
                    close_prices[sym] = s_close
                else:
                    results[sym] = {
                        "symbol": sym, "cagr": 0.0, "win_rate": 0.0, 
                        "max_drawdown": 0.0, "sharpe_ratio": 0.0, "status": "INSUFFICIENT_DATA"
                    }

            if not close_prices:
                return results

            # Create Price Matrix
            price_matrix = pd.DataFrame(close_prices).sort_index()
            
            # Use pandas rolling MAs to keep a flat symbol-indexed matrix.
            fast_ma = price_matrix.rolling(window=50, min_periods=50).mean()
            slow_ma = price_matrix.rolling(window=200, min_periods=200).mean()

            entries = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
            exits = (fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))

            portfolio = vbt.Portfolio.from_signals(
                price_matrix,
                entries,
                exits,
                init_cash=100000,
                fees=0.001,
                freq='1D'
            )

            ann_return = portfolio.annualized_return() * 100
            win_rate = portfolio.trades.win_rate() * 100
            max_dd = portfolio.max_drawdown() * 100
            sharpe = portfolio.sharpe_ratio()

            for sym in price_matrix.columns:
                try:
                    cagr_val = self._sanitize_metric(self._metric_for_symbol(ann_return, sym), 0.0)
                    win_rate_val = self._sanitize_metric(self._metric_for_symbol(win_rate, sym), 0.0)
                    max_dd_val = self._sanitize_metric(self._metric_for_symbol(max_dd, sym), 0.0)
                    sharpe_val = self._sanitize_metric(self._metric_for_symbol(sharpe, sym), 0.0)
                    
                    results[sym] = {
                        "symbol": sym,
                        "cagr": round(cagr_val, 2),
                        "win_rate": round(win_rate_val, 2),
                        "max_drawdown": round(max_dd_val, 2),
                        "sharpe_ratio": round(sharpe_val, 2),
                        "status": "OK"
                    }
                except Exception as inner_e:
                    results[sym] = {
                        "symbol": sym, "cagr": 0.0, "win_rate": 0.0, 
                        "max_drawdown": 0.0, "sharpe_ratio": 0.0, "status": f"ERROR: {inner_e}"
                    }

            return results
            
        except Exception as e:
            print(f"[VectorBT] Batch Backtest failed: {e}")
            return {s: {"symbol": s, "status": f"BATCH_ERROR: {str(e)}"} for s in symbols}

if __name__ == "__main__":
    engine = VectorBTEngine(period="5y")
    res = engine.run_batch_momentum_backtest(["SAKSOFT.NS", "TCS.NS"])
    print("\n--- VectorBT Optimization Results ---")
    for sym, r in res.items():
        print(f"{sym}: {r.get('cagr')}% CAGR | {r.get('win_rate')}% Win | Status: {r.get('status')}")
