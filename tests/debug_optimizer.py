import sys
import os
import traceback

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.optimizer import PortfolioOptimizer

print("[DEBUG] importing PortfolioOptimizer")

try:
    optimizer = PortfolioOptimizer()
    print("[DEBUG] Optimizer instantiated")
    
    stocks = [
         {'Symbol': 'A', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0},
         {'Symbol': 'B', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0},
         {'Symbol': 'C', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0},
         {'Symbol': 'D', 'Sector': 'Tech', 'Price': 100, 'ATR': 2.0}
    ]
    
    optimizer.max_sector_weight = 0.2
    print("[DEBUG] Running optimize_allocation")
    
    df = optimizer.optimize_allocation(stocks)
    print("[DEBUG] Optimization done")
    print(df)
    
except Exception:
    traceback.print_exc()
