import pandas as pd

def _safe_div(numerator, denominator, default=0.0):
    try:
        if denominator in (0, None):
            return default
        return numerator / denominator
    except Exception:
        return default


def calculate_piotroski_f_score(ticker):
    """
    Calculates the 9-point Piotroski F-Score.
    """
    f_score = 0
    try:
        fin = ticker.financials
        bs = ticker.balance_sheet
        cf = ticker.cashflow

        if fin.empty or bs.empty or cf.empty:
            return 0

        # 1. Profitability (4 pts)
        net_income = fin.loc["Net Income"].iloc[0] if "Net Income" in fin.index else 0
        total_assets = bs.loc["Total Assets"].iloc[0] if "Total Assets" in bs.index else 1
        roa = _safe_div(net_income, total_assets)
        if roa > 0:
            f_score += 1

        cfo = (
            cf.loc["Operating Cash Flow"].iloc[0]
            if "Operating Cash Flow" in cf.index
            else 0
        )
        if cfo > 0:
            f_score += 1

        net_income_prev = (
            fin.loc["Net Income"].iloc[1]
            if len(fin.columns) > 1 and "Net Income" in fin.index
            else 0
        )
        total_assets_prev = (
            bs.loc["Total Assets"].iloc[1]
            if len(bs.columns) > 1 and "Total Assets" in bs.index
            else 1
        )
        roa_prev = _safe_div(net_income_prev, total_assets_prev)
        if roa > roa_prev:
            f_score += 1

        if cfo > net_income:
            f_score += 1

        # 2. Leverage (3 pts)
        ltd = bs.loc["Long Term Debt"].iloc[0] if "Long Term Debt" in bs.index else 0
        ltd_prev = (
            bs.loc["Long Term Debt"].iloc[1]
            if len(bs.columns) > 1 and "Long Term Debt" in bs.index
            else 0
        )
        if _safe_div(ltd, total_assets) <= _safe_div(ltd_prev, total_assets_prev):
            f_score += 1

        current_assets = (
            bs.loc["Current Assets"].iloc[0] if "Current Assets" in bs.index else 0
        )
        current_liab = (
            bs.loc["Current Liabilities"].iloc[0]
            if "Current Liabilities" in bs.index
            else 1
        )
        curr_ratio = _safe_div(current_assets, current_liab)

        current_assets_prev = (
            bs.loc["Current Assets"].iloc[1]
            if len(bs.columns) > 1 and "Current Assets" in bs.index
            else 0
        )
        current_liab_prev = (
            bs.loc["Current Liabilities"].iloc[1]
            if len(bs.columns) > 1 and "Current Liabilities" in bs.index
            else 1
        )
        curr_ratio_prev = _safe_div(current_assets_prev, current_liab_prev)

        if curr_ratio > curr_ratio_prev:
            f_score += 1

        shares = (
            bs.loc["Ordinary Shares Number"].iloc[0]
            if "Ordinary Shares Number" in bs.index
            else 0
        )
        shares_prev = (
            bs.loc["Ordinary Shares Number"].iloc[1]
            if len(bs.columns) > 1 and "Ordinary Shares Number" in bs.index
            else 0
        )
        if shares <= shares_prev:
            f_score += 1

        # 3. Efficiency (2 pts)
        gp = fin.loc["Gross Profit"].iloc[0] if "Gross Profit" in fin.index else 0
        rev = fin.loc["Total Revenue"].iloc[0] if "Total Revenue" in fin.index else 1
        gm = _safe_div(gp, rev)

        gp_prev = (
            fin.loc["Gross Profit"].iloc[1]
            if len(fin.columns) > 1 and "Gross Profit" in fin.index
            else 0
        )
        rev_prev = (
            fin.loc["Total Revenue"].iloc[1]
            if len(fin.columns) > 1 and "Total Revenue" in fin.index
            else 1
        )
        gm_prev = _safe_div(gp_prev, rev_prev)
        if gm > gm_prev:
            f_score += 1

        ato = _safe_div(rev, total_assets)
        ato_prev = _safe_div(rev_prev, total_assets_prev)
        if ato > ato_prev:
            f_score += 1

        return f_score
    except Exception:
        return 0


