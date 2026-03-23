import sqlite3
import pandas as pd
import re
from datetime import datetime

# Raw data from user
raw_data = """
MRPL
ENERGY
191.798	
85
-0.1%
6
13.0%	23.9%	
INST
2.01%
HIGH PROM
-24.8%
Fair: 145.79
BULL	242.2	177.5	
N/A

IMFA
BASIC MATERIALS
1,210.045	
80
-2.8%
8
9.3%	18.5%	
INST
0.87%
HIGH PROM
-35.8%
Fair: 845.39
BULL	1,646.4	1,180.7	
N/A

STYL
TECHNOLOGY
253.956	
80
-5.1%
7
10.1%	32.9%	
INST
5.88%
HIGH PROM
-34.9%
Fair: 162.37
BULL	311.8	228.6	
N/A

GARUDA
INDUSTRIALS
167.27	
75
-5.8%
4
125.0%	35.0%	
INST
0.42%
HIGH PROM
-51.1%
Fair: 93.09
BULL	238.2	167.2	
N/A

BLS
INDUSTRIALS
250.025	
75
-3.4%
4
43.6%	24.9%	
INST
5.34%
HIGH PROM
-51.2%
Fair: 134.86
BULL	345.1	252.3	
N/A

CANBK
FINANCIAL SERVICES
141.47	
72
4.8%
6
-42.6%	14.1%	
INST
10.91%
HIGH PROM
+70.4%
Fair: 254.59
BULL	186.8	141	
N/A

CHENNPETRO
ENERGY
939.333	
72
2.6%
5
21.3%	33.4%	
INST
5.11%
HIGH PROM
+54.8%
Fair: 1,387.85
BULL	1,120.6	831.9	
N/A

TRIVENI
CONSUMER DEFENSIVE
368.779	
72
-2.4%
2
16.5%	27.7%	
INST
10.68%
HIGH PROM
-44.7%
Fair: 210.31
BULL	475.4	356.6	
N/A

VAIBHAVGBL
CONSUMER CYCLICAL
213.861	
72
-7.9%
8
9.1%	12.8%	
INST
16.13%
HIGH PROM
-34.7%
Fair: 155.4
BULL	297.3	210.6	
N/A

VOLTAMP
INDUSTRIALS
8,587.539	
72
-4.0%
6
30.4%	18.8%	
INST
47.03%
-56.6%
Fair: 3,579.25
BULL	10,320.6	7,694.2	
N/A

LICI
FINANCIAL SERVICES
815	
72
2.4%
3
16.1%	50.4%	
INST
1.25%
HIGH PROM
-30.3%
Fair: 602.65
BULL	1,080.3	824.8	
N/A

YATHARTH
HEALTHCARE
681.471	
72
-4.6%
5
46.2%	23.7%	
INST
12.76%
HIGH PROM
-62.3%
Fair: 261.94
BULL	868.6	650.9	
N/A

GRAVITA
INDUSTRIALS
1,512.192	
72
-3.4%
4
2.1%	28.5%	
INST
13.36%
HIGH PROM
-62.9%
Fair: 606.15
BULL	2,040.4	1,530.8	
N/A

CHOLAHLDNG
FINANCIAL SERVICES
1,548.304	
72
-4.4%
5
18.6%	14.7%	
INST
30.55%
-15.9%
Fair: 1,437.43
BULL	2,136.5	1,596.4	
N/A

BANCOINDIA
CONSUMER CYCLICAL
566.158	
71
-3.0%
6
23.5%	23.7%	
INST
1.4%
HIGH PROM
-54.4%
Fair: 296.21
BULL	812.2	594.9	
N/A

TORNTPHARM
HEALTHCARE
4,432.468	
70
2.9%
9
17.6%	20.6%	
INST
14.71%
HIGH PROM
-85.5%
Fair: 613.02
BULL	5,283	4,034	
N/A

TATACOMM
COMMUNICATION SERVICES
1,474.286	
70
-2.8%
7
6.7%	98.3%	
INST
25.93%
HIGH PROM
-79.0%
Fair: 348.48
BULL	2,070.6	1,560.6	
N/A

SHILCTECH
INDUSTRIALS
3,840.851	
70
-5.5%
4
10.7%	34.8%	
INST
1.3%
HIGH PROM
-70.3%
Fair: 1,155.73
BULL	4,870.5	3,473.2	
N/A

VESUVIUS
INDUSTRIALS
495.56	
70
-2.5%
8
25.8%	13.9%	
INST
24.46%
HIGH PROM
-73.3%
Fair: 138.15
BULL	646.5	476.8	
N/A

HDFCAMC
FINANCIAL SERVICES
2,479.994	
70
-1.5%
7
20.1%	26.6%	
INST
24.02%
HIGH PROM
-80.9%
Fair: 521.85
BULL	3,415.2	2,592.7	
N/A

BHARTIHEXA
COMMUNICATION SERVICES
1,588.11	
70
-2.6%
8
4.8%	23.8%	
INST
10.8%
HIGH PROM
-80.6%
Fair: 325.66
BULL	2,100.5	1,587.9	
N/A

GULFOILLUB
BASIC MATERIALS
991.781	
70
-3.9%
6
9.1%	22.1%	
INST
8.75%
HIGH PROM
-33.6%
Fair: 726.74
BULL	1,368.5	1,029.1	
N/A

PRUDENT
FINANCIAL SERVICES
2,162.99	
70
-6.6%
6
20.6%	31.3%	
INST
28.99%
HIGH PROM
-82.0%
Fair: 463.42
BULL	3,211.7	2,363.7	
N/A

KRN
TECHNOLOGY
961.619	
70
13.9%
5
37.5%	34.1%	
INST
5.18%
HIGH PROM
-81.7%
Fair: 144.42
BULL	985.6	717	
N/A

ELECON
INDUSTRIALS
407.088	
70
-3.4%
6
4.3%	18.7%	
INST
7.87%
HIGH PROM
-48.3%
Fair: 219.82
BULL	531.2	385.4	
N/A

PREMIERENE
TECHNOLOGY
733.638	
70
-6.0%
8
13.0%	15.6%	
INST
12.73%
HIGH PROM
-70.8%
Fair: 220.21
BULL	941	700.8	
N/A

JYOTICNC
INDUSTRIALS
787.307	
70
-5.6%
6
28.1%	-23.6%	
INST
20.51%
HIGH PROM
+66.5%
Fair: 1,401.17
BULL	1,051.6	771.4	
N/A

SCI
INDUSTRIALS
239.005	
70
-3.5%
9
22.5%	11.5%	
INST
5.02%
HIGH PROM
+21.1%
Fair: 316.53
BULL	326.7	237.3	
N/A

BAJAJ-AUTO
CONSUMER CYCLICAL
9,501.12	
70
0.3%
3
23.1%	22.2%	
INST
15.75%
HIGH PROM
-69.6%
Fair: 2,960.76
BULL	12,161.2	9,303.2	
N/A

SHRIPISTON
CONSUMER CYCLICAL
2,943.7	
69
-0.6%
5
20.7%	19.1%	
INST
12.09%
HIGH PROM
-56.4%
Fair: 1,289.39
BULL	3,694	2,710.1	
N/A

FORCEMOT
CONSUMER CYCLICAL
21,442.756	
69
-3.3%
8
12.7%	11.4%	
INST
5.31%
HIGH PROM
-67.3%
Fair: 7,880.65
BULL	30,173.8	21,323.9	
N/A

REFEX
ENERGY
210.963	
69
-9.0%
3
-19.7%	23.7%	
INST
0.74%
HIGH PROM
-31.9%
Fair: 165.98
BULL	304.9	217	
N/A

PETRONET
ENERGY
288.5	
69
-1.3%
7
-8.7%	22.0%	
INST
29.36%
HIGH PROM
-8.2%
Fair: 277.04
BULL	377.2	286	
N/A

TIMETECHNO
CONSUMER CYCLICAL
167.417	
68
-3.7%
9
12.8%	11.1%	
INST
21.23%
-37.0%
Fair: 121.29
BULL	240.8	179.1	
N/A

GOKULAGRO
CONSUMER DEFENSIVE
161.963	
68
-6.2%
9
26.6%	21.9%	
INST
2.45%
HIGH PROM
-41.6%
Fair: 96.89
BULL	207.3	152.8	
N/A

CASTROLIND
ENERGY
185.588	
68
-3.5%
7
6.4%	43.7%	
INST
20.29%
HIGH PROM
-65.7%
Fair: 64.37
BULL	234.6	182.7	
N/A

RRKABEL
INDUSTRIALS
1,476.574	
68
0.1%
3
42.3%	15.3%	
INST
18.21%
HIGH PROM
-69.7%
Fair: 432.33
BULL	1,781.8	1,333.2	
N/A

SHARDACROP
BASIC MATERIALS
1,014.266	
67
-3.1%
7
38.7%	11.8%	
INST
10.53%
HIGH PROM
-44.9%
Fair: 647.02
BULL	1,466.6	1,044	
N/A

BRITANNIA
CONSUMER DEFENSIVE
5,965.496	
67
-0.7%
7
8.2%	57.4%	
INST
24.77%
HIGH PROM
-90.3%
Fair: 590.69
BULL	7,635.6	5,860.2	
N/A

TRANSRAILL
INDUSTRIALS
517	
67
-2.9%
7
32.6%	15.4%	
INST
1.16%
HIGH PROM
-41.1%
Fair: 334.76
BULL	710.1	520.1	
N/A

MSTCLTD
INDUSTRIALS
425.132	
67
-6.3%
5
9.0%	35.5%	
INST
3.01%
HIGH PROM
-37.9%
Fair: 285.88
BULL	575.3	432	
N/A

ENRIN
UTILITIES
2,935.686	
67
4.2%
9
26.0%	21.9%	
INST
58.48%
-89.0%
Fair: 303.61
BULL	3,447.1	2,556.5	
N/A

SKYGOLD
CONSUMER CYCLICAL
331.355	
66
-4.7%
5
77.1%	19.3%	
INST
11.42%
HIGH PROM
-58.5%
Fair: 152.3
BULL	458.4	324.5	
N/A

PNGJL
CONSUMER CYCLICAL
549.767	
66
-3.8%
5
35.6%	20.4%	
INST
4.47%
HIGH PROM
-49.9%
Fair: 286.42
BULL	714.6	526.9	
N/A

BANKINDIA
FINANCIAL SERVICES
154.027	
65
3.7%
7
8.9%	8.4%	
INST
15.06%
HIGH PROM
+79.5%
Fair: 303.55
BULL	211.5	158.6	
N/A

JAMNAAUTO
CONSUMER CYCLICAL
126.048	
65
-5.3%
4
18.7%	20.7%	
INST
8.88%
HIGH PROM
-62.7%
Fair: 53.33
BULL	178.5	126.5	
N/A

INDUSTOWER
COMMUNICATION SERVICES
443.05	
65
-2.4%
8
7.9%	22.8%	
INST
29.55%
HIGH PROM
-37.5%
Fair: 295.82
BULL	591.1	448.3	
N/A

NAM-INDIA
FINANCIAL SERVICES
860.911	
65
-1.8%
6
29.4%	25.1%	
INST
90.85%
-80.2%
Fair: 186.02
BULL	1,176.1	857	
N/A

EXHICON.BO
COMMUNICATION SERVICES
501.836	
65
-5.3%
7
63.8%	57.1%	
INST
0%
HIGH PROM
-58.6%
Fair: 227.56
BULL	686.7	509.6	
N/A

SPORTKING
UNKNOWN
110.44	
65
-5.8%
7
6.2%	26.4%	
INST
0%
0.0%
Fair: 0
BULL	145	104.3	
N/A
"""

