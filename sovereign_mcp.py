import asyncio
import os
import sys
from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP
import pandas as pd

# Add the current directory to sys.path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.regime_hmm import RegimeHMM
from modules.mirofish_client import MiroFishClient
from screener import get_stock_data, TICKERS
from ticker_list import SECTORS

# Initialize FastMCP server
mcp = FastMCP("Sovereign Engine")

# --- Tools ---

@mcp.tool()
async def get_market_regime() -> str:
    """
    Detects the current market regime (BULLISH, BEARISH, VOLATILE) 
    using the Hidden Markov Model (HMM) on Nifty 50 returns.
    """
    try:
        # Run in thread since it's a blocking yfinance call
        hmm = RegimeHMM()
        regime = await asyncio.to_thread(hmm.predict_regime)
        return f"Current Market Regime (HMM): {regime}"
    except Exception as e:
        return f"Error detecting market regime: {str(e)}"

@mcp.tool()
async def analyze_ticker(symbol: str) -> str:
    """
    Performs a deep Sovereign Engine analysis on a single stock ticker.
    Returns fundamentals, technicals, and a final Sovereign Score.
    Example: analyze_ticker("RELIANCE.NS")
    """
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO") and len(symbol) <= 6:
             symbol = f"{symbol.upper()}.NS"
             
        data = await get_stock_data(symbol)
        if "_fetch_error" in data:
            return f"Error fetching data for {symbol}: {data['_fetch_error']}"
        
        # Format the output nicely
        score = data.get("Score", 0)
        grade = "A+" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C"
        
        report = [
            f"### Sovereign Analysis: {symbol}",
            f"**Sovereign Score:** {score} ({grade})",
            f"**Current Price:** Rs. {data.get('Price', 'N/A')}",
            f"**Market Regime Alignment:** {data.get('Tech_Signal', 'N/A')}",
            "",
            "**Key Fundamentals:**",
            f"- ROE: {data.get('ROE%', 'N/A')}%",
            f"- Sales Growth (5Y): {data.get('Sales_Growth_5Y%', 'N/A')}%",
            f"- Debt/Equity: {data.get('Debt_Equity', 'N/A')}",
            f"- Piotroski F-Score: {data.get('F_Score', 'N/A')}/9",
            "",
            "**Technical Indicators:**",
            f"- RSI: {data.get('RSI', 'N/A')}",
            f"- RS Rating: {data.get('RS_Rating', 'N/A')}",
            f"- DMA 50/200: {data.get('Price_vs_50DMA', 'N/A')}% / {data.get('Price_vs_200DMA', 'N/A')}%",
            "",
            f"**Thesis Status:** {data.get('Thesis_Check', 'Inconclusive')}"
        ]
        return "\n".join(report)
    except Exception as e:
        return f"Error analyzing {symbol}: {str(e)}"

@mcp.tool()
async def validate_with_swarm(symbol: str) -> str:
    """
    Triggers the MiroFish Multi-Agent Swarm Intelligence simulation for a stock.
    Use this for high-conviction validation of a core investment thesis.
    """
    try:
        client = MiroFishClient()
        # Mock context (can be improved by pulling real news/filings)
        context = f"Analyzing {symbol} for structural multibagger potential. Fundamentals are strong with expanding margins."
        
        report = await asyncio.to_thread(client.simulate_ticker, symbol.upper(), context)
        return f"### MiroFish Swarm Consensus: {symbol}\n\n{report}"
    except Exception as e:
        return f"Error running swarm simulation: {str(e)}"

@mcp.tool()
async def list_sector_opportunities() -> str:
    """
    Lists current top opportunities from the high-conviction SECTORS list.
    """
    try:
        return f"Sovereign Engine high-conviction monitoring list: {', '.join(SECTORS)}"
    except Exception as e:
        return f"Error listing sectors: {str(e)}"

if __name__ == "__main__":
    mcp.run()
