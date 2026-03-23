from datetime import datetime, timedelta

def audit_stock_data(stock_data):
    """
    Phase 19: Performs a Data Integrity Audit on the stock data.
    Returns:
        is_clean (bool): True if data is trusted for trading.
        flags (list): List of warning issues found.
    """
    flags = []
    is_clean = True
    
    # 1. Critical Missing Data Guardrails
    # We cannot score a stock without these
    critical_fields = ["Price", "Sales_Growth_TTM%", "ROE%", "RS_Rating"]
    for field in critical_fields:
        val = stock_data.get(field)
        if val is None or val == "":
             flags.append(f"Missing {field}")
             is_clean = False
             
    # 2. Outlier / Sanity Check
    price = stock_data.get("Price", 0)
    if price <= 0:
        flags.append("Invalid Price")
        is_clean = False
        
    pe = stock_data.get("PE_Ratio", 0)
    if pe > 500:
        flags.append("PE > 500 (Outlier)")
        # Not 'dirty' but risky
        
    # 3. Data Freshness (Simulated as we don't have row-level timestamps from yf directly usually)
    # But we can check volume
    # if volume == 0, it might be a trading holiday or suspended
    # We don't have volume in the dict passed here explicitly unless we add it
    
    # 4. Sector Check
    if stock_data.get("Sector") == "Unknown":
        flags.append("Unknown Sector")
        
    # 5. Zero Values where there shouldn't be
    if stock_data.get("Market_Cap_Cr", 0) == 0:
        flags.append("Zero Market Cap")
        is_clean = False
        
    return is_clean, "; ".join(flags)
