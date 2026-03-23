
import asyncio
import os
from datetime import datetime
import numpy as np
import yfinance as yf
from jinja2 import Environment, FileSystemLoader

from modules.quarterly_results import get_quarterly_timeline
from modules.price_fundamentals import get_price_vs_fundamentals
from modules.shareholding import get_shareholding_pattern
from modules.technicals import get_technical_analysis
from modules.symbol_utils import normalize_symbol

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "web-ui", "reports")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "report_cache")

if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def _safe_float(value, default=0.0):
    try:
        if value is None or isinstance(value, bool): return default
        parsed = float(value)
        if not np.isfinite(parsed): return default
        return parsed
    except: return default

async def generate_premium_html_report(symbol: str):
    """
    Generate a stunning HTML investment report using the premium template and Jinja2.
    """
    symbol = normalize_symbol(symbol)

    output_path = os.path.join(REPORTS_DIR, f"{symbol.split('.')[0]}.html")
    if os.path.exists(output_path):
        mtime = os.path.getmtime(output_path)
        if (datetime.now().timestamp() - mtime) < 300:  # Reduced to 5 minutes
            print(f"Returning cached Premium Report for {symbol}...")
            return output_path

    print(f"Generating Premium Audit Report for {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # Gather data in parallel
    info_task = asyncio.to_thread(lambda: ticker.info)
    quarterly_task = get_quarterly_timeline(symbol, quarters=8)
    valuation_task = get_price_vs_fundamentals(symbol)
    shareholding_task = get_shareholding_pattern(symbol)
    technicals_task = get_technical_analysis(symbol)
    
    info, q_data, v_data, s_data, t_data = await asyncio.gather(
        info_task, quarterly_task, valuation_task, shareholding_task, technicals_task
    )
    
    if not info:
        return "Error: Failed to fetch symbol info"

    # Ensure segments are dicts even on failure
    if not isinstance(q_data, dict): q_data = {}
    if not isinstance(v_data, dict): v_data = {}
    if not isinstance(s_data, dict): s_data = {}
    if not isinstance(t_data, dict): t_data = {}

    # --- V7.1 FUNDAMENTALS & ANALYST OVERRIDE ---
    from modules.estimates import get_estimate_data
    est_data = get_estimate_data(symbol)
    f_override = {}
    manual_target = None
    manual_rec = None
    if est_data and est_data.get("source") == "manual_seed":
        seed = est_data.get("estimates", {})
        f_override = seed.get("fundamentals_override", {})
        manual_target = seed.get("target_high") or seed.get("target_median")
        manual_rec = seed.get("consensus")

    price = _safe_float(info.get("currentPrice", info.get("regularMarketPrice", 1)))
    sector = info.get("sector", "N/A")
    industry = info.get("industry", "N/A")
    is_finance = any(x in (sector + industry).lower() for x in ["bank", "finance", "financial", "nbfc"])

    # --- 1. Base Info ---
    context = {
        "current_date": datetime.now().strftime("%b %d, %Y"),
        "name": info.get("longName", symbol.split(".")[0]),
        "valuation": {
            "symbol": symbol,
            "intrinsic_value": "N/A",
            "margin_of_safety": "0.0",
            "verdict": "NEUTRAL"
        },
        "sector": sector,
        "industry": industry,
        "current_price": f"{price:,.2f}",
        "momentum_50d_pct": f"{_safe_float(info.get('fiftyDayAverageChangePercent'))*100:.2f}",
        "market_cap_cr": f"{f_override.get('Market_Cap_Cr'):,.0f}" if "Market_Cap_Cr" in f_override else f"{_safe_float(info.get('marketCap'))/10000000:,.0f}",
        "pe_ratio": f"{_safe_float(info.get('trailingPE')):,.2f}",
        "range_low": f"{_safe_float(info.get('fiftyTwoWeekLow')):,.2f}",
        "range_high": f"{_safe_float(info.get('fiftyTwoWeekHigh')):,.2f}",
    }

    # --- 2. Checklist ---
    checklist_items = []
    
    # C1: ROE
    roe = _safe_float(f_override.get("ROE%")) / 100 if "ROE%" in f_override else _safe_float(info.get("returnOnEquity"))
    c1_pass = roe > 0.15
    checklist_items.append({
        "criterion": "Return on Equity (ROE)",
        "threshold": "> 15%",
        "actual": f"{roe*100:.1f}%",
        "status": "PASS" if c1_pass else "FAIL"
    })
    
    # C2: Debt/Equity
    de = _safe_float(f_override.get("Debt_Equity")) if "Debt_Equity" in f_override else _safe_float(info.get("debtToEquity"))
    if is_finance:
        c2_pass = True 
        de_str = "N/A (Bank)"
    else:
        de_val = de / 100 if de > 2 else de 
        c2_pass = de_val < 1.0
        de_str = f"{de_val:.2f}"
    checklist_items.append({
        "criterion": "Debt to Equity",
        "threshold": "< 1.0",
        "actual": de_str,
        "status": "PASS" if c2_pass else "FAIL"
    })
    
    # C3: Sales Growth
    rev_growth = _safe_float(f_override.get("Sales_Growth_TTM%")) / 100 if "Sales_Growth_TTM%" in f_override else _safe_float(info.get("revenueGrowth"))
    if "Sales_Growth_5Y%" in f_override and rev_growth == 0:
        rev_growth = _safe_float(f_override.get("Sales_Growth_5Y%")) / 100
    c3_pass = rev_growth > 0.10
    checklist_items.append({
        "criterion": "Sales Growth (YoY)",
        "threshold": "> 10%",
        "actual": f"{rev_growth*100:.1f}%",
        "status": "PASS" if c3_pass else "FAIL"
    })
    
    # C4: Profit Growth
    profit_growth = _safe_float(f_override.get("EPS_Growth%")) / 100 if "EPS_Growth%" in f_override else _safe_float(info.get("earningsGrowth"))
    c4_pass = profit_growth > 0.15
    checklist_items.append({
        "criterion": "Profit Growth (YoY)",
        "threshold": "> 15%",
        "actual": f"{profit_growth*100:.1f}%",
        "status": "PASS" if c4_pass else "FAIL"
    })
    
    # C5: Promoter Holding
    promoter = _safe_float(s_data.get("pattern", {}).get("promoters", 0))
    c5_pass = promoter > 40
    checklist_items.append({
        "criterion": "Promoter Holding",
        "threshold": "> 40%",
        "actual": f"{promoter:.1f}%",
        "status": "PASS" if c5_pass else "FAIL"
    })
    
    context["checklist"] = checklist_items

    # --- 3. Quarterly Results ---
    quarters = q_data.get("quarters", [])
    q_list = []
    for i, q in enumerate(quarters):
        rev_g = _safe_float(q.get("revenue_growth_qoq"))
        q_list.append({
            "period": q.get("quarter", "N/A"),
            "is_latest": i == len(quarters) - 1,
            "revenue": f"{_safe_float(q.get('revenue')):,.0f}",
            "profit": f"{_safe_float(q.get('profit')):,.0f}",
            "growth": round(rev_g, 1) if rev_g != 0 else None
        })
    context["quarterly_results"] = q_list

    # --- 4. Valuation & Analyst ---
    eps = _safe_float(info.get("trailingEps"))
    bv = _safe_float(info.get("bookValue"))
    graham = round(((22.5 * eps * bv)**0.5), 2) if eps > 0 and bv > 0 else 0
    mos = round(((graham - price) / graham) * 100, 1) if graham > price else 0
    
    rec = str(manual_rec).upper() if manual_rec else str(info.get("recommendationKey", "HOLD")).replace("_", " ").upper()
    target = _safe_float(manual_target) if manual_target else _safe_float(info.get("targetMeanPrice"))
    upside = round(((target - price) / price) * 100, 1) if target > price else 0

    context["valuation"]["intrinsic_value"] = f"{graham:,.2f}"
    context["valuation"]["margin_of_safety"] = str(mos)
    context["valuation"]["verdict"] = "STRONG BUY" if rec in ["BUY", "STRONG BUY"] and mos > 20 else "NEUTRAL"
    if mos < 0: context["valuation"]["verdict"] = "OVERVALUED"

    context["analyst_target"] = f"{target:,.2f}"
    context["analyst_upside"] = str(upside)
    context["pb_ratio"] = f"{_safe_float(info.get('priceToBook')):,.2f}"
    context["valuation_extras_html"] = "" # Extend here if needed

    # --- 5. Shareholding & Governance ---
    inst_h = _safe_float(s_data.get("pattern", {}).get("institutions", 0))
    context["shareholding"] = {
        "promoter": f"{promoter:.2f}",
        "institution": f"{inst_h:.2f}",
        "public": f"{_safe_float(s_data.get('pattern', {}).get('public', 0)):.2f}"
    }

    short_int = _safe_float(info.get("shortPercentOfFloat", 0)) * 100
    context["governance"] = {
        "overall_risk": info.get("overallRisk", "N/A"),
        "audit_risk": info.get("auditRisk", "N/A"),
        "board_risk": info.get("boardRisk", "N/A"),
        "shareholder_rights": info.get("shareHolderRightsRisk", "N/A"),
        "short_interest": f"{short_int:.2f}%" if short_int > 0 else "N/A",
        "has_red_flags": any(info.get(r, 0) and info.get(r, 0) > 7 for r in ["overallRisk", "auditRisk", "boardRisk", "shareHolderRightsRisk"]) or short_int > 5
    }

    raw_yield = _safe_float(info.get('dividendYield'))
    div_yield_pct = raw_yield * 100 if 0 < raw_yield < 1 else raw_yield
    
    # --- 6. Dividend ---
    context["dividend"] = {
        "yield": f"{div_yield_pct:.2f}",
        "latest": f"{_safe_float(info.get('lastDividendValue')):,.2f}",
        "ex_date": "N/A", # Yahoo often hides this in complex structures, placeholder for now
        "record_date": "N/A"
    }
    
    # --- 7. Execution Quality ---
    mcap_cr = _safe_float(f_override.get("Market_Cap_Cr")) if "Market_Cap_Cr" in f_override else _safe_float(info.get("marketCap")) / 10000000
    model_bps = 200
    if mcap_cr > 50000: model_bps = 20
    elif mcap_cr > 15000: model_bps = 50
    elif mcap_cr > 5000: model_bps = 100
    
    context["exec_model_slip"] = str(model_bps)
    context["exec_real_slip"] = str(model_bps) # Default to model for now

    # --- 8. Targets ---
    context["targets"] = {
        "conservative": f"{price * 1.10:,.2f}",
        "bull": f"{price * 1.30:,.2f}"
    }
    
    context["entry_zone"] = {
        "low": f"{price * 0.95:,.2f}",
        "high": f"{price:,.2f}"
    }

    roe_pct = round(roe * 100, 1) if (roe and roe > 0) else 0.0
    consistency = q_data.get("trends", {}).get("consistency", "UNKNOWN")
    context["thesis"] = {
        "title": "Champion in Credit Execution" if is_finance else "Market Leadership in Core Segment",
        "points": [
            f"Dominant footprint within the {industry} space.",
            f"{roe_pct}% Return on Equity, demonstrating strict capital efficiency.",
            "Consistent quarterly execution metrics." if consistency == "HIGH" else "Volatile but recovering quarterly execution."
        ]
    }
    context["stop_loss"] = f"{price * 0.85:,.2f}"

    # Render Template
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("audit_report.html")
    html_output = template.render(context)

    output_path = os.path.join(REPORTS_DIR, f"{symbol.split('.')[0]}.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_output)
    
    print(f"Report generated: {output_path}")
    return output_path

if __name__ == "__main__":
    import asyncio
    asyncio.run(generate_premium_html_report("PFC.NS"))
