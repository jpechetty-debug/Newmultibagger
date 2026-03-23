import sys
from unittest.mock import MagicMock

# Mock out modules that call external APIs
sys.modules["modules.promoter_intel"] = MagicMock()
sys.modules["modules.promoter_intel"].calculate_promoter_score.return_value = {"is_disqualified": False, "score_adjustment": 0}
sys.modules["modules.estimates"] = MagicMock()
sys.modules["modules.estimates"].get_estimate_data.return_value = {"momentum": {"is_disqualified": False}}

sys.path.append('d:/Tradeidesa/Multibagger')
from modules.scoring import calculate_institutional_score
import numpy as np

def test_cliffs():
    print("Verifying Institutional Checklist Spline...")
    base_data = {
        "Symbol": "TEST.NS",
        "Market_Cap_Cr": 2000,
        "PE_Ratio": 20,
        "Avg_ROE_5Y%": 20,
        "Debt_Equity": 0.5,
        "CFO_PAT_Ratio": 1.1,
        "Down_From_52W_High%": 10,
        "Sales_Growth_5Y%": 20,
        "EPS_Growth%": 15,
        "Promoter_Holding%": 55,
        "F_Score": 7,
        "Earnings_Inflection_Score": 0,
        "Sector": "Technology",
        "Value_Gap%": 10,
        "Technical_Signal": "Neutral"
    }

    results = []
    metrics_to_fail = [
        "Market_Cap_Cr", "PE_Ratio", "Avg_ROE_5Y%", "Debt_Equity", "CFO_PAT_Ratio",
        "Down_From_52W_High%", "Sales_Growth_5Y%", "EPS_Growth%", "Promoter_Holding%",
        "F_Score", "Earnings_Inflection_Score", "Value_Gap%"
    ]

    for i in range(13):
        test_data = base_data.copy()
        # To fail i metrics
        for j in range(i):
            key = metrics_to_fail[j]
            if key == "PE_Ratio": test_data[key] = 100
            elif key == "Debt_Equity": test_data[key] = 5
            elif key == "CFO_PAT_Ratio": test_data[key] = -1
            elif key == "Down_From_52W_High%": test_data[key] = 80
            elif key == "F_Score": test_data[key] = 1
            elif key == "Market_Cap_Cr": test_data[key] = 100
            else: test_data[key] = -10
        
        score_info = calculate_institutional_score(test_data)
        pass_count = int(score_info['checklist_score'].split('/')[0])
        results.append((pass_count, score_info['total_score'], score_info['raw_score']))

    results.sort()
    print("Passes | Final Score | Raw Score")
    print("-------|-------------|-----------")
    for p, fs, rs in results:
        print(f"{p:6} | {fs:11.3f} | {rs:9.1f}")
        
    for i in range(1, len(results)):
        diff = abs(results[i][1] - results[i-1][1])
        if diff > 15:
            print(f"WARNING: Large jump detected at {results[i][0]} passes (diff: {diff:.1f})")

    # Verify tie-breaker
    print("\nVerifying Deterministic Tie-Breaker...")
    s1 = calculate_institutional_score({"Symbol": "AAA", "F_Score": 7, "Sector": "Tech"})["total_score"]
    s2 = calculate_institutional_score({"Symbol": "BBB", "F_Score": 7, "Sector": "Tech"})["total_score"]
    print(f"AAA Score: {s1:.5f}")
    print(f"BBB Score: {s2:.5f}")
    if s1 != s2:
        print("PASS: Scores are distinct and deterministic.")
    else:
        print("FAIL: Scores are still identical.")

if __name__ == "__main__":
    test_cliffs()

if __name__ == "__main__":
    test_cliffs()
