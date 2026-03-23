 FEATURE 2: QUARTERLY RESULTS TIMELINE
Backend Implementation 
File 1: modules/quarterly_results.py (NEW FILE)
python"""
Quarterly Results Timeline Module
Analyzes quarterly financial performance trends over time.
"""

import pandas as pd
import yfinance as yf
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import numpy as np


async def get_quarterly_timeline(symbol: str, quarters: int = 12) -> Dict:
    """
    Get quarterly financial results for the last N quarters.
    
    Args:
        symbol: Stock symbol (e.g., 'RELIANCE.NS')
        quarters: Number of quarters to fetch (default: 12)
        
    Returns:
        {
            'symbol': 'RELIANCE.NS',
            'company_name': 'Reliance Industries Ltd',
            'quarters': [
                {
                    'quarter': 'Q1 FY24',
                    'date': '2023-06-30',
                    'revenue': 85000,  # in Crores
                    'profit': 12000,
                    'margin': 14.1,
                    'ebitda': 18000,
                    'ebitda_margin': 21.2,
                    'revenue_growth_qoq': 8.2,  # QoQ %
                    'profit_growth_qoq': 12.5,
                    'revenue_growth_yoy': 15.3,  # YoY %
                    'profit_growth_yoy': 18.7,
                    'eps': 18.5,
                    'book_value': 1250.0
                },
                ...
            ],
            'trends': {
                'revenue_trend': 'GROWING',  # GROWING/DECLINING/FLAT
                'profit_trend': 'GROWING',
                'margin_trend': 'EXPANDING',  # EXPANDING/CONTRACTING/STABLE
                'consistency': 'HIGH',  # HIGH/MEDIUM/LOW
                'avg_revenue_growth': 8.5,
                'avg_profit_growth': 12.3,
                'avg_margin': 14.2,
                'quarters_with_growth': 9,
                'total_quarters': 11  # (excluding first quarter which has no comparison)
            },
            'alerts': [
                {
                    'type': 'WARNING',
                    'message': 'Margin compression in last 2 quarters',
                    'severity': 'MEDIUM'
                }
            ],
            'timestamp': '2026-02-14T10:30:00'
        }
    """
    try:
        # Fetch data in background thread
        ticker = await asyncio.to_thread(yf.Ticker, symbol)
        info = await asyncio.to_thread(lambda: ticker.info)
        
        # Get quarterly financials
        quarterly_income = await asyncio.to_thread(lambda: ticker.quarterly_income_stmt)
        quarterly_balance = await asyncio.to_thread(lambda: ticker.quarterly_balance_sheet)
        quarterly_cashflow = await asyncio.to_thread(lambda: ticker.quarterly_cashflow)
        
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
        
        # Get the number of quarters available (up to requested amount)
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
        revenue = 0
        if 'Total Revenue' in income_stmt.index:
            revenue = income_stmt.loc['Total Revenue', quarter_date]
        
        # Extract profit
        profit = 0
        if 'Net Income' in income_stmt.index:
            profit = income_stmt.loc['Net Income', quarter_date]
        
        # Extract EBITDA (Operating Income + Depreciation)
        ebitda = 0
        if 'EBITDA' in income_stmt.index:
            ebitda = income_stmt.loc['EBITDA', quarter_date]
        elif 'Operating Income' in income_stmt.index:
            operating_income = income_stmt.loc['Operating Income', quarter_date]
            depreciation = 0
            if 'Depreciation And Amortization' in cashflow.index:
                depreciation = cashflow.loc['Depreciation And Amortization', quarter_date]
            ebitda = operating_income + abs(depreciation)
        
        # Convert to Crores (assuming data is in local currency)
        # For Indian stocks, yfinance returns data in rupees
        revenue_cr = revenue / 10000000  # 1 Cr = 10 Million
        profit_cr = profit / 10000000
        ebitda_cr = ebitda / 10000000
        
        # Calculate margins
        margin = (profit / revenue * 100) if revenue > 0 else 0
        ebitda_margin = (ebitda / revenue * 100) if revenue > 0 else 0
        
        # Get EPS (if available)
        eps = None
        if not balance_sheet.empty:
            try:
                shares = balance_sheet.loc['Ordinary Shares Number', quarter_date] if 'Ordinary Shares Number' in balance_sheet.index else None
                if shares and shares > 0:
                    eps = profit / shares
            except:
                pass
        
        # Get Book Value per Share
        book_value_per_share = None
        if not balance_sheet.empty:
            try:
                equity = balance_sheet.loc['Stockholders Equity', quarter_date] if 'Stockholders Equity' in balance_sheet.index else 0
                shares = balance_sheet.loc['Ordinary Shares Number', quarter_date] if 'Ordinary Shares Number' in balance_sheet.index else 1
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
            # Growth rates will be calculated later
            'revenue_growth_qoq': None,
            'profit_growth_qoq': None,
            'revenue_growth_yoy': None,
            'profit_growth_yoy': None
        }
        
    except Exception as e:
        print(f"Error processing quarter {quarter_date}: {str(e)}")
        return None


