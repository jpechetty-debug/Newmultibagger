"""
Sovereign AI Trading Engine - Indian Sector Mapping Layer
Maps broad yfinance sectors to specific Indian market classifications.
"""

# Industry mapping based on keywords in company name or yfinance industry
INDIAN_SECTOR_MAP = {
    "SPORTKING": "Textiles (Spinning)",
    "RELIANCE": "Energy / O2C",
    "TCS": "IT Services",
    "INFY": "IT Services",
    "HDFCBANK": "Banking (PVT)",
    "ICICIBANK": "Banking (PVT)",
    "SBIN": "Banking (PSU)",
    "MARUTI": "Automobile",
    "TATAMOTORS": "Automobile",
    "JINDALSTEL": "Steel",
    "TATASTEEL": "Steel",
    "ADANIENT": "Conglomerate",
}

INDUSTRY_KEYWORDS = {
    "Textile": "Textiles",
    "Spinning": "Textiles",
    "Garment": "Textiles",
    "Bank": "Financial Services",
    "Finance": "Financial Services",
    "Software": "IT Services",
    "Information Technology": "IT Services",
    "Steel": "Metals & Mining",
    "Aluminum": "Metals & Mining",
    "Metals": "Metals & Mining",
    "Pharma": "Healthcare",
    "Drug": "Healthcare",
    "Hospital": "Healthcare",
    "Construction": "Industrials",
    "Engineering": "Industrials",
    "Power": "Energy & Utilities",
    "Electric": "Energy & Utilities",
    "Telecom": "Communications",
}

def get_refined_sector(symbol: str, long_name: str, yf_sector: str, yf_industry: str) -> str:
    """
    Refines the broad yfinance sector into a more accurate Indian market classification.
    """
    # 1. Exact Symbol/LongName Match
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
    if clean_sym in INDIAN_SECTOR_MAP:
        return INDIAN_SECTOR_MAP[clean_sym]
    
    name_upper = long_name.upper()
    for key, val in INDIAN_SECTOR_MAP.items():
        if key in name_upper:
            return val
            
    # 2. Industry Keyword Match
    industry_text = (yf_industry or "").title()
    for kw, mapping in INDUSTRY_KEYWORDS.items():
        if kw in industry_text:
            return mapping
            
    # 3. Fallback to yf_sector if it's not "Unknown"
    if yf_sector and yf_sector != "Unknown":
        return yf_sector
        
    return "Unknown"
