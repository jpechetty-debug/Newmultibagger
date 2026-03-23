
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
import ticker_list

def clean_symbol(sym):
    if not isinstance(sym, str): return ""
    sym = sym.strip()
    if not sym.endswith(".NS") and not sym.endswith(".BO"):
        return f"{sym}.NS"
    return sym

def main():
    raw_list = [clean_symbol(s) for s in ticker_list.TICKERS if s]
    unique_list = sorted(list(set(raw_list)))
    
    output_path = os.path.join(BASE_DIR, "ops", "ticker_list_822.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(unique_list))
    
    print(f"Generated {len(unique_list)} unique tickers in {output_path}")

if __name__ == "__main__":
    main()