def format_quarter_label(date) -> str:
    """
    Convert datetime to quarter label (e.g., Q1 FY24).
    
    Indian fiscal year runs Apr-Mar:
    Q1: Apr-Jun
    Q2: Jul-Sep
    Q3: Oct-Dec
    Q4: Jan-Mar
    """
    month = date.month
    year = date.year
    
    # Determine quarter based on month
    if month in [4, 5, 6]:
        quarter = 'Q1'
        fy_year = year + 1
    elif month in [7, 8, 9]:
        quarter = 'Q2'
        fy_year = year + 1
    elif month in [10, 11, 12]:
        quarter = 'Q3'
        fy_year = year + 1
    else:  # [1, 2, 3]
        quarter = 'Q4'
        fy_year = year
    
    return f"{quarter} FY{str(fy_year)[2:]}"


def calculate_growth_rates(quarters: List[Dict]) -> List[Dict]:
    """Calculate QoQ and YoY growth rates for all quarters."""
    if len(quarters) < 2:
        return quarters
    
    for i in range(len(quarters)):
        # QoQ Growth (compare with previous quarter)
        if i > 0:
            prev = quarters[i-1]
            curr = quarters[i]
            
            # Revenue QoQ
            if prev['revenue'] > 0:
                curr['revenue_growth_qoq'] = round(
                    (curr['revenue'] - prev['revenue']) / prev['revenue'] * 100, 
                    1
                )
            
            # Profit QoQ
            if prev['profit'] > 0:
                curr['profit_growth_qoq'] = round(
                    (curr['profit'] - prev['profit']) / prev['profit'] * 100, 
                    1
                )
            elif prev['profit'] <= 0 and curr['profit'] > 0:
                # Turnaround from loss to profit
                curr['profit_growth_qoq'] = 999.9  # Cap at large positive
        
        # YoY Growth (compare with same quarter last year)
        if i >= 4:
            prev_year = quarters[i-4]
            curr = quarters[i]
            
            # Revenue YoY
            if prev_year['revenue'] > 0:
                curr['revenue_growth_yoy'] = round(
                    (curr['revenue'] - prev_year['revenue']) / prev_year['revenue'] * 100, 
                    1
                )
            
            # Profit YoY
            if prev_year['profit'] > 0:
                curr['profit_growth_yoy'] = round(
                    (curr['profit'] - prev_year['profit']) / prev_year['profit'] * 100, 
                    1
                )
            elif prev_year['profit'] <= 0 and curr['profit'] > 0:
                curr['profit_growth_yoy'] = 999.9
    
    return quarters


