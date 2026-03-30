"""
Sovereign Engine: Swarm Intelligence Validation Scan
Uses the MiroFish Multi-Agent Engine to predict the trajectory of high-conviction picks.
"""

import argparse
import sys
import logging
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scan_swarm")

from modules.mirofish_client import MiroFishClient

# Mock database retrieval of fundamentals
def get_mock_context(ticker: str) -> str:
    return f"""
    The stock {ticker} has recently crossed its 50-day moving average on strong volume.
    Operating margins have expanded from 15% to 18% over the last two quarters.
    The sector is currently experiencing a cyclical upturn due to macro tailwinds.
    Management guided for 20% revenue growth in the upcoming fiscal year.
    Institutional holdings have increased by 2.5% in the last 30 days.
    """

def run_swarm_scan(tickers: list):
    console = Console()
    console.print(Panel(f"[bold magenta]MiroFish Swarm Validation[/bold magenta]\nLaunching multi-agent simulation for: {', '.join(tickers)}", border_style="magenta"))
    
    client = MiroFishClient()
    
    table = Table(title="Swarm Consensus Output")
    table.add_column("Ticker", style="cyan", no_wrap=True)
    table.add_column("MiroFish Swarm Report", style="green")
    
    for ticker in tickers:
        console.print(f"\\n[blue]Generating project context for {ticker}...[/blue]")
        context = get_mock_context(ticker)
        
        console.print(f"[blue]Submitting to MiroFish Simulation Engine...[/blue]")
        # This will either connect to MiroFish on :5001 or fallback
        report = client.simulate_ticker(ticker, context)
        
        table.add_row(ticker, report)
        
    console.print("\\n", table)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MiroFish Swarm simulation on target tickers.")
    parser.add_argument("--tickers", type=str, required=True, help="Comma-separated list of tickers (e.g. RELIANCE.NS,TCS.NS)")
    
    args = parser.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    
    if not tickers:
        logger.error("No valid tickers provided.")
        sys.exit(1)
        
    run_swarm_scan(tickers)
