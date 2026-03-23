
"""
News Gate (Gate 0)
------------------
The "First Line of Defense" against Governance Failures.
Scans news headlines for critical keywords that indicate immediate existential risk.

Keywords are mostly Binary:
- Auditor Resignation -> BLOCK
- Fraud/Scam -> BLOCK
- Raid/Search -> BLOCK
- Default/Insolvency -> BLOCK

This module forces a "Guilty until Proven Innocent" approach for governance news.
"""

import re

class NewsGate:
    def __init__(self):
        # Critical Keywords that trigger immediate BLOCK
        self.KRITICAL_KEYWORDS = [
            r"auditor\s+resign",       # Auditor Resignation
            r"forensic\s+audit",       # Forensic Audit
            r"fraud",                  # General Fraud
            r"scam",                   # General Scam
            r"raid",                   # Income Tax / ED / CBI Raid
            r"search\s+and\s+seizure", # IT Raid
            r"cbi",                    # Central Bureau of Investigation
            r"enforcement\s+directorate", # ED
            r"sebi\s+order",           # Regulatory Action
            r"sebi\s+bar",             # Regulatory Ban
            r"pledge\s+invok",         # Pledge Invocation
            r"default",                # Debt Default
            r"insolvency",             # IBC
            r"bankruptcy",             # IBC
            r"nclt",                   # National Company Law Tribunal
            r"qualified\s+opinion",    # Auditor red flag
            r"adverse\s+opinion",      # Auditor red flag
            r"whistle\s?blower",       # Whistleblower complaint
            r"financial\s+irregularit" # Accounting fraud
        ]

    def validate_news(self, symbol, news_items):
        """
        Scans a list of news items for the stock.
        
        Args:
            symbol (str): Stock Symbol.
            news_items (list): List of dicts [{'title': '...', 'summary': '...'}] or strings.
            
        Returns:
            (is_clean, reason)
        """
        if not news_items:
            # No news is Good news (usually), or Data Gap.
            # We assume clean if no negative news found.
            return True, "No News Data"

        for item in news_items:
            # Handle both dict (from API) and string (simple list)
            if isinstance(item, dict):
                text = (item.get('title', '') + " " + item.get('summary', '')).lower()
            else:
                text = str(item).lower()
                
            for pattern in self.KRITICAL_KEYWORDS:
                if re.search(pattern, text):
                    # Found a critical keyword
                    detected_word = pattern.replace(r"\s+", " ").replace(r"\\", "")
                    reason = f"GOVERNANCE KILL: Found '{detected_word}' in news: {text[:50]}..."
                    return False, reason

        return True, "News Clean"
