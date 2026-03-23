import numpy as np
import pandas as pd

def calculate_recovery_metrics(cumulative_returns):
    """
    Phase 37: Drawdown Recovery Metrics.
    Calculates the 'Pain Period' - how long the portfolio spends underwater.
    
    Args:
        cumulative_returns (pd.Series): Series of cumulative returns (values >= 1.0).
        
    Returns:
        max_duration_days (int): Longest time between High Water Marks.
        avg_recovery_days (float): Average time to recover.
        ulcer_index (float): Measure of downside volatility.
    """
    high_water_mark = cumulative_returns.cummax()
    drawdown = cumulative_returns / high_water_mark - 1
    
    # 1. Ulcer Index (Root Mean Squared Drawdown)
    ulcer_index = np.sqrt(np.mean(drawdown ** 2)) * 100
    
    # 2. Recovery Duration
    # Find periods where drawdown < 0
    underwater = drawdown < 0
    
    # Identify streaks of True
    # We can use comparison with shifted version to find start/end
    # Or just iterate (simpler for now since Series length < 2000 usually)
    
    max_duration = 0
    current_duration = 0
    total_duration = 0
    count = 0
    
    for x in underwater:
        if x: # Is underwater
            current_duration += 1
        else:
            if current_duration > 0:
                max_duration = max(max_duration, current_duration)
                total_duration += current_duration
                count += 1
                current_duration = 0
                
    # Check if currently underwater (streak continues to end)
    if current_duration > 0:
         max_duration = max(max_duration, current_duration)
         total_duration += current_duration
         count += 1
         
    # Convert Trading Days to Calendar Days approx (x 1.4) or keep Trading Days
    # We'll use Trading Days.
    
    avg_duration = (total_duration / count) if count > 0 else 0
    
    return max_duration, avg_duration, ulcer_index
