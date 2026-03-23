"""
Peer Comparison Module
Compares stocks against sector peers with comprehensive metrics.
"""

import pandas as pd
from typing import List, Dict, Optional
import yfinance as yf
import asyncio
from datetime import datetime
import sqlite3
import os
from modules.retry_utils import run_with_exponential_backoff

# NSE Sector Mapping (Initial set provided by user)
SECTOR_MAP = {
    # IT Sector
    'TCS.NS': 'Information Technology',
    'INFY.NS': 'Information Technology',
    'WIPRO.NS': 'Information Technology',
    'HCLTECH.NS': 'Information Technology',
    'TECHM.NS': 'Information Technology',
    'LTI.NS': 'Information Technology',
    'MINDTREE.NS': 'Information Technology',
    'MPHASIS.NS': 'Information Technology',
    'COFORGE.NS': 'Information Technology',
    'PERSISTENT.NS': 'Information Technology',
    
    # Finance Sector
    'HDFCBANK.NS': 'Banking & Finance',
    'ICICIBANK.NS': 'Banking & Finance',
    'SBIN.NS': 'Banking & Finance',
    'KOTAKBANK.NS': 'Banking & Finance',
    'AXISBANK.NS': 'Banking & Finance',
    'INDUSINDBK.NS': 'Banking & Finance',
    'BANDHANBNK.NS': 'Banking & Finance',
    'FEDERALBNK.NS': 'Banking & Finance',
    'IDFCFIRSTB.NS': 'Banking & Finance',
    'PNB.NS': 'Banking & Finance',
    'BANKBARODA.NS': 'Banking & Finance',
    'BAJFINANCE.NS': 'Banking & Finance',
    'BAJAJFINSV.NS': 'Banking & Finance',
    'HDFCLIFE.NS': 'Banking & Finance',
    'SBILIFE.NS': 'Banking & Finance',
    'ICICIGI.NS': 'Banking & Finance',
    'ICICIPRULI.NS': 'Banking & Finance',
    'PFC.NS': 'Banking & Finance',
    'REC.NS': 'Banking & Finance',
    'RECLTD.NS': 'Banking & Finance',
    'CHOLAFIN.NS': 'Banking & Finance',
    'M&MFIN.NS': 'Banking & Finance',
    'MUTHOOTFIN.NS': 'Banking & Finance',
    'MANAPPURAM.NS': 'Banking & Finance',
    'AUBANK.NS': 'Banking & Finance',
    'KARURVYSYA.NS': 'Banking & Finance',
    'SHRIRAMFIN.NS': 'Banking & Finance',
    'MAHABANK.NS': 'Banking & Finance',
    'UNIONBANK.NS': 'Banking & Finance',
    'CANBK.NS': 'Banking & Finance',
    'INDIANB.NS': 'Banking & Finance',
    'BANKINDIA.NS': 'Banking & Finance',
    'CENTRALBK.NS': 'Banking & Finance',
    'UCOBANK.NS': 'Banking & Finance',
    'IOB.NS': 'Banking & Finance',
    'J&KBANK.NS': 'Banking & Finance',
    'CSBBANK.NS': 'Banking & Finance',
    'DCBBANK.NS': 'Banking & Finance',
    'EQUITASBNK.NS': 'Banking & Finance',
    'SOUTHBANK.NS': 'Banking & Finance',
    'KTKBANK.NS': 'Banking & Finance',
    'RBLBANK.NS': 'Banking & Finance',
    'CUB.NS': 'Banking & Finance',
    'IDBI.NS': 'Banking & Finance',
    'YESBANK.NS': 'Banking & Finance',
    
    # Energy Sector
    'RELIANCE.NS': 'Oil & Gas',
    'ONGC.NS': 'Oil & Gas',
    'IOC.NS': 'Oil & Gas',
    'BPCL.NS': 'Oil & Gas',
    'HINDPETRO.NS': 'Oil & Gas',
    'GAIL.NS': 'Oil & Gas',
    'PETRONET.NS': 'Oil & Gas',
    'COALINDIA.NS': 'Oil & Gas',
    'NTPC.NS': 'Power',
    'POWERGRID.NS': 'Power',
    'TATAPOWER.NS': 'Power',
    'ADANIPOWER.NS': 'Power',
    'ADANIGREEN.NS': 'Power',
    'SJVN.NS': 'Power',
    'NHPC.NS': 'Power',
    'IREDA.NS': 'Power',
    'JSWENERGY.NS': 'Power',
    
    # Auto Sector
    'MARUTI.NS': 'Automobile',
    'TATAMOTORS.NS': 'Automobile',
    'M&M.NS': 'Automobile',
    'BAJAJ-AUTO.NS': 'Automobile',
    'HEROMOTOCO.NS': 'Automobile',
    'EICHERMOT.NS': 'Automobile',
    'ASHOKLEY.NS': 'Automobile',
    'TVSMOTOR.NS': 'Automobile',
    'ESCORTS.NS': 'Automobile',
    'APOLLOTYRE.NS': 'Automobile',
    'MRF.NS': 'Automobile',
    'BHARATFORG.NS': 'Automobile',
    
    # Pharma Sector
    'SUNPHARMA.NS': 'Pharmaceuticals',
    'DRREDDY.NS': 'Pharmaceuticals',
    'CIPLA.NS': 'Pharmaceuticals',
    'DIVISLAB.NS': 'Pharmaceuticals',
    'BIOCON.NS': 'Pharmaceuticals',
    'AUROPHARMA.NS': 'Pharmaceuticals',
    'LUPIN.NS': 'Pharmaceuticals',
    'TORNTPHARM.NS': 'Pharmaceuticals',
    'ALKEM.NS': 'Pharmaceuticals',
    'IPCALAB.NS': 'Pharmaceuticals',
    'MAXHEALTH.NS': 'Pharmaceuticals',
    
    # FMCG Sector
    'HINDUNILVR.NS': 'FMCG',
    'ITC.NS': 'FMCG',
    'NESTLEIND.NS': 'FMCG',
    'BRITANNIA.NS': 'FMCG',
    'DABUR.NS': 'FMCG',
    'MARICO.NS': 'FMCG',
    'GODREJCP.NS': 'FMCG',
    'COLPAL.NS': 'FMCG',
    'TATACONSUM.NS': 'FMCG',
    'VARUN.NS': 'FMCG',
    'VBL.NS': 'FMCG',
    
    # Metals & Mining
    'TATASTEEL.NS': 'Metals & Mining',
    'HINDALCO.NS': 'Metals & Mining',
    'JSWSTEEL.NS': 'Metals & Mining',
    'VEDL.NS': 'Metals & Mining',
    'SAIL.NS': 'Metals & Mining',
    'NATIONALUM.NS': 'Metals & Mining',
    'JINDALSTEL.NS': 'Metals & Mining',
    'NMDC.NS': 'Metals & Mining',
    
    # Cement
    'ULTRACEMCO.NS': 'Cement',
    'GRASIM.NS': 'Cement',
    'SHREECEM.NS': 'Cement',
    'ACC.NS': 'Cement',
    'AMBUJACEM.NS': 'Cement',
    'JKCEMENT.NS': 'Cement',
    'RAMCOCEM.NS': 'Cement',
    
    # Telecom
    'BHARTIARTL.NS': 'Telecom',
    'INDUSTOWER.NS': 'Telecom',
    
    # Infrastructure & Defense
    'LT.NS': 'Infrastructure',
    'ADANIPORTS.NS': 'Infrastructure',
    'DLF.NS': 'Infrastructure',
    'GODREJPROP.NS': 'Infrastructure',
    'OBEROIRLTY.NS': 'Infrastructure',
    'BEL.NS': 'Defense',
    'HAL.NS': 'Defense',
    'BDL.NS': 'Defense',
    'MAZDOCK.NS': 'Defense',
    'COCHINSHIP.NS': 'Defense',
    'RVNL.NS': 'Railways',
    'IRFC.NS': 'Railways',
    'IRCON.NS': 'Railways',
}


