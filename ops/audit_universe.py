
import pandas as pd
import os
import sys

# Define Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
import ticker_list

NIFTY_500_CSV = os.path.join(BASE_DIR, "MW-NIFTY-500-12-Feb-2026.csv")
MICROCAP_250_CSV = os.path.join(BASE_DIR, "MW-NIFTY-MICROCAP-250-12-Feb-2026.csv")

def clean_symbol(sym):
    if not isinstance(sym, str): return ""
    sym = sym.strip()
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        return f"{sym}.NS"
    return sym

def main():
    output = []
    output.append("--- Auditing Stock Universe ---")
    
    # 1. Nifty 500
    try:
        df_500 = pd.read_csv(NIFTY_500_CSV)
        output.append(f"Nifty 500 CSV Columns: {list(df_500.columns)}")
        # Try to find symbol column
        col = next((c for c in df_500.columns if 'symbol' in c.lower()), None)
        if col:
            nifty_500 = set([clean_symbol(s) for s in df_500[col].tolist()])
            output.append(f"NIFTY 500 Count: {len(nifty_500)}")
        else:
            output.append("Could not find symbol column in Nifty 500 CSV")
            nifty_500 = set()
    except Exception as e:
        output.append(f"Error reading Nifty 500 CSV: {e}")
        nifty_500 = set()

    # 2. Microcap 250
    try:
        df_micro = pd.read_csv(MICROCAP_250_CSV)
        output.append(f"Microcap 250 CSV Columns: {list(df_micro.columns)}")
        col = next((c for c in df_micro.columns if 'symbol' in c.lower()), None)
        if col:
            micro_250 = set([clean_symbol(s) for s in df_micro[col].tolist()])
            output.append(f"Microcap 250 Count: {len(micro_250)}")
        else:
            output.append("Could not find symbol column in Microcap 250 CSV")
            micro_250 = set()
    except Exception as e:
        output.append(f"Error reading Microcap 250 CSV: {e}")
        micro_250 = set()

    # 3. Current Ticker List - CHECK DUPLICATES
    try:
        raw_list = [clean_symbol(s) for s in ticker_list.TICKERS if s]
        current_set = set(raw_list)
        output.append(f"Current ticker_list.py Raw Count: {len(raw_list)}")
        output.append(f"Current ticker_list.py Unique Count: {len(current_set)}")
        
        # Find Duplicates
        seen = set()
        dupes = set()
        for x in raw_list:
            if x in seen:
                dupes.add(x)
            seen.add(x)
            
        if dupes:
            output.append(f"DUPLICATES FOUND ({len(dupes)}): {', '.join(dupes)}")
        else:
            output.append("No duplicates found in ticker_list.py")
            
    except Exception as e:
        output.append(f"Error reading ticker_list.py: {e}")
        current_set = set()
        user_picks = set() # Define to avoid error later

    # 4. User Picks (Stocks in current_list BUT NOT in Nifty Indices)
    universe_indices = nifty_500.union(micro_250)
    user_picks = current_set - universe_indices # Use current_set here
    output.append(f"User Picks (Outside Indices): {len(user_picks)}")
    
    # 5. Total Theoretical Universe
    total_universe = universe_indices.union(user_picks)
    output.append(f"Total Combined Universe: {len(total_universe)}")
    
    # 6. Check against 818
    target = 818
    diff = target - len(total_universe)
    output.append(f"Target: {target}")
    output.append(f"Difference: {diff}")

    if len(total_universe) == target:
        output.append("\n[MATCH] The 818 stocks are: Nifty 500 + Microcap 250 + Specific User Picks.")
    else:
        output.append("\n[MISMATCH] Breakdown:")
        output.append(f"Nifty 500: {len(nifty_500)}")
        
        # Breakdown Nifty 500
        # for s in nifty_500: output.append(f"  {s}")

        output.append(f"Microcap 250: {len(micro_250)}")
        output.append(f"User Picks unique: {len(user_picks)}")
        
    # Write to file
    with open(os.path.join(BASE_DIR, "ops", "audit_result.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(output))

if __name__ == "__main__":
    main()