def clean_val(val):
    if not val: return None
    val = val.replace('%', '').replace(',', '').strip()
    try:
        return float(val)
    except:
        return val

def parse_elite_data(data):
    lines = [l.strip() for l in data.split('\n') if l.strip()]
    stocks = []
    
    i = 0
    while i < len(lines):
        try:
            ticker = lines[i]
            sector = lines[i+1]
            price = clean_val(lines[i+2])
            rank = clean_val(lines[i+3])
            ai_predict = clean_val(lines[i+4])
            quality = clean_val(lines[i+5])
            
            growth_roe = lines[i+6].split()
            sales_growth = clean_val(growth_roe[0]) if len(growth_roe) > 0 else 0
            roe = clean_val(growth_roe[1]) if len(growth_roe) > 1 else 0
            
            inst_label = lines[i+7] # INST
            inst_holding = clean_val(lines[i+8])
            
            # Handling variable number of lines for promoter/valuation
            prom_val = lines[i+9]
            if "PROM" in prom_val:
                promoter_holding = 75 if "HIGH" in prom_val else 50
                val_gap = clean_val(lines[i+10])
                fair_line = lines[i+11]
                signal_line = lines[i+12]
                backtest_line = lines[i+13]
                i_step = 14
            else:
                # No PROM line, maybe skipped
                promoter_holding = 0
                val_gap = clean_val(prom_val)
                fair_line = lines[i+10]
                signal_line = lines[i+11]
                backtest_line = lines[i+12]
                i_step = 13
            
            fair_val = clean_val(fair_line.replace('Fair:', ''))
            
            signal_parts = signal_line.split()
            signal = signal_parts[0]
            target = clean_val(signal_parts[1]) if len(signal_parts) > 1 else 0
            stop = clean_val(signal_parts[2]) if len(signal_parts) > 2 else 0
            
            # Normalize Ticker
            if not ticker.endswith('.NS') and not ticker.endswith('.BO'):
                ticker += '.NS'
            
            stocks.append({
                'symbol': ticker,
                'sector': sector,
                'price': price,
                'score': rank,
                'ml_predicted_return': ai_predict,
                'f_score': quality,
                'sales_cagr_5y': sales_growth,
                'avg_roe_5y': roe,
                'inst_holding': inst_holding,
                'promoter_holding': promoter_holding,
                'value_gap': val_gap,
                'graham_number': fair_val,
                'technical_signal': signal,
                'target_1': target,
                'stop_loss': stop,
                'updated_at': datetime.now()
            })
            i += i_step
        except Exception as e:
            print(f"Error parsing at index {i} ({lines[i] if i < len(lines) else 'EOF'}): {e}")
            i += 1
            
    return stocks

