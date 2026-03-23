import yfinance as yf
import pandas as pd
import numpy as np
from modules.recovery import calculate_recovery_metrics
from modules.tax_efficiency import calculate_tax_efficiency

def run_performance_analysis(tickers, weights=None, benchmark_symbol="^NSEI", period="1y", start_date=None, end_date=None):
    """
    Phase 16/17/31: Backtest Engine with Walk-Forward Capability.
    
    Args:
        tickers: List of symbols
        weights: Dict {symbol: weight}
        period: "1y", "2y" etc (used if dates not provided)
        start_date: "YYYY-MM-DD" (Optional - overrides period)
        end_date: "YYYY-MM-DD" (Optional - overrides period)
    """
    if weights:
        print(f"\nrunning Phase 17/31: Weighted Portfolio Backtest...")
    else:
        print(f"\nrunning Phase 16/31: Equal-Weight Backtest...")
    
    if not tickers:
        print("No tickers to backtest.")
        return
        
    try:
        # Fetch Data
        all_symbols = tickers + [benchmark_symbol]
        
        if start_date and end_date:
            print(f"  📅 Range: {start_date} to {end_date}")
            data = yf.download(all_symbols, start=start_date, end=end_date, progress=False)['Close']
        else:
            print(f"  📅 Period: {period}")
            data = yf.download(all_symbols, period=period, progress=False)['Close']
        
        if data.empty:
            print("Failed to download backtest data.")
            return

        # Calculate Daily Returns
        returns = data.pct_change().dropna()
        
        # 1. Strategy Return
        # Filter only valid columns that are in our ticker list
        valid_tickers = [t for t in tickers if t in data.columns]
        if not valid_tickers:
            print("No valid data for selected tickers.")
            return
            
        if weights:
            # Normalize weights to sum to 1 just in case
            w_sum = sum(weights.get(t, 0) for t in valid_tickers)
            if w_sum == 0:
                print("Invalid weights.")
                strategy_returns = returns[valid_tickers].mean(axis=1) # Fallback
            else:
                # Calculate weighted returns
                # returns is a DataFrame, multiply each column by its weight
                weighted_rets = pd.DataFrame()
                for t in valid_tickers:
                    w = weights.get(t, 0) / w_sum
                    weighted_rets[t] = returns[t] * w
                strategy_returns = weighted_rets.sum(axis=1)
                
                print("Applied Smart Sizing (Score-Based Weights).")
        else:
            strategy_returns = returns[valid_tickers].mean(axis=1)
        
        # 2. Benchmark Return
        if benchmark_symbol in returns.columns:
            benchmark_returns = returns[benchmark_symbol]
        else:
            # Fallback if benchmark failed
            benchmark_returns = pd.Series(0, index=returns.index)
            
        # 3. Cumulative Returns
        cum_strategy = (1 + strategy_returns).cumprod()
        cum_benchmark = (1 + benchmark_returns).cumprod()
        
        # 4. Metrics
        # Total Return
        total_strategy_ret = (cum_strategy.iloc[-1] - 1) * 100
        total_benchmark_ret = (cum_benchmark.iloc[-1] - 1) * 100
        
        # CAGR (Approximate for 1y period, equals Total Return)
        # For general case: (End/Start)^(1/years) - 1
        days = len(data)
        years = days / 252.0
        cagr_strategy = ((cum_strategy.iloc[-1]) ** (1/years) - 1) * 100
        cagr_benchmark = ((cum_benchmark.iloc[-1]) ** (1/years) - 1) * 100
        
        # Max Drawdown
        rolling_max = cum_strategy.cummax()
        drawdown = cum_strategy / rolling_max - 1
        max_dd = drawdown.min() * 100
        
        # Sharpe Ratio (Risk Free Rate = 6%)
        rf_daily = 0.06 / 252
        excess_returns = strategy_returns - rf_daily
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
        
        # Alpha
        alpha = cagr_strategy - cagr_benchmark
        
        # Phase 33: Real-World Slippage Modeling
        # Assume average slippage for the portfolio type
        # Ideally we calculate per stock, but for aggregate backtest:
        # Large Cap Portfolio: 0.5%, Mid: 1.0%, Small: 2.0%
        # We will estimate conservatively at 1.0% one-way (2% round trip drag)
        
        slippage_one_way = 1.0 
        round_trip_drag = slippage_one_way * 2
        net_cagr = cagr_strategy - round_trip_drag
        net_alpha = net_cagr - cagr_benchmark
        
        net_alpha = net_cagr - cagr_benchmark
        
        # Phase 37: Recovery Metrics
        rec_days, avg_rec, ulcer = calculate_recovery_metrics(cum_strategy)
        
        # Phase 38: Tax Efficiency Layer
        # We need strategy_type. We'll default to 'Balanced' if not passed, 
        # but ideally we should update the function signature. 
        # For now, let's infer or assume Balanced for standard backtest.
        post_tax_cagr, tax_drag, turnover, eff_tax = calculate_tax_efficiency(net_cagr, strategy_type="Balanced (Neutral)")
        
        # Output Report
        print("\n" + "="*40)
        print(f"📊 PHASE 16/33/37/38: BACKTEST REPORT")
        print("="*40)
        print(f"Strategy: {len(valid_tickers)} Stocks")
        print(f"Benchmark: {benchmark_symbol}")
        print("-" * 55)
        print(f"{'Metric':<15} | {'Gross':<8} | {'Net':<8} | {'Post-Tax':<8}")
        print("-" * 55)
        print(f"{'CAGR':<15} | {cagr_strategy:>7.1f}% | {net_cagr:>7.1f}% | {post_tax_cagr:>7.1f}%")
        print(f"{'Drawdown':<15} | {max_dd:>7.1f}% | {max_dd:>7.1f}% | {max_dd:>7.1f}%")
        print(f"{'Sharpe':<15} | {sharpe:>7.2f}  | {sharpe:>7.2f}  | {'--':>7}")
        print("-" * 55)
        print(f"Turnover Est : {turnover:>4.1f}x/yr  | Tax Rate: {eff_tax:.1f}%")
        print(f"Recovery Days: {rec_days:>4}d      | Ulcer Idx: {ulcer:.2f}")
        print("-" * 55)
        
        if alpha > 0:
            print(f"✅ GROSS ALPHA: +{alpha:.1f}%")
        else:
            print(f"❌ GROSS ALPHA: {alpha:.1f}%")
            
        if post_tax_cagr > cagr_benchmark:
             print(f"🏆 REAL ALPHA : +{post_tax_cagr - cagr_benchmark:.1f}% (Post-Tax)")
        else:
             print(f"💸 TAX TRAP   :Strategy loses edge after Tax/Slippage")

        print("="*40 + "\n")
        
        return {
            "CAGR": cagr_strategy,
            "NetCAGR": net_cagr,
            "MaxDD": max_dd,
            "Sharpe": sharpe,
            "Alpha": alpha,
            "NetAlpha": net_alpha
        }
        
    except Exception as e:
        print(f"Backtest Error: {e}")