def extract_financial_metric(df, keys, default=0):
    """
    Finds a metric in a DataFrame using a list of possible keys or partial matches.
    """
    if df.empty:
        return default
    
    # 1. Try exact matches first
    for key in keys:
        if key in df.index:
            val = df.loc[key].iloc[0]
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val
                
    # 2. Try partial/fuzzy matches if no exact match found
    for key in keys:
        for index_name in df.index:
            if key.lower() in index_name.lower():
                val = df.loc[index_name].iloc[0]
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    return val
    return default


def calculate_current_roe(ticker):
    """
    Derives Current ROE from Net Income and Equity statements.
    """
    try:
        fin = ticker.financials
        bs = ticker.balance_sheet
        if fin.empty or bs.empty:
            return 0

        # Keys used by yfinance can be inconsistent
        net_income = extract_financial_metric(
            fin, ["Net Income", "Net Profit", "PAT", "Profit After Tax"]
        )
        equity = extract_financial_metric(
            bs, ["Stockholders Equity", "Common Stock Equity", "Total Equity", "Shareholders Equity"]
        )

        roe = _safe_div(net_income, equity)
        return round(roe * 100, 2)
    except Exception:
        return 0


def calculate_roce(ticker):
    """
    Calculates Return on Capital Employed (ROCE).
    ROCE = EBIT / (Total Assets - Current Liabilities)
    """
    try:
        fin = ticker.financials
        bs = ticker.balance_sheet
        if fin.empty or bs.empty:
            return 0

        # EBIT or Operating Income
        ebit = extract_financial_metric(
            fin, ["EBIT", "Operating Income", "Operating Profit"]
        )
        
        # Capital Employed = Total Assets - Current Liabilities
        total_assets = extract_financial_metric(
            bs, ["Total Assets"]
        )
        current_liabilities = extract_financial_metric(
            bs, ["Current Liabilities", "Total Current Liabilities"]
        )
        
        capital_employed = total_assets - current_liabilities
        
        roce = _safe_div(ebit, capital_employed)
        return round(roce * 100, 2)
    except Exception:
        return 0


def calculate_median_pat_growth(ticker, years=5):
    """
    Calculates the median PAT (Profit After Tax) growth over the last N years.
    """
    try:
        fin = ticker.financials
        if fin.empty:
            return 0

        pat_keys = ["Net Income", "Net Profit", "PAT", "Profit After Tax"]
        row_key = None
        for key in pat_keys:
            if key in fin.index:
                row_key = key
                break
            for index_name in fin.index:
                if key.lower() in index_name.lower():
                    row_key = index_name
                    break
            if row_key: break
            
        if not row_key:
            return 0

        pats = fin.loc[row_key]
        if isinstance(pats, pd.DataFrame):
            pats = pats.iloc[0]
            
        pats = pats.iloc[::-1] # Oldest to newest
        if len(pats) < 2:
            return 0

        growths = []
        for i in range(1, len(pats)):
            prev = pats.iloc[i-1]
            curr = pats.iloc[i]
            if prev != 0 and pd.notna(prev) and pd.notna(curr):
                growths.append((curr - prev) / abs(prev))
        
        if not growths:
            return 0
            
        import numpy as np
        median_growth = np.median(growths)
        return round(float(median_growth) * 100, 2)
    except Exception:
        return 0


def calculate_recent_sales_growth(ticker):
    """
    Calculates Sales Growth (YoY) from the last two financial years.
    """
    try:
        fin = ticker.financials
        if fin.empty:
            return 0

        # financials.iloc[0] is most recent, iloc[1] is previous
        revenue_keys = ["Total Revenue", "Operating Revenue", "Revenue From Operations", "Net Sales"]
        
        # Fuzzy match for the row key
        row_key = None
        for key in revenue_keys:
            # Try exact first
            if key in fin.index:
                row_key = key
                break
            # Try fuzzy
            for index_name in fin.index:
                if key.lower() in index_name.lower():
                    row_key = index_name
                    break
            if row_key: break
        
        if not row_key:
            return 0

        revs = fin.loc[row_key]
        if isinstance(revs, pd.DataFrame): # safety for multi-row matches
            revs = revs.iloc[0]
            
        if len(revs) < 2:
            return 0

        curr_rev = revs.iloc[0]
        prev_rev = revs.iloc[1]

        # Handle potential None/NaN
        if pd.isna(curr_rev) or pd.isna(prev_rev) or prev_rev == 0:
            return 0

        growth = _safe_div(curr_rev - prev_rev, prev_rev)
        return round(growth * 100, 2)
    except Exception:
        return 0


