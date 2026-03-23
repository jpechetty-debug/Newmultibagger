"""
Quarterly Results Timeline Module
Analyzes quarterly financial performance trends over time.
"""

import pandas as pd
import yfinance as yf
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import numpy as np
from modules.retry_utils import run_with_exponential_backoff

def _safe_float(value) -> Optional[float]:
    """Return finite float or None."""
    try:
        if value is None: return None
        parsed = float(value)
        if not np.isfinite(parsed): return None
        return parsed
    except: return None

async def get_quarterly_timeline(symbol: str, quarters: int = 12) -> Dict:
    """
    Get quarterly financial results for the last N quarters with resilience.
    """
    try:
        async def _load_quarterly_payload():
            ticker = await asyncio.to_thread(yf.Ticker, symbol)
            info_task = asyncio.to_thread(lambda: ticker.info)
            income_task = asyncio.to_thread(lambda: ticker.quarterly_income_stmt)
            balance_task = asyncio.to_thread(lambda: ticker.quarterly_balance_sheet)
            cashflow_task = asyncio.to_thread(lambda: ticker.quarterly_cashflow)
            return await asyncio.gather(
                info_task, income_task, balance_task, cashflow_task
            )

        info, quarterly_income, quarterly_balance, quarterly_cashflow = (
            await run_with_exponential_backoff(
                _load_quarterly_payload,
                context=f"yfinance quarterly timeline for {symbol}",
            )
        )

        if quarterly_income.empty:
            return {
                'symbol': symbol,
                'company_name': info.get('longName', symbol.replace('.NS', '')),
                'quarters': [],
                'trends': {},
                'alerts': [{
                    'type': 'ERROR',
                    'message': 'No quarterly data available',
                    'severity': 'HIGH'
                }],
                'timestamp': datetime.now().isoformat()
            }

        # Process quarterly data
        results = []
        num_quarters = min(quarters, len(quarterly_income.columns))

        for i in range(num_quarters):
            col = quarterly_income.columns[i]
            quarter_data = await process_quarter_data(
                col,
                quarterly_income,
                quarterly_balance,
                quarterly_cashflow,
                info
            )
            if quarter_data:
                results.append(quarter_data)

        # Reverse to show chronological order (oldest first)
        results = results[::-1]

        # Calculate growth rates (QoQ and YoY)
        results = calculate_growth_rates(results)

        # Analyze trends
        trends = analyze_quarterly_trends(results)

        # Generate alerts
        alerts = generate_quarterly_alerts(results, trends)

        return {
            'symbol': symbol,
            'company_name': info.get('longName', symbol.replace('.NS', '')),
            'quarters': results,
            'trends': trends,
            'alerts': alerts,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        print(f"Error fetching quarterly timeline for {symbol}: {str(e)}")
        return {
            'symbol': symbol,
            'quarters': [],
            'trends': {},
            'alerts': [{
                'type': 'ERROR',
                'message': f'Failed to fetch data: {str(e)}',
                'severity': 'HIGH'
            }],
            'timestamp': datetime.now().isoformat()
        }

async def process_quarter_data(
    quarter_date,
    income_stmt: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    cashflow: pd.DataFrame,
    company_info: Dict
) -> Optional[Dict]:
    """Process data for a single quarter."""
    try:
        # Extract revenue
        revenue = 0.0
        revenue_labels = [
            'Total Revenue', 'Operating Revenue', 'Revenue', 
            'Interest Income', 'Net Interest Income', 'Total Expenses'
        ]
        for label in revenue_labels:
            if label in income_stmt.index:
                val = _safe_float(income_stmt.loc[label, quarter_date])
                if val is not None and val != 0:
                    revenue = val
                    break

        if revenue == 0 and 'Interest Income' in income_stmt.index:
            val = _safe_float(income_stmt.loc['Interest Income', quarter_date])
            if val is not None: revenue = val

        # Extract profit
        profit = 0.0
        profit_labels = ['Net Income', 'Net Income Common Stockholders', 'Net Income From Continuing Operations']
        for label in profit_labels:
            if label in income_stmt.index:
                val = _safe_float(income_stmt.loc[label, quarter_date])
                if val is not None and val != 0:
                    profit = val
                    break
        
        # Extract EBITDA
        ebitda = 0.0
        ebitda_labels = ['EBITDA', 'Normalized EBITDA', 'Operating Profit']
        for label in ebitda_labels:
            if label in income_stmt.index:
                val = _safe_float(income_stmt.loc[label, quarter_date])
                if val is not None and val != 0:
                    ebitda = val
                    break

        # Convert to Crores
        revenue_cr = revenue / 10000000
        profit_cr = profit / 10000000
        ebitda_cr = ebitda / 10000000
        
        # Calculate margins
        margin = (profit / revenue * 100) if revenue > 0 else 0
        ebitda_margin = (ebitda / revenue * 100) if revenue > 0 else 0
        
        # Get EPS
        eps = 0.0
        if not balance_sheet.empty:
            try:
                shares = _safe_float(balance_sheet.loc['Ordinary Shares Number', quarter_date]) if 'Ordinary Shares Number' in balance_sheet.index else None
                if shares and shares > 0:
                    eps = profit / shares
            except:
                pass
        
        # Get Book Value per Share
        book_value_per_share = None
        if not balance_sheet.empty:
            try:
                equity = _safe_float(balance_sheet.loc['Stockholders Equity', quarter_date]) if 'Stockholders Equity' in balance_sheet.index else 0
                shares = _safe_float(balance_sheet.loc['Ordinary Shares Number', quarter_date]) if 'Ordinary Shares Number' in balance_sheet.index else 1
                if shares > 0:
                    book_value_per_share = equity / shares
            except:
                pass
        
        # Format quarter label
        quarter_label = format_quarter_label(quarter_date)
        
        return {
            'quarter': quarter_label,
            'date': quarter_date.strftime('%Y-%m-%d'),
            'revenue': round(revenue_cr, 0),
            'profit': round(profit_cr, 0),
            'ebitda': round(ebitda_cr, 0),
            'margin': round(margin, 1),
            'ebitda_margin': round(ebitda_margin, 1),
            'eps': round(eps, 2) if eps else None,
            'book_value': round(book_value_per_share, 2) if book_value_per_share else None,
            'revenue_growth_qoq': None,
            'profit_growth_qoq': None,
            'revenue_growth_yoy': None,
            'profit_growth_yoy': None
        }
        
    except Exception as e:
        print(f"Error processing quarter {quarter_date}: {str(e)}")
        return None

def format_quarter_label(date) -> str:
    """Format datetime to quarter label (Indian FY)."""
    month = date.month
    year = date.year
    if month in [4, 5, 6]:
        quarter, fy_year = 'Q1', year + 1
    elif month in [7, 8, 9]:
        quarter, fy_year = 'Q2', year + 1
    elif month in [10, 11, 12]:
        quarter, fy_year = 'Q3', year + 1
    else:
        quarter, fy_year = 'Q4', year
    return f"{quarter} FY{str(fy_year)[2:]}"

def calculate_growth_rates(quarters: List[Dict]) -> List[Dict]:
    """Calculate QoQ and YoY growth rates."""
    if len(quarters) < 2:
        return quarters
    for i in range(len(quarters)):
        if i > 0:
            prev, curr = quarters[i-1], quarters[i]
            if prev['revenue'] > 0:
                curr['revenue_growth_qoq'] = round((curr['revenue'] - prev['revenue']) / prev['revenue'] * 100, 1)
            if prev['profit'] > 0:
                curr['profit_growth_qoq'] = round((curr['profit'] - prev['profit']) / prev['profit'] * 100, 1)
            elif prev['profit'] <= 0 and curr['profit'] > 0:
                curr['profit_growth_qoq'] = 999.9
        if i >= 4:
            prev_year, curr = quarters[i-4], quarters[i]
            if prev_year['revenue'] > 0:
                curr['revenue_growth_yoy'] = round((curr['revenue'] - prev_year['revenue']) / prev_year['revenue'] * 100, 1)
            if prev_year['profit'] > 0:
                curr['profit_growth_yoy'] = round((curr['profit'] - prev_year['profit']) / prev_year['profit'] * 100, 1)
            elif prev_year['profit'] <= 0 and curr['profit'] > 0:
                curr['profit_growth_yoy'] = 999.9
    return quarters

def analyze_quarterly_trends(quarters: List[Dict]) -> Dict:
    """Analyze trends across quarters."""
    if len(quarters) < 3:
        return {
            'revenue_trend': 'INSUFFICIENT_DATA',
            'profit_trend': 'INSUFFICIENT_DATA',
            'margin_trend': 'INSUFFICIENT_DATA',
            'consistency': 'UNKNOWN'
        }
    
    recent = quarters[-4:]
    revenue_growth = [q['revenue_growth_qoq'] for q in recent if q.get('revenue_growth_qoq') is not None]
    avg_revenue_growth = sum(revenue_growth) / len(revenue_growth) if revenue_growth else 0
    revenue_trend = 'GROWING' if avg_revenue_growth > 5 else ('DECLINING' if avg_revenue_growth < -5 else 'FLAT')
    
    profit_growth = [q['profit_growth_qoq'] for q in recent if q.get('profit_growth_qoq') is not None and q['profit_growth_qoq'] < 900]
    avg_profit_growth = sum(profit_growth) / len(profit_growth) if profit_growth else 0
    profit_trend = 'GROWING' if avg_profit_growth > 5 else ('DECLINING' if avg_profit_growth < -5 else 'FLAT')
    
    margins = [q['margin'] for q in recent]
    margin_change = margins[-1] - margins[0] if len(margins) >= 2 else 0
    margin_trend = 'EXPANDING' if margin_change > 2 else ('CONTRACTING' if margin_change < -2 else 'STABLE')
    avg_margin = sum(margins) / len(margins) if margins else 0
    
    quarters_with_growth = sum(1 for q in quarters if q.get('revenue_growth_qoq') and q['revenue_growth_qoq'] > 0)
    total_data = sum(1 for q in quarters if q.get('revenue_growth_qoq') is not None)
    consistency = 'HIGH' if (quarters_with_growth / total_data if total_data else 0) >= 0.75 else ('MEDIUM' if (quarters_with_growth / total_data if total_data else 0) >= 0.5 else 'LOW')
    
    return {
        'revenue_trend': revenue_trend,
        'profit_trend': profit_trend,
        'margin_trend': margin_trend,
        'consistency': consistency,
        'avg_revenue_growth': round(avg_revenue_growth, 1),
        'avg_profit_growth': round(avg_profit_growth, 1),
        'avg_margin': round(avg_margin, 1),
        'quarters_with_growth': quarters_with_growth,
        'total_quarters': total_data
    }

def generate_quarterly_alerts(quarters: List[Dict], trends: Dict) -> List[Dict]:
    """Generate alerts based on trends."""
    alerts = []
    if len(quarters) < 2: return alerts
    recent, latest = quarters[-4:], quarters[-1]
    
    revenue_declines = sum(1 for q in recent[-3:] if q.get('revenue_growth_qoq') and q['revenue_growth_qoq'] < 0)
    if revenue_declines >= 2:
        alerts.append({'type': 'WARNING', 'message': f'Revenue declining for {revenue_declines} consecutive quarters', 'severity': 'HIGH'})
    
    if len(recent) >= 2:
        margin_change = latest['margin'] - recent[-2]['margin']
        if margin_change < -3:
            alerts.append({'type': 'WARNING', 'message': f'Margin compressed by {abs(margin_change):.1f}% in latest quarter', 'severity': 'MEDIUM'})
    
    if (latest.get('revenue_growth_qoq', 0) > 0 and latest.get('profit_growth_qoq', 0) < -5):
        alerts.append({'type': 'WARNING', 'message': 'Profit declining despite revenue growth - margin pressure', 'severity': 'HIGH'})
        
    if trends['consistency'] == 'HIGH' and trends['avg_revenue_growth'] > 10:
        alerts.append({'type': 'POSITIVE', 'message': f'Strong consistent growth: {trends["avg_revenue_growth"]}% avg revenue growth', 'severity': 'LOW'})

    if len(recent) >= 3:
        prev_two = recent[-3:-1]
        prev_two_negative = all(
            q.get('profit_growth_qoq') is not None and q['profit_growth_qoq'] < 0
            for q in prev_two
        )
        latest_profit_growth = latest.get('profit_growth_qoq')
        latest_positive = (
            latest_profit_growth is not None
            and latest_profit_growth > 5
            and latest_profit_growth < 900
        )
        if prev_two_negative and latest_positive:
            alerts.append({
                'type': 'POSITIVE',
                'message': 'Turnaround detected - profit growth resumed after 2 quarters',
                'severity': 'LOW'
            })

    if len(recent) >= 2:
        latest_ebitda_margin = latest.get('ebitda_margin')
        prev_ebitda_margin = recent[-2].get('ebitda_margin')
        if latest_ebitda_margin is not None and prev_ebitda_margin is not None:
            ebitda_change = latest_ebitda_margin - prev_ebitda_margin
            if ebitda_change > 3:
                alerts.append({
                    'type': 'POSITIVE',
                    'message': f'EBITDA margin expanded by {ebitda_change:.1f}% - operational efficiency improving',
                    'severity': 'LOW'
                })
        
    return alerts