def get_sector(symbol: str) -> str:
    """Get sector for a given stock symbol."""
    return SECTOR_MAP.get(symbol, 'Unknown')


def get_sector_peers(symbol: str, limit: int = 5) -> List[str]:
    """
    Get peer stocks from the same sector.
    """
    sector = get_sector(symbol)
    
    if sector == 'Unknown':
        return []
    
    # Get all stocks in same sector
    peers = [s for s, sec in SECTOR_MAP.items() if sec == sector and s != symbol]
    
    return peers[:limit]


async def get_peer_comparison(symbol: str) -> Dict:
    """
    Get comprehensive peer comparison data.
    """
    # Normalize symbol
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"
        
    sector = get_sector(symbol)
    peer_symbols = get_sector_peers(symbol, limit=5)
    
    # Fetch metrics for main stock
    stock_metrics = await fetch_stock_metrics(symbol)
    
    if not peer_symbols:
        return {
            'stock': symbol,
            'sector': sector,
            'peers': [],
            'stock_metrics': stock_metrics,
            'sector_avg': {},
            'rankings': {'total_peers': 1, 'score_rank': 1, 'score_rank_desc': "1/1"},
            'timestamp': datetime.now().isoformat()
        }
    
    # Fetch metrics for all peers in parallel
    peer_data = await asyncio.gather(
        *[fetch_stock_metrics(peer) for peer in peer_symbols],
        return_exceptions=True
    )
    
    # Filter out failed fetches
    peer_data = [p for p in peer_data if isinstance(p, dict) and 'error' not in p]
    
    # Calculate sector averages
    all_stocks = [stock_metrics] + peer_data
    sector_avg = calculate_sector_average(all_stocks)
    
    # Calculate rankings
    rankings = calculate_rankings(symbol, all_stocks)
    
    return {
        'stock': symbol,
        'sector': sector,
        'peers': peer_data,
        'stock_metrics': stock_metrics,
        'sector_avg': sector_avg,
        'rankings': rankings,
        'timestamp': datetime.now().isoformat()
    }


