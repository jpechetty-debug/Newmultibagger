
"""
Super Investor Registry
-----------------------
Tracks high-conviction holdings of renowned Indian super-investors.
This acts as a "Cloning Source" for the Conviction Engine.

NOTE: This registry should be updated quarterly based on shareholding patterns.
"""

SUPER_INVESTORS = {
    "DOLLY_KHANNA": {
        "style": "Momentum + Value in Smallcaps",
        "holdings": [
            "CPSEETF.NS", "CHENNPETRO.NS", "MANGCHEFER.NS", "ZUARIIND.NS",
            "UJJIVANSFB.NS", "KCP.NS", "NITINSPIN.NS", "RAIN.NS",
            "SOMATEX.NS", "TINPLATE.NS"
        ]
    },
    "ASHISH_KACHOLIA": {
        "style": "High Growth Small/Midcaps",
        "holdings": [
            "GRAVITA.NS", "FSL.NS", "LUMAXIND.NS", "SAFARI.NS",
            "GARFIBRES.NS", "PCBL.NS", "AMIORG.NS", "YASHO.NS",
            "ADORWELD.NS", "BRANDCONC.NS"
        ]
    },
    "VIJAY_KEDIA": {
        "style": "Turnaround + Niche Management",
        "holdings": [
            "TEJASNET.NS", "ELECON.NS", "VAIBHAVGBL.NS", "MAHLOG.NS",
            "SUDARSCHEM.NS", "REPRO.NS", "LYKALABS.NS"
        ]
    },
    "MUKUL_AGRAWAL": {
        "style": "Aggressive Growth / Defense / Rail",
        "holdings": [
            "NEULANDLAB.NS", "ZEELEARN.NS", "PDS.NS", "RAYMOND.NS",
            "PARAMOUNT.NS", "DWARKESH.NS", "WHEELS.NS"
        ]
    },
    "SUNIL_SINGHANIA": {
        "style": "Institutional Quality at Fair Price",
        "holdings": [
            "HINDWAREAP.NS", "MASTEK.NS", "ROUTE.NS", "IONEXCHANG.NS",
            "CMSINFO.NS", "TECHNOE.NS", "PIXTRANS.NS"
        ]
    }
}

def get_super_investor_interest(symbol):
    """
    Returns a list of investors holding the stock.
    Example: ['DOLLY_KHANNA', 'VIJAY_KEDIA']
    """
    interested_investors = []
    symbol = symbol.upper()
    
    # Normalize symbol (handle .NS extension)
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol_ns = f"{symbol}.NS"
    else:
        symbol_ns = symbol

    for investor, data in SUPER_INVESTORS.items():
        # Check both raw and NS versions
        if symbol in data['holdings'] or symbol_ns in data['holdings']:
            interested_investors.append(investor)
            
    return interested_investors