def check_earnings_inflection(ticker):
    """
    Detects detailed earnings acceleration (Phase 12).
    Returns a dict with status and score (0-5).
    """
    score = 0
    try:
        q_fin = ticker.quarterly_financials
        if q_fin.empty or len(q_fin.columns) < 3:
            return {"score": 0, "status": False}

        if "Total Revenue" not in q_fin.index or "Net Income" not in q_fin.index:
            return {"score": 0, "status": False}

        # 1. Revenue Acceleration
        rev = q_fin.loc["Total Revenue"]
        rev_curr = rev.iloc[0]
        rev_prev = rev.iloc[1]
        rev_prev2 = rev.iloc[2]

        rev_growth_curr = _safe_div(rev_curr - rev_prev, rev_prev)
        rev_growth_prev = _safe_div(rev_prev - rev_prev2, rev_prev2)

        if rev_growth_curr > rev_growth_prev:
            score += 1  # Revenue Accelerating

        if rev_growth_curr > 0.15:  # >15% Growth
            score += 1

        # 2. EPS Acceleration (Using Net Income as proxy if EPS missing)
        ni = q_fin.loc["Net Income"]
        ni_curr = ni.iloc[0]
        ni_prev = ni.iloc[1]
        ni_prev2 = ni.iloc[2]

        ni_growth_curr = _safe_div(ni_curr - ni_prev, abs(ni_prev))
        ni_growth_prev = _safe_div(ni_prev - ni_prev2, abs(ni_prev2))

        if ni_growth_curr > ni_growth_prev:
            score += 1  # Earnings Accelerating

        if ni_growth_curr > 0.20:  # >20% Growth
            score += 1

        # 3. Margin Expansion
        margin_curr = _safe_div(ni_curr, rev_curr)
        margin_prev = _safe_div(ni_prev, rev_prev)

        if margin_curr > margin_prev:
            score += 1  # Margin Expanding

        return {"score": score, "status": score >= 3}  # True if 3+ points
    except Exception:
        return {"score": 0, "status": False}


def analyze_margins_and_leverage(ticker):
    """
    Phase 14: Analyzes Operating Leverage and Margin Trends.
    Returns a dict with 'Margin_Trend' (bool) and 'Operating_Leverage' (bool).
    """
    try:
        fin = ticker.financials
        if fin.empty or len(fin.columns) < 3 or "Total Revenue" not in fin.index:
            return {"Margin_Trend": False, "Operating_Leverage": False}

        # 1. Margin Trend (3 Years)
        # Margins = Operating Income / Total Revenue
        if "Operating Income" in fin.index:
            op_inc = fin.loc["Operating Income"]
        elif "EBIT" in fin.index:
            op_inc = fin.loc["EBIT"]
        else:
            return {"Margin_Trend": False, "Operating_Leverage": False}

        rev = fin.loc["Total Revenue"]

        m_curr = _safe_div(op_inc.iloc[0], rev.iloc[0])
        m_prev = _safe_div(op_inc.iloc[1], rev.iloc[1])
        m_prev2 = _safe_div(op_inc.iloc[2], rev.iloc[2])

        margin_expansion = m_curr > m_prev > m_prev2

        # 2. Operating Leverage (Current Year)
        # Op Income Growth > Sales Growth
        op_growth = _safe_div(op_inc.iloc[0] - op_inc.iloc[1], abs(op_inc.iloc[1]))
        rev_growth = _safe_div(rev.iloc[0] - rev.iloc[1], abs(rev.iloc[1]))

        op_leverage = op_growth > (rev_growth * 1.2)  # 20% faster growth

        return {"Margin_Trend": margin_expansion, "Operating_Leverage": op_leverage}
    except Exception:
        return {"Margin_Trend": False, "Operating_Leverage": False}
