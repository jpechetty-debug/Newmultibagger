import csv
import re

def get_csv_tickers(file_path):
    tickers = []
    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row['Symbol'].strip()
            if symbol:
                tickers.append(symbol)
    return tickers

def get_current_tickers(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Regex to find strings inside quotes in the TICKERS list
    tickers = re.findall(r'"([^"]+)"', content)
    return tickers

csv_list = get_csv_tickers('Return Yearly.csv')
current_list = get_current_tickers('ticker_list.py')

# Normalize: remove .NS or .BO for comparison
current_normalized = {t.split('.')[0] for t in current_list}

missing = []
for symbol in csv_list:
    if symbol not in current_normalized:
        missing.append(symbol)

print(f"Total in CSV: {len(csv_list)}")
print(f"Total in Ticker List: {len(current_list)}")
print(f"Missing Tickers: {len(missing)}")
print("List of Missing Tickers:")
for m in missing:
    print(f'"{m}.NS",')
