
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.fundamental_filters import validate_garp_criteria

mock_data = {
    "Symbol": "TCS.NS",
    "Price": 3500,
    "Sector": "IT Services",
    "Score": 90,
    "Sales_Growth_5Y%": 20, 
    "Sales_Growth_TTM%": 18,
    "Avg_ROE_5Y%": 30,
    "ROE%": 35,
    "PEG_Ratio": 1.5,
    "Debt_Equity": 0.0,
    "Promoter_Holding%": 72,
    "Inst_Holding%": 20,
    "conviction_score": 80,
    "rs_rating": 2.0
}

try:
    print(f"Testing filter with: {mock_data}")
    result = validate_garp_criteria(mock_data)
    print(f"Result: {result}")
except Exception as e:
    print(f"CRASH: {e}")
    import traceback
    traceback.print_exc()
