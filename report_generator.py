import asyncio
import hashlib
import os
import re
import tempfile
from datetime import datetime

import yfinance as yf
import sys
import socket
socket.setdefaulttimeout(20.0)

from modules.retry_utils import run_with_exponential_backoff


CACHE_DIR = "reports_cache"
CACHE_TTL_DAYS = 7
REPORT_SCHEMA_VERSION = "v2"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _cache_key(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    safe_symbol = re.sub(r"[^A-Z0-9._-]", "_", normalized) or "UNKNOWN"
    key_material = f"{REPORT_SCHEMA_VERSION}|{normalized}"
    key_hash = hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:12]
    return f"{safe_symbol}_{REPORT_SCHEMA_VERSION}_{key_hash}"


def _cache_path(symbol: str) -> str:
    return os.path.join(CACHE_DIR, f"{_cache_key(symbol)}.md")


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _signature_path(cache_path: str) -> str:
    return f"{cache_path}.sha256"


def _safe_float(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float(value, default=0.0):
    parsed = _safe_float(value)
    if parsed is None:
        return default
    return parsed


def _normalize_recommendation(raw_value, n_analysts: int) -> str:
    if n_analysts <= 0:
        return "NO_COVERAGE"

    key = str(raw_value or "").strip().lower().replace("_", " ")
    if key in {"", "none", "na", "n/a", "null"}:
        return "NO_COVERAGE"

    mapping = {
        "strong buy": "STRONG BUY",
        "buy": "BUY",
        "hold": "HOLD",
        "underperform": "UNDERPERFORM",
        "sell": "SELL",
    }
    return mapping.get(key, key.upper())


def _read_verified_cache(cache_path: str):
    if not os.path.exists(cache_path):
        return None

    sig_path = _signature_path(cache_path)
    if not os.path.exists(sig_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as cache_file:
            payload = cache_file.read()
        with open(sig_path, "r", encoding="utf-8") as sig_file:
            expected_sig = sig_file.read().strip()
    except OSError:
        return None

    current_sig = _sha256_text(payload)
    if current_sig != expected_sig:
        print(f"Cache signature mismatch for {cache_path}. Recomputing report.")
        return None

    return payload


def _atomic_write_text(path: str, content: str):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=os.path.dirname(path) or ".",
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _write_signed_cache(cache_path: str, report: str):
    _ensure_cache_dir()
    _atomic_write_text(cache_path, report)
    _atomic_write_text(_signature_path(cache_path), _sha256_text(report))


async def generate_analyst_report(symbol):
    symbol = _normalize_symbol(symbol)
    if not symbol:
        return "Error: Invalid symbol"

    _ensure_cache_dir()
    cache_path = _cache_path(symbol)

    # Cache check with integrity verification
    if os.path.exists(cache_path):
        try:
            mtime = os.path.getmtime(cache_path)
            age_days = (datetime.now().timestamp() - mtime) / (24 * 3600)
            if age_days < CACHE_TTL_DAYS:
                cached_report = _read_verified_cache(cache_path)
                if cached_report is not None:
                    return cached_report
        except Exception as exc:
            print(f"Cache read error for {symbol}: {exc}")

    try:
        ticker = yf.Ticker(symbol)
        info = await run_with_exponential_backoff(
            lambda: asyncio.to_thread(lambda: ticker.info),
            context=f"yfinance report info for {symbol}",
        )

        if not info:
            return f"Error: Failed to fetch data for {symbol}"

        # V7.1 Fundamentals Override
        from modules.estimates import get_estimate_data
        est_data = get_estimate_data(symbol)
        f_override = {}
        manual_target = None
        manual_rec = None
        manual_analysts = 0
        if est_data and est_data.get("source") == "manual_seed":
            seed = est_data.get("estimates", {})
            f_override = seed.get("fundamentals_override", {})
            manual_target = seed.get("target_high") or seed.get("target_median")
            manual_rec = seed.get("consensus")
            manual_analysts = seed.get("analyst_count", 0)

        name = info.get("longName", symbol)
        current_price = _to_float(info.get("currentPrice"), 0.0)
        if current_price <= 0:
            current_price = _to_float(info.get("regularMarketPrice"), 0.0)

        market_cap = _to_float(info.get("marketCap"), 0.0)
        market_cap_crore = _to_float(f_override.get("Market_Cap_Cr"), market_cap / 10000000 if market_cap else 0)

        pe = _to_float(info.get("trailingPE"), 0.0)
        if "PE_Ratio" in f_override:
            pe = _to_float(f_override.get("PE_Ratio"), pe)
        
        # Enhanced ROE Fetch
        roe = _to_float(info.get("returnOnEquity"), None)
        if roe is None:
            # Fallback 1: Calculate ROE using book value and shares outstanding
            book_val = _to_float(info.get("bookValue"), None)
            shares = _to_float(info.get("sharesOutstanding"), None)
            net_income = _to_float(info.get("netIncomeToCommon"), None)
            if book_val and shares and net_income:
                equity = book_val * shares
                if equity > 0:
                    roe = net_income / equity
        
        if roe is None:
            # Fallback 2: Search statements
            try:
                bs = await asyncio.to_thread(lambda: ticker.balance_sheet)
                q_bs = await asyncio.to_thread(lambda: ticker.quarterly_balance_sheet)
                net_inc = _to_float(info.get("netIncomeToCommon"), 0)
                
                equity = None
                # Check multiple labels for equity
                labels = ['Stockholders Equity', 'Total Equity Gross Minority Interest', 'Common Stock Equity']
                
                # Try annual first
                for l in labels:
                    if l in bs.index:
                        equity = bs.loc[l].iloc[0]
                        break
                
                if not equity:
                    # Try quarterly
                    for l in labels:
                        if l in q_bs.index:
                            equity = q_bs.loc[l].iloc[0]
                            break
                
                if equity and equity > 0:
                    roe = net_inc / equity
            except:
                roe = 0
        
        roe = (roe * 100) if roe else 0
        if "ROE%" in f_override:
            roe = _to_float(f_override.get("ROE%"), roe)

        # Debt to Equity
        debt_equity = _to_float(info.get("debtToEquity"), None)
        if debt_equity is None:
            try:
                bs = await asyncio.to_thread(lambda: ticker.balance_sheet)
                total_debt = None
                for l in ['Total Debt', 'Net Debt']:
                    if l in bs.index:
                        total_debt = bs.loc[l].iloc[0]
                        break
                
                # We need equity again
                book_val = _to_float(info.get("bookValue"), None)
                shares = _to_float(info.get("sharesOutstanding"), None)
                equity = (book_val * shares) if (book_val and shares) else None
                
                if total_debt is not None and equity:
                    debt_equity = total_debt / equity
            except:
                debt_equity = 0
        
        if debt_equity and debt_equity > 10:
            # yfinance sometimes returns percentages (e.g. 150 instead of 1.5)
            sector = str(info.get("sector", ""))
            is_finance = "Financial" in sector or "Credit" in sector or "Bank" in sector
            if not is_finance:
                debt_equity /= 100
                
        if "Debt_Equity" in f_override:
            debt_equity = _to_float(f_override.get("Debt_Equity"), debt_equity)

        # Enhanced CFO Fetch
        cfo = _to_float(info.get("operatingCashflow"), None)
        if cfo is None:
            try:
                cf_stmt = await asyncio.to_thread(lambda: ticker.cashflow)
                if not cf_stmt.empty and 'Operating Cash Flow' in cf_stmt.index:
                    cfo = cf_stmt.loc['Operating Cash Flow'].iloc[0]
                else:
                    q_cf = await asyncio.to_thread(lambda: ticker.quarterly_cashflow)
                    if not q_cf.empty and 'Operating Cash Flow' in q_cf.index:
                        cfo = q_cf.loc['Operating Cash Flow'].iloc[0]
            except:
                cfo = 0
        
        pat = _to_float(info.get("netIncomeToCommon"), 0.0)
        
        # Determine CFO/PAT ratio (deterministic status-friendly representation)
        cfo_pat_ratio = None
        if cfo is not None and pat > 0:
            cfo_pat_ratio = cfo / pat
            cfo_pat_display = f"{cfo_pat_ratio:.2f}"
        elif cfo is not None and cfo > 0 and pat <= 0:
            cfo_pat_display = "N/A (PAT<=0)"
        else:
            cfo_pat_display = "N/A"


        high_52 = _to_float(info.get("fiftyTwoWeekHigh"), current_price) or current_price
        down_pct = round(((high_52 - current_price) / high_52) * 100, 2) if high_52 else 0

        def pass_pill(text="PASS"):
            return f'<span class="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] font-black tracking-widest uppercase shadow-[0_0_10px_rgba(16,185,129,0.2)]">{text}</span>'
            
        def fail_pill(text):
            return f'<span class="px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[10px] font-black tracking-widest uppercase">{text}</span>'
            
        def caution_pill(text):
            return f'<span class="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px] font-black tracking-widest uppercase">{text}</span>'

        check_mcap = pass_pill("PASS") if market_cap_crore > 1000 else fail_pill("FAIL")
        check_roe = pass_pill("PASS") if (roe and roe > 15) else fail_pill("FAIL")
        roe_display = f"{round(roe, 2)}%" if roe else "N/A"

        sector = str(info.get("sector", ""))
        is_finance = "Financial" in sector or "Bank" in sector
        if is_finance:
            de_display_text = "N/A (Bank)"
            check_de = pass_pill("PASS")
        else:
            de_display = round(debt_equity, 2) if debt_equity is not None else None
            de_display_text = f"{de_display:.2f}" if de_display is not None else "N/A"
            check_de = pass_pill("PASS") if (de_display is not None and de_display < 0.5) else fail_pill("FAIL")

        if cfo_pat_ratio is None:
            check_cfo = caution_pill("REVIEW")
        else:
            check_cfo = pass_pill("PASS") if cfo_pat_ratio >= 1 else fail_pill("FAIL")

        pe_display = f"{round(pe, 2)}" if pe and pe > 0 else "N/A"
        if pe and pe > 0:
            check_pe = pass_pill("PASS") if pe < 25 else fail_pill("FAIL")
        else:
            check_pe = caution_pill("REVIEW")

        check_mom = pass_pill("PASS") if down_pct < 25 else fail_pill("FAIL")

        n_analysts = int(_to_float(info.get("numberOfAnalystOpinions"), 0.0))
        rec_key_raw = info.get("recommendationKey", "none")
        target_mean = _safe_float(info.get("targetMeanPrice"))
        
        if manual_rec:
            rec_key_raw = manual_rec
            n_analysts = int(manual_analysts) if manual_analysts else n_analysts
        if manual_target:
            target_mean = _safe_float(manual_target)

        rec_display = _normalize_recommendation(rec_key_raw, n_analysts)
        has_target = target_mean is not None and target_mean > 0 and current_price > 0
        target_mean_display = f"{target_mean:,.2f}" if has_target else "N/A"
        upside_display = (
            f"{round(((target_mean - current_price) / current_price) * 100, 2)}%"
            if has_target
            else "N/A"
        )
        profit_margins_ratio = _to_float(info.get("profitMargins"), 0.0)
        quick_ratio = _safe_float(info.get("quickRatio"))
        current_ratio = _safe_float(info.get("currentRatio"))

        date_str = datetime.now().strftime("%d-%b-%Y")

        # Extract Growth Metrics
        revenue_growth = _to_float(info.get("revenueGrowth"), None)
        if "Sales_Growth_TTM%" in f_override:
             revenue_growth = _to_float(f_override.get("Sales_Growth_TTM%"), 0.0) / 100
        elif "Sales_Growth_5Y%" in f_override and revenue_growth is None:
             revenue_growth = _to_float(f_override.get("Sales_Growth_5Y%"), 0.0) / 100
             
        if revenue_growth is not None:
             revenue_growth_pct = round(revenue_growth * 100, 1)
             check_sales = pass_pill("PASS") if revenue_growth_pct > 10 else fail_pill("FAIL")
             revenue_disp = f"{revenue_growth_pct}%"
        else:
             check_sales = caution_pill("REVIEW")
             revenue_disp = "N/A"
             
        earnings_growth = _to_float(info.get("earningsGrowth"), None)
        if "EPS_Growth%" in f_override:
             earnings_growth = _to_float(f_override.get("EPS_Growth%"), 0.0) / 100
             
        if earnings_growth is not None:
             earnings_growth_pct = round(earnings_growth * 100, 1)
             check_eps = pass_pill("PASS") if earnings_growth_pct > 0 else fail_pill("FAIL")
             eps_disp = f"{earnings_growth_pct}%"
        else:
             check_eps = caution_pill("REVIEW")
             eps_disp = "N/A"

        report = f"""# {name} ({symbol}) - Investment Report
**Date:** {date_str} | **Price:** {current_price:,.2f} | **M.Cap:** {round(market_cap_crore):,} Cr

## 1. 8-Point Checklist
| Criterion | Threshold | Actual | Status |
| :--- | :--- | :--- | :--- |
| **Market Cap** | > 1,000 Cr | {round(market_cap_crore)} Cr | {check_mcap} |
| **Valuation (PE)** | < 25 | {pe_display} | {check_pe} |
| **Efficiency (ROE)** | > 15% | {roe_display} | {check_roe} |
| **Debt / Equity** | < 0.5 | {de_display_text} | {check_de} |
| **Cash Quality** | CFO > PAT | {cfo_pat_display} | {check_cfo} |
| **Momentum** | < 25% Drop | -{down_pct}% | {check_mom} |
| **Sales Growth** | > 10% | {revenue_disp} | {check_sales} |
| **EPS Growth** | > 0% | {eps_disp} | {check_eps} |

## 2. Analyst Consensus
**Recommendation:** {rec_display} (Based on {n_analysts} Analysts)

| Metric | Value |
| :--- | :--- |
| **Target Price (Avg)** | {target_mean_display} |
| **Upside Potential** | {upside_display} |
| **Number of Analysts**| {n_analysts} |

## 3. Financial Health Snapshot
| Metric | Value | Comment |
| :--- | :--- | :--- |
| **Profit Margin** | {round(profit_margins_ratio * 100, 1) if profit_margins_ratio else 0}% | {'Healthy' if profit_margins_ratio > 0.1 else 'Low'} |
| **Quick Ratio** | {round(quick_ratio, 2) if quick_ratio is not None else 'N/A'} | Liquid Assets vs Liabilities |
| **Current Ratio** | {round(current_ratio, 2) if current_ratio is not None else 'N/A'} | Short term solvency |

## 4. Shareholding Pattern
| Holder Category | % Holding |
| :--- | :--- |
| **Insiders/Promoters** | {round(info.get('heldPercentInsiders', 0) * 100, 2) if info.get('heldPercentInsiders') else 0}% |
| **Institutions** | {round(info.get('heldPercentInstitutions', 0) * 100, 2) if info.get('heldPercentInstitutions') else 0}% |
| **Public/Others** | {round(100 - ((info.get('heldPercentInsiders', 0) or 0) + (info.get('heldPercentInstitutions', 0) or 0)) * 100, 2)}% |

## 5. Red Flags & Governance
| Risk Category | Score (1=Low, 10=High) | Status |
| :--- | :--- | :--- |
| **Overall ISS Risk** | {info.get('overallRisk', 'N/A')} | {fail_pill(' RED FLAG') if info.get('overallRisk', 0) and info.get('overallRisk', 0) > 7 else pass_pill(' OK')} |
| **Audit Risk** | {info.get('auditRisk', 'N/A')} | {fail_pill(' RED FLAG') if info.get('auditRisk', 0) and info.get('auditRisk', 0) > 7 else pass_pill(' OK')} |
| **Board Risk** | {info.get('boardRisk', 'N/A')} | {fail_pill(' RED FLAG') if info.get('boardRisk', 0) and info.get('boardRisk', 0) > 7 else pass_pill(' OK')} |
| **Shareholder Rights** | {info.get('shareHolderRightsRisk', 'N/A')} | {fail_pill(' RED FLAG') if info.get('shareHolderRightsRisk', 0) and info.get('shareHolderRightsRisk', 0) > 7 else pass_pill(' OK')} |
| **Short Interest Float** | {round(info.get('shortPercentOfFloat', 0) * 100, 2) if info.get('shortPercentOfFloat') else 'N/A'}% | {fail_pill(' HIGH') if info.get('shortPercentOfFloat', 0) and info.get('shortPercentOfFloat', 0) > 0.05 else pass_pill(' OK')} |

---
*Auto-generated quantitative report. Not financial advice.*
"""
        _write_signed_cache(cache_path, report)
        return report
    except Exception as exc:
        return f"Error generating report: {str(exc)}"


if __name__ == "__main__":
    print(asyncio.run(generate_analyst_report("RELIANCE.NS")))
