"""
analyze_stock.py - Institutional Grade Stock Analyzer
Provides a robust, parameterized CLI interface for the Sovereign AI Trading Engine.
"""

import sys
import asyncio
import argparse
from typing import Dict, Any

from screener import get_stock_data, calculate_institutional_score

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str) -> None:
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*50}")
    print(f" {text}")
    print(f"{'='*50}{Colors.RESET}")

def evaluate_metric(name: str, value: Any, threshold: str, condition: bool, unit: str = "") -> None:
    status = f"{Colors.GREEN}✅ PASS{Colors.RESET}" if condition else f"{Colors.FAIL}❌ FAIL{Colors.RESET}"
    safe_value = f"{round(value, 2)}{unit}" if isinstance(value, (int, float)) else str(value)
    print(f" {name:<25} {threshold:<10} | {status} ({safe_value})")

def display_report(symbol: str, data: Dict[str, Any], score_data: Dict[str, Any]) -> None:
    print_header(f"📊 Institutional Analysis: {symbol.upper()}")
    
    price = data.get('Price', 0) or 0
    print(f" {Colors.BOLD}Current Price:{Colors.RESET} ₹{price:,.2f}")
    
    score = score_data.get("total_score", 0)
    score_color = Colors.GREEN if score >= 75 else (Colors.WARNING if score >= 60 else Colors.FAIL)
    print(f" {Colors.BOLD}Composite Score:{Colors.RESET} {score_color}{score:.1f}/100{Colors.RESET}")
    print(f" {Colors.BOLD}Data Confidence:{Colors.RESET} {score_data.get('data_confidence', 'N/A')}%")
    print(f" {Colors.BOLD}Quality Checklist:{Colors.RESET} {score_data.get('checklist_score', 'N/A')}\n")

    print(f" {Colors.BLUE}{Colors.BOLD}--- Growth & Profitability ---{Colors.RESET}")
    sales_growth = data.get('Sales_Growth_TTM%', 0) or 0
    evaluate_metric("Sales Growth (TTM)", sales_growth, "> 15%", sales_growth > 15, "%")
    roe = data.get('ROE%', 0) or 0
    evaluate_metric("Return on Equity (ROE)", roe, "> 15%", roe > 15, "%")
    eps_growth = data.get('EPS_Growth%', 0) or 0
    evaluate_metric("EPS Growth", eps_growth, "> 20%", eps_growth > 20, "%")

    print(f"\n {Colors.BLUE}{Colors.BOLD}--- Valuation & Health ---{Colors.RESET}")
    debt_equity = data.get('Debt_Equity', 0) or 0
    evaluate_metric("Debt to Equity", debt_equity, "< 1.0", debt_equity < 1.0)
    peg = data.get('PEG_Ratio', 0) or 0
    evaluate_metric("PEG Ratio", peg, "< 1.5", 0 < peg < 1.5)
    f_score = data.get('F_Score', 0) or 0
    evaluate_metric("Piotroski F-Score", f_score, ">= 6", f_score >= 6)
    smart_money = data.get('Smart_Money%', 0) or 0
    evaluate_metric("Smart Money Holding", smart_money, "> 40%", smart_money > 40, "%")

    print(f"\n {Colors.BLUE}{Colors.BOLD}--- Technical Indicators ---{Colors.RESET}")
    dma_50 = data.get('50_DMA', 0) or 0
    dma_200 = data.get('200_DMA', 0) or 0
    rsi = data.get('RSI', 0) or 0
    evaluate_metric("Price vs 50 DMA", price, "> 50DMA", price > dma_50)
    evaluate_metric("Price vs 200 DMA", price, "> 200DMA", price > dma_200)
    evaluate_metric("Golden Cross", dma_50, "50 > 200", dma_50 > dma_200)
    evaluate_metric("RSI Momentum", rsi, "40-75", 40 <= rsi <= 75)

    print(f"\n {Colors.BLUE}{Colors.BOLD}--- Institutional Consensus ---{Colors.RESET}")
    target_price = data.get('Target_Mean_Price', 0) or 0
    rating = data.get('Analyst_Rating', 'N/A')
    if isinstance(rating, str): rating = rating.replace('_', ' ').title()
    analysts = data.get('Analyst_Count', 0) or 0
    usd_diff = ((target_price - price) / price * 100) if price > 0 and target_price > 0 else 0
    
    print(f" Recommendation:       {Colors.BOLD}{rating}{Colors.RESET}")
    print(f" Mean Target Price:    ₹{target_price:,.2f} ({usd_diff:+.1f}%)")
    print(f" Analyst Coverage:     {analysts} institutions")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*50}{Colors.RESET}\n")

async def analyze_stock(symbol: str) -> None:
    print(f"Fetching comprehensive data for {Colors.BOLD}{symbol}{Colors.RESET}...")
    try:
        data = await get_stock_data(symbol)
    except Exception as e:
        print(f"{Colors.FAIL}❌ Critical API Error while fetching data: {e}{Colors.RESET}")
        return

    if not data:
        print(f"{Colors.FAIL}❌ Failed to fetch data. Verify ticker symbol ({symbol}) and network.{Colors.RESET}")
        return

    try:
        score_data = calculate_institutional_score(data)
        if not isinstance(score_data, dict):
            score_data = {"total_score": float(score_data)}
    except Exception as e:
        print(f"{Colors.WARNING}⚠️ Warning: Error calculating institutional score: {e}{Colors.RESET}")
        score_data = {"total_score": 0.0}

    display_report(symbol, data, score_data)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Institutional Grade Stock Analyzer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("symbol", type=str, nargs="?", default="SAKSOFT.NS",
                        help="Stock ticker symbol (e.g., RELIANCE.NS)")
    args = parser.parse_args()
    
    try:
        asyncio.run(analyze_stock(args.symbol.upper()))
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Analysis aborted by user.{Colors.RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()

