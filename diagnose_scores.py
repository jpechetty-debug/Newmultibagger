"""Quick diagnostic of current scores in DB."""
import sqlite3
import pandas as pd

conn = sqlite3.connect("stocks.db")

# 1. Check columns
cols = [row[1] for row in conn.execute("PRAGMA table_info(multibaggers)").fetchall()]

# 2. Load all data
df = pd.read_sql("SELECT * FROM multibaggers ORDER BY score DESC", conn)

lines = []
lines.append(f"Total stocks in DB: {len(df)}")
lines.append(f"Score >= 80 (Elite): {len(df[df['score'] >= 80])}")
lines.append(f"Score >= 65 (Buy):   {len(df[df['score'] >= 65])}")
lines.append(f"Score >= 50 (Hold):  {len(df[df['score'] >= 50])}")
lines.append(f"Score <  50 (Avoid): {len(df[df['score'] < 50])}")
lines.append(f"Score Stats: Mean={df['score'].mean():.1f}, Median={df['score'].median():.1f}, Max={df['score'].max():.1f}, Min={df['score'].min():.1f}")
lines.append("")

# 3. Top 25
display_cols = ['symbol', 'score']
for c in ['price', 'sales_growth', 'roe', 'pe_ratio', 'peg_ratio', 'f_score', 'debt_equity', 
           'rs_rating', 'market_cap_cr', 'conviction_score', 'technical_signal']:
    if c in df.columns:
        display_cols.append(c)

lines.append("=== TOP 25 STOCKS ===")
top = df[display_cols].head(25)
pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 200)
lines.append(top.to_string(index=False))

with open("diagnosis_output.txt", "w") as f:
    f.write("\n".join(lines))
    
conn.close()
print("Done -> diagnosis_output.txt")
