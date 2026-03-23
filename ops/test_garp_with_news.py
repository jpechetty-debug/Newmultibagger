
import sys
import os
import pandas as pd

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.garp_strategy import GarpStrategy
from portfolio.allocator import PortfolioAllocator

def test_garp_news_integration():
    print("Testing GARP Strategy + News Gate Integration...")
    
    strategy = GarpStrategy()
    
    # 1. Mock Universe (Override load_universe to avoid DB dependency for this test)
    # We use a real symbol (TCS) to test news fetching
    mock_universe = pd.DataFrame([
        {
            "symbol": "TCS.NS",
            "price": 3500,
            "sector": "IT Services",
            "score": 90,
            "sales_growth_5y%": 20, 
            "sales_growth_ttm%": 18,
            "avg_roe_5y%": 30,
            "roe%": 35,
            "peg_ratio": 1.5,
            "debt_equity": 0.0,
            "promoter_holding%": 72,
            "inst_holding%": 20,
            "conviction_score": 80,
            "rs_rating": 2.0
        }
    ])
    
    # Monkey patch logic to return this universe
    strategy.universe = mock_universe
    # We skip load_universe call by setting it directly and not calling it in generate_proposals?
    # No, generate_proposals calls load_universe. We can monkeypatch load_universe.
    strategy.load_universe = lambda: setattr(strategy, 'universe', mock_universe)
    
    print("1. Generating Proposals (Fetching News)...")
    proposals = strategy.generate_proposals(top_n=5)
    
    if not proposals:
        print("❌ No proposals generated (Filters might have failed or Fetch error)")
        return

    tcs_prop = proposals[0]
    print(f"   Proposal: {tcs_prop['Symbol']}")
    
    # 2. Verify News Fetching
    news = tcs_prop.get('Recent_News', [])
    print(f"   News Items Fetched: {len(news)}")
    if len(news) > 0:
        print(f"   Sample Title: {news[0].get('title', 'N/A')}")
        print("✅ News Fetching Works")
    else:
        print("⚠️ No news fetched (Could be network or no news)")
        
    # 3. Test Allocator Gate 0 (Injection)
    print("\n2. Testing Allocator Gate 0...")
    allocator = PortfolioAllocator(capital=1000000)
    
    # Clean Case
    print("   Allocating Clean Proposal...")
    allocs = allocator.allocate([tcs_prop])
    if allocs:
        print("✅ Clean Allocation Passed")
    else:
        print("❌ Clean Allocation Failed")
        
    # Dirty Case (Inject Bad News)
    print("   Injecting Bad News (Auditor Resignation)...")
    tcs_prop['Recent_News'] = [{'title': 'Auditor Resigns immediately', 'summary': 'Fraud detected.'}]
    
    allocs_dirty = allocator.allocate([tcs_prop])
    if not allocs_dirty:
        print("✅/🛑 Gate 0 Blocked Bad News (Expected)")
    else:
        print(f"❌ Gate 0 Failed! Allocated: {allocs_dirty}")

if __name__ == "__main__":
    try:
        test_garp_news_integration()
    except Exception as e:
        import traceback
        with open("ops/error.log", "w") as f:
            f.write(traceback.format_exc())
        print("Error written to ops/error.log")