def analyze_quarterly_trends(quarters: List[Dict]) -> Dict:
    """
    Analyze trends across quarters.
    
    Returns trend analysis including:
    - Revenue/Profit trend (GROWING/DECLINING/FLAT)
    - Margin trend (EXPANDING/CONTRACTING/STABLE)
    - Consistency rating
    - Average growth rates
    """
    if len(quarters) < 3:
        return {
            'revenue_trend': 'INSUFFICIENT_DATA',
            'profit_trend': 'INSUFFICIENT_DATA',
            'margin_trend': 'INSUFFICIENT_DATA',
            'consistency': 'UNKNOWN'
        }
    
    # Get recent quarters (last 4 for trend analysis)
    recent = quarters[-4:] if len(quarters) >= 4 else quarters
    
    # Revenue trend
    revenue_growth = [
        q['revenue_growth_qoq'] 
        for q in recent 
        if q.get('revenue_growth_qoq') is not None
    ]
    
    if revenue_growth:
        avg_revenue_growth = sum(revenue_growth) / len(revenue_growth)
        
        if avg_revenue_growth > 5:
            revenue_trend = 'GROWING'
        elif avg_revenue_growth < -5:
            revenue_trend = 'DECLINING'
        else:
            revenue_trend = 'FLAT'
    else:
        revenue_trend = 'UNKNOWN'
        avg_revenue_growth = 0
    
    # Profit trend
    profit_growth = [
        q['profit_growth_qoq'] 
        for q in recent 
        if q.get('profit_growth_qoq') is not None and q['profit_growth_qoq'] < 900
    ]
    
    if profit_growth:
        avg_profit_growth = sum(profit_growth) / len(profit_growth)
        
        if avg_profit_growth > 5:
            profit_trend = 'GROWING'
        elif avg_profit_growth < -5:
            profit_trend = 'DECLINING'
        else:
            profit_trend = 'FLAT'
    else:
        profit_trend = 'UNKNOWN'
        avg_profit_growth = 0
    
    # Margin trend
    margins = [q['margin'] for q in recent]
    if len(margins) >= 2:
        margin_change = margins[-1] - margins[0]
        
        if margin_change > 2:
            margin_trend = 'EXPANDING'
        elif margin_change < -2:
            margin_trend = 'CONTRACTING'
        else:
            margin_trend = 'STABLE'
        
        avg_margin = sum(margins) / len(margins)
    else:
        margin_trend = 'UNKNOWN'
        avg_margin = 0
    
    # Consistency (how many quarters had positive growth)
    quarters_with_growth = sum(
        1 for q in quarters 
        if q.get('revenue_growth_qoq') and q['revenue_growth_qoq'] > 0
    )
    total_quarters_with_data = sum(
        1 for q in quarters 
        if q.get('revenue_growth_qoq') is not None
    )
    
    if total_quarters_with_data > 0:
        consistency_ratio = quarters_with_growth / total_quarters_with_data
        
        if consistency_ratio >= 0.75:
            consistency = 'HIGH'
        elif consistency_ratio >= 0.5:
            consistency = 'MEDIUM'
        else:
            consistency = 'LOW'
    else:
        consistency = 'UNKNOWN'
    
    return {
        'revenue_trend': revenue_trend,
        'profit_trend': profit_trend,
        'margin_trend': margin_trend,
        'consistency': consistency,
        'avg_revenue_growth': round(avg_revenue_growth, 1),
        'avg_profit_growth': round(avg_profit_growth, 1),
        'avg_margin': round(avg_margin, 1),
        'quarters_with_growth': quarters_with_growth,
        'total_quarters': total_quarters_with_data
    }


def generate_quarterly_alerts(quarters: List[Dict], trends: Dict) -> List[Dict]:
    """Generate alerts based on quarterly trends."""
    alerts = []
    
    if len(quarters) < 2:
        return alerts
    
    recent = quarters[-4:] if len(quarters) >= 4 else quarters
    latest = quarters[-1]
    
    # Alert 1: Declining revenue for 2+ consecutive quarters
    revenue_declines = sum(
        1 for q in recent[-3:] 
        if q.get('revenue_growth_qoq') and q['revenue_growth_qoq'] < 0
    )
    
    if revenue_declines >= 2:
        alerts.append({
            'type': 'WARNING',
            'message': f'Revenue declining for {revenue_declines} consecutive quarters',
            'severity': 'HIGH'
        })
    
    # Alert 2: Margin compression
    if len(recent) >= 2:
        margin_change = latest['margin'] - recent[-2]['margin']
        if margin_change < -3:
            alerts.append({
                'type': 'WARNING',
                'message': f'Margin compressed by {abs(margin_change):.1f}% in latest quarter',
                'severity': 'MEDIUM'
            })
    
    # Alert 3: Profit decline despite revenue growth
    if (latest.get('revenue_growth_qoq') and latest['revenue_growth_qoq'] > 0 and
        latest.get('profit_growth_qoq') and latest['profit_growth_qoq'] < -5):
        alerts.append({
            'type': 'WARNING',
            'message': 'Profit declining despite revenue growth - margin pressure',
            'severity': 'HIGH'
        })
    
    # Alert 4: Strong consistent growth
    if trends['consistency'] == 'HIGH' and trends['avg_revenue_growth'] > 10:
        alerts.append({
            'type': 'POSITIVE',
            'message': f'Strong consistent growth: {trends["avg_revenue_growth"]}% avg revenue growth',
            'severity': 'LOW'
        })
    
    # Alert 5: Turnaround detected
    if len(recent) >= 3:
        prev_two_negative = all(
            q.get('profit_growth_qoq') and q['profit_growth_qoq'] < 0 
            for q in recent[-3:-1]
        )
        latest_positive = (
            latest.get('profit_growth_qoq') and 
            latest['profit_growth_qoq'] > 5
        )
        
        if prev_two_negative and latest_positive:
            alerts.append({
                'type': 'POSITIVE',
                'message': 'Turnaround detected - profit growth resumed after 2 quarters',
                'severity': 'LOW'
            })
    
    # Alert 6: EBITDA margin expansion
    if len(recent) >= 2:
        ebitda_change = latest['ebitda_margin'] - recent[-2]['ebitda_margin']
        if ebitda_change > 3:
            alerts.append({
                'type': 'POSITIVE',
                'message': f'EBITDA margin expanded by {ebitda_change:.1f}% - operational efficiency improving',
                'severity': 'LOW'
            })
    
    return alerts

