
def normalize_symbol(symbol: str) -> str:
    """
    Centralized utility to normalize stock symbols for the Indian market.
    Handles common typos and suffixes.
    """
    if not symbol:
        return ""
        
    symbol = symbol.strip().upper()
    
    # Handle .N suffix (often used as an abbreviation for .NS)
    if symbol.endswith(".N") and not symbol.endswith(".NS"):
        symbol = symbol[:-2] + ".NS"
    
    # Ensure it ends with .NS or .BO if no suffix provided
    # Defaulting to .NS for NSE-listed stocks
    if "." not in symbol:
        symbol += ".NS"
        
    return symbol
