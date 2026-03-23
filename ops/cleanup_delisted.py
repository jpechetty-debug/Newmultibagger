
import sqlite3
import os

# Safe list to NEVER delete automatically
WHITELIST = ["TATAMOTORS.NS", "REC.NS", "RECLTD.NS", "RELIANCE.NS", "SBIN.NS", "HDFCBANK.NS"]

def cleanup():
    candidates_file = "delisted_candidates.txt"
    if not os.path.exists(candidates_file):
        print("No candidates file found.")
        return

    with open(candidates_file, "r") as f:
        candidates = [line.strip() for line in f if line.strip()]

    to_delete = []
    for c in candidates:
        if c in WHITELIST:
            print(f"⚠️ Skipping WHITELISTED stock: {c}")
        else:
            to_delete.append(c)

    if not to_delete:
        print("No stocks to delete.")
        return

    print(f"Preparing to delete: {to_delete}")

    # 1. DB Cleanup
    db_path = "stocks.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    for sym in to_delete:
        cursor.execute("DELETE FROM multibaggers WHERE symbol = ?", (sym,))
        if cursor.rowcount > 0:
            print(f"✅ Deleted {sym} from DB.")
        else:
            print(f"⚠️ {sym} not found in DB.")
            
    conn.commit()
    conn.close()

    # 2. Update ticker_list.py
    ticker_file = "ticker_list.py"
    with open(ticker_file, "r") as f:
        lines = f.readlines()

    new_lines = []
    removed_count = 0
    for line in lines:
        keep = True
        for sym in to_delete:
            if f'"{sym}"' in line or f"'{sym}'" in line:
                # Basic check, might be part of a list
                # Inspecting line content
                if sym in line:
                    # Replace the quoted string with empty or remove line if it's just that ticker?
                    # ticker_list.py structure is `    "SYM", "SYM2",`
                    # We can replace `"SYM",` with ``
                    line = line.replace(f'"{sym}",', "")
                    line = line.replace(f"'{sym}',", "")
                    line = line.replace(f'"{sym}"', "")
                    line = line.replace(f"'{sym}'", "")
                    print(f"removed {sym} from ticker_list.py")
                    removed_count += 1
        
        if line.strip() != "" and line.strip() != ",":
            new_lines.append(line)

    with open(ticker_file, "w") as f:
        f.writelines(new_lines)
        
    print(f"Updated ticker_list.py (removed references).")

if __name__ == "__main__":
    cleanup()