def upsert_to_db(stocks):
    conn = sqlite3.connect('stocks.db')
    cursor = conn.cursor()
    
    count = 0
    for s in stocks:
        try:
            # We use INSERT OR REPLACE but need to be careful not to wipe other columns if we use REPLACE
            # Better to use UPDATE or a selective REPLACE if table exists.
            # But database.py uses a delete-and-append pattern for multibaggers.
            # We'll do a manual UPDATE or INSERT for each.
            
            cursor.execute("SELECT symbol FROM multibaggers WHERE symbol = ?", (s['symbol'],))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute("""
                    UPDATE multibaggers SET 
                        price = ?, sector = ?, score = ?, ml_predicted_return = ?, 
                        f_score = ?, sales_cagr_5y = ?, avg_roe_5y = ?, 
                        inst_holding = ?, promoter_holding = ?, value_gap = ?, 
                        graham_number = ?, technical_signal = ?, target_1 = ?, 
                        stop_loss = ?, updated_at = ?
                    WHERE symbol = ?
                """, (
                    s['price'], s['sector'], s['score'], s['ml_predicted_return'],
                    s['f_score'], s['sales_cagr_5y'], s['avg_roe_5y'],
                    s['inst_holding'], s['promoter_holding'], s['value_gap'],
                    s['graham_number'], s['technical_signal'], s['target_1'],
                    s['stop_loss'], s['updated_at'], s['symbol']
                ))
            else:
                cursor.execute("""
                    INSERT INTO multibaggers 
                    (symbol, price, sector, score, ml_predicted_return, f_score, 
                     sales_cagr_5y, avg_roe_5y, inst_holding, promoter_holding, 
                     value_gap, graham_number, technical_signal, target_1, stop_loss, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s['symbol'], s['price'], s['sector'], s['score'], s['ml_predicted_return'],
                    s['f_score'], s['sales_cagr_5y'], s['avg_roe_5y'],
                    s['inst_holding'], s['promoter_holding'], s['value_gap'],
                    s['graham_number'], s['technical_signal'], s['target_1'],
                    s['stop_loss'], s['updated_at']
                ))
            count += 1
        except Exception as e:
            print(f"Error upserting {s['symbol']}: {e}")
            
    conn.commit()
    conn.close()
    print(f"✅ Successfully ingested {count} elite picks.")

if __name__ == "__main__":
    stocks = parse_elite_data(raw_data)
    print(f"Parsed {len(stocks)} stocks.")
    upsert_to_db(stocks)