async def fetch_stock_metrics(symbol: str) -> Dict:
    """
    Fetch all relevant metrics for a stock with retries and non-blocking I/O.
    """
    try:
        # Optimization: Fetch only 'info' + 'history' first.
        # 'financials' and 'balance_sheet' involve heavy network calls.
        # We try to get data from 'info' which is faster (often).
        
        async def _load_full_payload():
            ticker = await asyncio.to_thread(yf.Ticker, symbol)
            # Fetch essential data
            info = await asyncio.to_thread(lambda: ticker.info)
            hist = await asyncio.to_thread(lambda: ticker.history(period="3mo"))
            return ticker, info, hist

        ticker, info, hist = await run_with_exponential_backoff(
            _load_full_payload,
            context=f"yfinance peer fetch for {symbol}",
        )
        
        # Lazy load these only if needed
        financials = pd.DataFrame()
        balance_sheet = pd.DataFrame()
        
        async def _lazy_load_financials():
            return await asyncio.to_thread(lambda: ticker.financials)
            
        async def _lazy_load_bs():
            return await asyncio.to_thread(lambda: ticker.balance_sheet)

        pe = info.get("trailingPE")
        roe = info.get("returnOnEquity")
        if roe:
            roe = round(roe * 100, 1)

        # Try getting D/E from info first (Fastest)
        debt_equity = info.get("debtToEquity")
        if debt_equity is not None:
             # YF returns it as percentage usually (e.g. 50.5 for 0.5)
             debt_equity = round(debt_equity / 100, 2)
        else:
            # Fallback to granular calculation (Slow)
            try:
                balance_sheet = await _lazy_load_bs()
                if not balance_sheet.empty:
                    debt_row = next((r for r in balance_sheet.index if "Total Debt" in r), None)
                    equity_row = next(
                        (
                            r
                            for r in balance_sheet.index
                            if "Stockholders Equity" in r or "Common Stock Equity" in r
                        ),
                        None,
                    )
                    if debt_row and equity_row:
                        total_debt = balance_sheet.loc[debt_row].iloc[0]
                        total_equity = balance_sheet.loc[equity_row].iloc[0]
                        if total_equity and total_equity > 0:
                            debt_equity = round(total_debt / total_equity, 2)
            except Exception:
                pass

        market_cap = info.get("marketCap", 0)
        market_cap_cr = round((market_cap * 75) / 10000000, 0) if market_cap else None

        price_change_1m = None
        price_change_3m = None
        current_price = None

        if not hist.empty:
            current_price = round(hist["Close"].iloc[-1], 2)
            if len(hist) >= 20:
                price_1m_ago = hist["Close"].iloc[-20]
                price_change_1m = round(
                    ((current_price - price_1m_ago) / price_1m_ago) * 100, 1
                )

            price_3m_ago = hist["Close"].iloc[0]
            price_change_3m = round(
                ((current_price - price_3m_ago) / price_3m_ago) * 100, 1
            )

        # Try getting Growth from info (Fastest)
        revenue_growth = info.get("revenueGrowth") # e.g. 0.15 for 15%
        if revenue_growth:
            revenue_growth = round(revenue_growth * 100, 1)
        
        profit_growth = info.get("earningsGrowth")
        if profit_growth:
            profit_growth = round(profit_growth * 100, 1)

        # Fallback if both missing
        if revenue_growth is None or profit_growth is None:
            try:
                financials = await _lazy_load_financials()
                if not financials.empty and len(financials.columns) >= 2:
                    if revenue_growth is None:
                        rev_row = next((r for r in financials.index if "Total Revenue" in r), None)
                        if rev_row:
                            rev_current = financials.loc[rev_row].iloc[0]
                            rev_previous = financials.loc[rev_row].iloc[1]
                            if rev_previous and rev_previous > 0:
                                revenue_growth = round(
                                    ((rev_current - rev_previous) / rev_previous) * 100, 1
                                )
                    
                    if profit_growth is None:
                        net_inc_row = next((r for r in financials.index if "Net Income" in r), None)
                        if net_inc_row:
                            profit_current = financials.loc[net_inc_row].iloc[0]
                            profit_previous = financials.loc[net_inc_row].iloc[1]
                            if profit_previous and profit_previous > 0:
                                profit_growth = round(
                                    ((profit_current - profit_previous) / profit_previous) * 100,
                                    1,
                                )
            except Exception:
                pass

        terminal_score = await get_terminal_score_from_db(symbol)

        return {
            "symbol": symbol,
            "name": info.get("longName", symbol.replace(".NS", "")),
            "pe": round(pe, 1) if pe and pe > 0 else None,
            "roe": roe,
            "debt_equity": debt_equity,
            "market_cap": int(market_cap_cr) if market_cap_cr else None,
            "price_change_1m": price_change_1m,
            "price_change_3m": price_change_3m,
            "terminal_score": terminal_score,
            "revenue_growth": revenue_growth,
            "profit_growth": profit_growth,
            "current_price": current_price,
        }
    except Exception as e:
        print(f"Peer fetch failed for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


async def get_terminal_score_from_db(symbol: str) -> Optional[int]:
    """Fetch Terminal Score from stocks.db"""
    try:
        return await asyncio.to_thread(_sync_db_score_lookup, symbol)
    except:
        return None

def _sync_db_score_lookup(symbol: str):
    db_path = "stocks.db"
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Clean symbol for DB lookup (sometimes only symbol without .NS)
        clean_symbol = symbol.replace(".NS", "")
        
        # Check multibaggers table
        cursor.execute("SELECT score FROM multibaggers WHERE symbol IN (?, ?)", (symbol, clean_symbol))
        row = cursor.fetchone()
        if row: return int(row[0])
        
        # Check microcaps table
        cursor.execute("SELECT score FROM microcaps WHERE symbol IN (?, ?)", (symbol, clean_symbol))
        row = cursor.fetchone()
        if row: return int(row[0])
        
        conn.close()
    except:
        pass
    return None


def calculate_sector_average(all_stocks: List[Dict]) -> Dict:
    """Calculate sector average metrics."""
    valid_data = [p for p in all_stocks if 'error' not in p]
    if not valid_data: return {}
    
    df = pd.DataFrame(valid_data)
    averages = {}
    
    cols = ['pe', 'roe', 'debt_equity', 'terminal_score', 'revenue_growth', 'profit_growth']
    for col in cols:
        if col in df.columns:
            values = df[col].dropna()
            if not values.empty:
                averages[col] = round(values.mean(), 1)
    
    return averages


def calculate_rankings(symbol: str, all_stocks: List[Dict]) -> Dict:
    """Calculate stock ranks among peers."""
    valid_stocks = [s for s in all_stocks if 'error' not in s]
    total_peers = len(valid_stocks)
    
    rankings = {'total_peers': total_peers}
    
    # PE Ranking (lower is better)
    pe_stocks = sorted([(s['symbol'], s['pe']) for s in valid_stocks if s.get('pe')], key=lambda x: x[1])
    if pe_stocks:
        rank = next((i+1 for i, (sym, _) in enumerate(pe_stocks) if sym == symbol), None)
        if rank: rankings['pe_rank_desc'] = f"{rank}/{len(pe_stocks)}"
        rankings['pe_rank'] = rank
        
    # ROE Ranking (higher is better)
    roe_stocks = sorted([(s['symbol'], s['roe']) for s in valid_stocks if s.get('roe')], key=lambda x: x[1], reverse=True)
    if roe_stocks:
        rank = next((i+1 for i, (sym, _) in enumerate(roe_stocks) if sym == symbol), None)
        if rank: rankings['roe_rank_desc'] = f"{rank}/{len(roe_stocks)}"
        rankings['roe_rank'] = rank
        
    # Score Ranking (higher is better)
    score_stocks = sorted([(s['symbol'], s['terminal_score']) for s in valid_stocks if s.get('terminal_score')], key=lambda x: x[1], reverse=True)
    if score_stocks:
        rank = next((i+1 for i, (sym, _) in enumerate(score_stocks) if sym == symbol), None)
        if rank: rankings['score_rank_desc'] = f"{rank}/{len(score_stocks)}"
        rankings['score_rank'] = rank
        
    return rankings

