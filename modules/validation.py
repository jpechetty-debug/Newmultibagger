from modules.backtest import run_performance_analysis
import datetime

def validate_robustness(tickers):
    """
    Phase 31: Walk-Forward Robustness Check (Multi-Regime Testing).
    Tests the selected portfolio across different market years to check consistency.
    
    Since we cannot 're-screen' historical universes without a PIT database,
    we validate the *durability* of the current selection.
    """
    print("\n" + "="*50)
    print("🔬 PHASE 31: WALK-FORWARD ROBUSTNESS CHECK")
    print("   (Testing Portfolio Durability Across Market Cycles)")
    print("="*50)
    
    # Define Cycles
    cycles = [
        {"name": "2022 (Bear/Volatile)", "start": "2022-01-01", "end": "2022-12-31"},
        {"name": "2023 (Recovery)",      "start": "2023-01-01", "end": "2023-12-31"},
        {"name": "2024-Present (Bull)",  "start": "2024-01-01", "end": datetime.datetime.now().strftime("%Y-%m-%d")}
    ]
    
    scorecard = []
    
    for cycle in cycles:
        print(f"\n--- Testing Regime: {cycle['name']} ---")
        try:
            # We use Equal Weight for robustness check to see if the 'Picks' are good
            # (ignoring dynamic weights for history)
            res = run_performance_analysis(
                tickers, 
                weights=None, 
                start_date=cycle['start'], 
                end_date=cycle['end']
            )
            
            if res:
                alpha = res.get("Alpha", 0)
                status = "PASS ✅" if alpha > 0 else "FAIL ❌"
                scorecard.append(f"{cycle['name']:<20} | Alpha: {alpha:>6.1f}% | {status}")
            else:
                 scorecard.append(f"{cycle['name']:<20} | NO DATA")
                 
        except Exception as e:
            print(f"Error in {cycle['name']}: {e}")
            
    print("\n" + "-"*50)
    print("ROBUSTNESS SCORECARD")
    print("-"*50)
    for line in scorecard:
        print(line)
        
    print("-"*50)
    # Final Verdict
    pass_count = sum(1 for line in scorecard if "PASS" in line)
    if pass_count == 3:
        print("🏆 VERDICT: INSTITUTIONAL GRADE (All-Weather Alpha)")
    elif pass_count == 2:
        print("🥈 VERDICT: ROBUST (Survives most regimes)")
    else:
        print("⚠️ VERDICT: FRAGILE (Regime Dependent)")
    print("="*50 + "\n")
