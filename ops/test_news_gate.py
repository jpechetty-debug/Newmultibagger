
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.news_gate import NewsGate
from portfolio.allocator import PortfolioAllocator

def test_news_gate():
    print("Testing Governance Kill Switch (News Gate)...")
    
    gate = NewsGate()
    
    # 1. Test Direct Logic
    print("\n--- Direct Keyword Test ---")
    
    clean_news = [{"title": "Quarterly Results announced", "summary": "Profit up 20%"}]
    dirty_news_1 = [{"title": "Auditor Resigns citing lack of info", "summary": "Statutory auditor quits."}]
    dirty_news_2 = [{"title": "SEBI bars promoter from market", "summary": "Insider trading case."}]
    dirty_news_3 = ["Some random text", "CBI raids company headquarters"] # List of strings format
    
    print(f"1. Clean News: {gate.validate_news('CLEAN', clean_news)}")
    print(f"2. Auditor Resign: {gate.validate_news('DIRTY1', dirty_news_1)}")
    print(f"3. SEBI Bar: {gate.validate_news('DIRTY2', dirty_news_2)}")
    print(f"4. CBI Raid (String List): {gate.validate_news('DIRTY3', dirty_news_3)}")
    
    # Check assertions
    if gate.validate_news('A', clean_news)[0] and not gate.validate_news('B', dirty_news_1)[0]:
        print("✅ Direct Logic Passed")
    else:
        print("❌ Direct Logic Failed")

    # 2. Test Allocator Integration
    print("\n--- Allocator Gate 0 Test ---")
    allocator = PortfolioAllocator(capital=1000000)
    
    proposals = [
        {
            "Symbol": "GOOD_CO",
            "Price": 100,
            "Recent_News": [{"title": "New plant entry", "summary": "Expansion plans."}],
            "Rank_Score": 90
        },
        {
            "Symbol": "FRAUD_CO",
            "Price": 50,
            "Recent_News": [{"title": "Forensic audit ordered", "summary": "Stock tanks 20%."}],
            "Rank_Score": 95 # Higher rank but should be blocked
        }
    ]
    
    allocations = allocator.allocate(proposals)
    
    allocated_symbols = [a['Symbol'] for a in allocations]
    print(f"Allocated: {allocated_symbols}")
    
    if "GOOD_CO" in allocated_symbols and "FRAUD_CO" not in allocated_symbols:
        print("✅ Allocator Gate 0 Passed (Blocked FRAUD_CO)")
    else:
        print("❌ Allocator Gate 0 Failed")

if __name__ == "__main__":
    test_news_gate()