File 2: Add to main.py (FastAPI Endpoint)
python# Add import at the top
from modules.quarterly_results import get_quarterly_timeline

# Add endpoint
@app.get("/api/quarterly-results/{symbol}")
async def quarterly_results_endpoint(symbol: str, quarters: int = 12):
    """
    Get quarterly financial results timeline.
    
    Args:
        symbol: Stock symbol (e.g., 'RELIANCE.NS')
        quarters: Number of quarters to fetch (default: 12)
        
    Returns:
        Quarterly results with trends and alerts
    """
    try:
        data = await get_quarterly_timeline(symbol, quarters)
        return data
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch quarterly results: {str(e)}"
        )

Frontend Implementation (3 hours)
File 3: web-ui/src/components/QuarterlyTimeline.jsx (NEW FILE)
jsximport React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart
} from 'recharts';

const QuarterlyTimeline = ({ symbol }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState('revenue'); // 'revenue' | 'profit' | 'margin' | 'combined'

  useEffect(() => {
    fetchQuarterlyData();
  }, [symbol]);

  const fetchQuarterlyData = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axios.get(`/api/quarterly-results/${symbol}`);
      setData(response.data);
    } catch (err) {
      console.error('Failed to fetch quarterly results:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        <span className="ml-3 text-gray-400">Loading quarterly results...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
        <p className="text-red-400">Failed to load quarterly results: {error}</p>
      </div>
    );
  }

  if (!data || !data.quarters || data.quarters.length === 0) {
    return (
      <div className="bg-yellow-900/20 border border-yellow-500 rounded-lg p-4">
        <p className="text-yellow-400">No quarterly data available for this stock</p>
      </div>
    );
  }

  const { quarters, trends, alerts, company_name } = data;

  // Prepare chart data
  const chartData = quarters.map(q => ({
    quarter: q.quarter,
    revenue: q.revenue,
    profit: q.profit,
    ebitda: q.ebitda,
    margin: q.margin,
    ebitda_margin: q.ebitda_margin,
    revenue_growth: q.revenue_growth_qoq || 0,
    profit_growth: q.profit_growth_qoq || 0
  }));

  // Custom tooltip for charts
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-gray-800 border border-gray-600 rounded-lg p-3 shadow-lg">
          <p className="font-semibold text-white mb-2">{label}</p>
          {payload.map((entry, index) => (
            <p key={index} className="text-sm" style={{ color: entry.color }}>
              {entry.name}: {typeof entry.value === 'number' ? entry.value.toFixed(1) : entry.value}
              {entry.name.includes('Margin') || entry.name.includes('Growth') ? '%' : ''}
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  // Trend badge component
  const TrendBadge = ({ trend, metric }) => {
    const getColor = () => {
      if (trend === 'GROWING' || trend === 'EXPANDING' || trend === 'HIGH') {
        return 'bg-green-900/30 text-green-400 border-green-500';
      } else if (trend === 'DECLINING' || trend === 'CONTRACTING' || trend === 'LOW') {
        return 'bg-red-900/30 text-red-400 border-red-500';
      } else {
        return 'bg-gray-700 text-gray-300 border-gray-600';
      }
    };

    return (
      <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold border ${getColor()}`}>
        {trend}
      </span>
    );
  };

  // Alert component
  const AlertBanner = ({ alert }) => {
    const getStyle = () => {
      if (alert.type === 'WARNING') {
        return 'bg-red-900/20 border-red-500 text-red-300';
      } else if (alert.type === 'POSITIVE') {
        return 'bg-green-900/20 border-green-500 text-green-300';
      } else {
        return 'bg-yellow-900/20 border-yellow-500 text-yellow-300';
      }
    };

    const getIcon = () => {
      if (alert.type === 'WARNING') return '⚠️';
      if (alert.type === 'POSITIVE') return '✓';
      return 'ℹ️';
    };

    return (
      <div className={`flex items-start border rounded-lg p-3 ${getStyle()}`}>
        <span className="text-xl mr-3">{getIcon()}</span>
        <div>
          <p className="text-sm font-medium">{alert.message}</p>
          {alert.severity && (
            <p className="text-xs opacity-75 mt-1">Severity: {alert.severity}</p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="quarterly-timeline space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-2xl font-bold text-white mb-1">
          Quarterly Results Timeline
        </h3>
        <p className="text-sm text-gray-400">
          {company_name} - Last {quarters.length} Quarters
        </p>
      </div>

      {/* Alerts */}
      {alerts && alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((alert, idx) => (
            <AlertBanner key={idx} alert={alert} />
          ))}
        </div>
      )}

      {/* Trend Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 uppercase mb-2">Revenue Trend</div>
          <TrendBadge trend={trends.revenue_trend} metric="revenue" />
          {trends.avg_revenue_growth !== undefined && (
            <div className={`text-lg font-bold mt-2 ${
              trends.avg_revenue_growth > 0 ? 'text-green-400' : 'text-red-400'
            }`}>
              {trends.avg_revenue_growth > 0 ? '+' : ''}{trends.avg_revenue_growth}%
              <span className="text-xs text-gray-400 ml-1">avg</span>
            </div>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 uppercase mb-2">Profit Trend</div>
          <TrendBadge trend={trends.profit_trend} metric="profit" />
          {trends.avg_profit_growth !== undefined && (
            <div className={`text-lg font-bold mt-2 ${
              trends.avg_profit_growth > 0 ? 'text-green-400' : 'text-red-400'
            }`}>
              {trends.avg_profit_growth > 0 ? '+' : ''}{trends.avg_profit_growth}%
              <span className="text-xs text-gray-400 ml-1">avg</span>
            </div>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 uppercase mb-2">Margin Trend</div>
          <TrendBadge trend={trends.margin_trend} metric="margin" />
          {trends.avg_margin !== undefined && (
            <div className="text-lg font-bold mt-2 text-white">
              {trends.avg_margin}%
              <span className="text-xs text-gray-400 ml-1">avg</span>
            </div>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-xs text-gray-400 uppercase mb-2">Consistency</div>
          <TrendBadge trend={trends.consistency} metric="consistency" />
          {trends.quarters_with_growth !== undefined && (
            <div className="text-sm text-gray-300 mt-2">
              {trends.quarters_with_growth}/{trends.total_quarters} quarters
              <span className="text-xs text-gray-400 ml-1">growth</span>
            </div>
          )}
        </div>
      </div>

      {/* View Mode Toggle */}
      <div className="flex items-center justify-between">
        <h4 className="text-lg font-semibold text-white">Performance Charts</h4>
        <div className="flex gap-2">
          <button
            onClick={() => setViewMode('revenue')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'revenue'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            Revenue
          </button>
          <button
            onClick={() => setViewMode('profit')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'profit'
                ? 'bg-green-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            Profit
          </button>
          <button
            onClick={() => setViewMode('margin')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'margin'
                ? 'bg-yellow-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            Margins
          </button>
          <button
            onClick={() => setViewMode('combined')}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              viewMode === 'combined'
                ? 'bg-purple-600 text-white'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            Combined
          </button>
        </div>
      </div>

      {/* Charts */}
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-700">
        {viewMode === 'revenue' && (
          <ResponsiveContainer width="100%" height={350}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="quarter" stroke="#9CA3AF" />
              <YAxis yAxisId="left" stroke="#9CA3AF" />
              <YAxis yAxisId="right" orientation="right" stroke="#9CA3AF" />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Bar yAxisId="left" dataKey="revenue" fill="#3B82F6" name="Revenue (₹Cr)" />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="revenue_growth"
                stroke="#10B981"
                strokeWidth={2}
                name="QoQ Growth %"
                dot={{ r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}

        {viewMode === 'profit' && (
          <ResponsiveContainer width="100%" height={350}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="quarter" stroke="#9CA3AF" />
              <YAxis yAxisId="left" stroke="#9CA3AF" />
              <YAxis yAxisId="right" orientation="right" stroke="#9CA3AF" />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Bar yAxisId="left" dataKey="profit" fill="#10B981" name="Profit (₹Cr)" />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="profit_growth"
                stroke="#F59E0B"
                strokeWidth={2}
                name="QoQ Growth %"
                dot={{ r: 4 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}

        {viewMode === 'margin' && (
          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="quarter" stroke="#9CA3AF" />
              <YAxis stroke="#9CA3AF" />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Line
                type="monotone"
                dataKey="margin"
                stroke="#FBBF24"
                strokeWidth={2}
                name="Net Margin %"
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="ebitda_margin"
                stroke="#8B5CF6"
                strokeWidth={2}
                name="EBITDA Margin %"
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}

        {viewMode === 'combined' && (
          <ResponsiveContainer width="100%" height={350}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="quarter" stroke="#9CA3AF" />
              <YAxis yAxisId="left" stroke="#9CA3AF" />
              <YAxis yAxisId="right" orientation="right" stroke="#9CA3AF" />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              <Bar yAxisId="left" dataKey="revenue" fill="#3B82F6" name="Revenue" opacity={0.6} />
              <Bar yAxisId="left" dataKey="profit" fill="#10B981" name="Profit" opacity={0.6} />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="margin"
                stroke="#FBBF24"
                strokeWidth={2}
                name="Margin %"
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Detailed Table */}
      <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-700">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-800 border-b border-gray-700">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">
                  Quarter
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">
                  Revenue (₹Cr)
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">
                  QoQ Growth
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">
                  YoY Growth
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">
                  Profit (₹Cr)
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">
                  QoQ Growth
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">
                  Margin %
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase">
                  EBITDA Margin %
                </th>
              </tr>
            </thead>
            <tbody>
              {quarters.map((q, idx) => (
                <tr
                  key={idx}
                  className={`border-b border-gray-700 hover:bg-gray-800/50 transition-colors ${
                    idx === quarters.length - 1 ? 'bg-blue-900/20' : 'bg-gray-800'
                  }`}
                >
                  <td className="px-4 py-3">
                    <div className="font-semibold text-white">{q.quarter}</div>
                    <div className="text-xs text-gray-400">{q.date}</div>
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-white">
                    ₹{q.revenue.toLocaleString()}
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold ${
                    q.revenue_growth_qoq > 0
                      ? 'text-green-400'
                      : q.revenue_growth_qoq < 0
                      ? 'text-red-400'
                      : 'text-gray-400'
                  }`}>
                    {q.revenue_growth_qoq !== null
                      ? `${q.revenue_growth_qoq > 0 ? '+' : ''}${q.revenue_growth_qoq}%`
                      : '—'}
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold ${
                    q.revenue_growth_yoy > 0
                      ? 'text-green-400'
                      : q.revenue_growth_yoy < 0
                      ? 'text-red-400'
                      : 'text-gray-400'
                  }`}>
                    {q.revenue_growth_yoy !== null
                      ? `${q.revenue_growth_yoy > 0 ? '+' : ''}${q.revenue_growth_yoy}%`
                      : '—'}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-white">
                    ₹{q.profit.toLocaleString()}
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold ${
                    q.profit_growth_qoq > 0
                      ? 'text-green-400'
                      : q.profit_growth_qoq < 0
                      ? 'text-red-400'
                      : 'text-gray-400'
                  }`}>
                    {q.profit_growth_qoq !== null && q.profit_growth_qoq < 900
                      ? `${q.profit_growth_qoq > 0 ? '+' : ''}${q.profit_growth_qoq}%`
                      : q.profit_growth_qoq >= 900
                      ? 'Turnaround'
                      : '—'}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-white">
                    {q.margin}%
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-white">
                    {q.ebitda_margin}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Key Insights */}
      <div className="bg-gray-800 rounded-lg p-5 border border-gray-700">
        <h4 className="text-sm font-semibold text-gray-400 mb-3 uppercase">
          Key Insights
        </h4>
        <div className="space-y-3">
          {/* Revenue Insight */}
          {trends.revenue_trend === 'GROWING' && (
            <div className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-900/30 flex items-center justify-center mr-3">
                <span className="text-green-400 text-xs">✓</span>
              </div>
              <p className="text-sm text-gray-300">
                Revenue showing <span className="font-semibold text-green-400">consistent growth</span> with
                average QoQ growth of <span className="font-semibold text-white">{trends.avg_revenue_growth}%</span>.
                {trends.consistency === 'HIGH' && (
                  <span className="text-green-400 ml-1">High consistency across quarters.</span>
                )}
              </p>
            </div>
          )}

          {trends.revenue_trend === 'DECLINING' && (
            <div className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-red-900/30 flex items-center justify-center mr-3">
                <span className="text-red-400 text-xs">⚠</span>
              </div>
              <p className="text-sm text-gray-300">
                Revenue <span className="font-semibold text-red-400">declining</span> with
                average QoQ change of <span className="font-semibold text-white">{trends.avg_revenue_growth}%</span>.
                <span className="text-red-400 ml-1">Thesis break risk - investigate fundamentals.</span>
              </p>
            </div>
          )}

          {/* Margin Insight */}
          {trends.margin_trend === 'EXPANDING' && (
            <div className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-900/30 flex items-center justify-center mr-3">
                <span className="text-green-400 text-xs">✓</span>
              </div>
              <p className="text-sm text-gray-300">
                Margins <span className="font-semibold text-green-400">expanding</span> - improving operational
                efficiency and pricing power.
              </p>
            </div>
          )}

          {trends.margin_trend === 'CONTRACTING' && (
            <div className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-red-900/30 flex items-center justify-center mr-3">
                <span className="text-red-400 text-xs">⚠</span>
              </div>
              <p className="text-sm text-gray-300">
                Margins <span className="font-semibold text-red-400">contracting</span> - watch for pricing
                pressure, cost inflation, or competitive headwinds.
              </p>
            </div>
          )}

          {/* Combined Insight */}
          {trends.profit_trend === 'GROWING' && trends.revenue_trend === 'GROWING' && (
            <div className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-900/30 flex items-center justify-center mr-3">
                <span className="text-green-400 text-xs">✓</span>
              </div>
              <p className="text-sm text-gray-300">
                Both revenue and profit growing - <span className="font-semibold text-green-400">strong
                fundamental momentum</span>. Stock is execution on strategy effectively.
              </p>
            </div>
          )}

          {/* Latest Quarter Highlight */}
          {quarters.length > 0 && (
            <div className="flex items-start">
              <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-900/30 flex items-center justify-center mr-3">
                <span className="text-blue-400 text-xs">ℹ</span>
              </div>
              <p className="text-sm text-gray-300">
                Latest quarter ({quarters[quarters.length - 1].quarter}):{' '}
                Revenue ₹{quarters[quarters.length - 1].revenue.toLocaleString()}Cr,{' '}
                Profit ₹{quarters[quarters.length - 1].profit.toLocaleString()}Cr,{' '}
                Margin {quarters[quarters.length - 1].margin}%.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Timestamp */}
      <div className="text-xs text-gray-500 text-center">
        Last updated: {new Date(data.timestamp).toLocaleString()}
      </div>
    </div>
  );
};

export default QuarterlyTimeline;

File 4: Integrate into Stock Detail Modal
jsx// In your StockDetailModal.jsx

import QuarterlyTimeline from './QuarterlyTimeline';

// Add to tabs array
const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'fundamentals', label: 'Fundamentals' },
  { id: 'peer-comparison', label: 'Peer Comparison' },
  { id: 'quarterly-results', label: 'Quarterly Results' }, // NEW TAB
  { id: 'news', label: 'News' },
];

// In tab content rendering:
{activeTab === 'quarterly-results' && (
  <QuarterlyTimeline symbol={selectedStock.symbol} />
)}

Testing Checklist

 Backend endpoint returns data for test symbols (RELIANCE.NS, TCS.NS)
 QoQ and YoY growth calculations are accurate
 Trend analysis (GROWING/DECLINING/FLAT) works correctly
 Alerts generate for margin compression, revenue decline
 Charts render correctly for all view modes (revenue, profit, margin, combined)
 Detailed table shows all quarters with proper formatting
 Loading and error states display properly
 Component integrates into modal without layout issues


This completes Feature 2: Quarterly Results Timeline