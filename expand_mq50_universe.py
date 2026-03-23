
import csv
import os
import re

def expand_mq50():
    csv_file = 'MW-NIFTY500-MULTICAP-MOMENTUM-QUALITY-50-12-Feb-2026.csv'
    ticker_file = 'ticker_list.py'
    
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found.")
        return

    new_symbols = set()
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # Data starts from line 18 (index 17) based on file view
            for line in lines[17:]:
                parts = line.split(',')
                if parts:
                    symbol = parts[0].strip().strip('"')
                    # Filter out Index name or empty lines
                    if symbol and symbol != "SYMBOL" and "NIFTY" not in symbol:
                        new_symbols.add(f"{symbol}.NS")
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        return

    print(f"Found {len(new_symbols)} unique symbols in MQ50 CSV.")

    # Read existing tickers to avoid duplicates
    existing_tickers = []
    with open(ticker_file, 'r') as f:
        content = f.read()
        existing_tickers = re.findall(r'"([^"]+)"', content)
    
    existing_set = set(existing_tickers)
    total_added = 0
    
    new_to_add = []
    for s in sorted(list(new_symbols)):
        if s not in existing_set:
            new_to_add.append(s)
            total_added += 1

    if not new_to_add:
        print("No new tickers to add. All MQ50 stocks are already in the list.")
        return

    print(f"Adding {total_added} new Momentum Quality tickers...")

    # Update ticker_list.py
    with open(ticker_file, 'r') as f:
        lines = f.readlines()

    # Find the last ']' and insert before it
    last_bracket_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if ']' in lines[i]:
            last_bracket_idx = i
            break

    if last_bracket_idx != -1:
        addition = [f"\n    # --- NIFTY MOMENTUM QUALITY 50 EXPANSION ---\n"]
        # Group in lines of 5
        for i in range(0, len(new_to_add), 5):
            chunk = new_to_add[i:i+5]
            line = "    " + ", ".join([f'"{s}"' for s in chunk]) + ",\n"
            addition.append(line)
        
        lines.insert(last_bracket_idx, "".join(addition))

    with open(ticker_file, 'w') as f:
        f.writelines(lines)

    print(f"Update complete. Added {total_added} tickers.")

if __name__ == "__main__":
    expand_mq50()
