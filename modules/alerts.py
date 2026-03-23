import pandas as pd
import datetime

class AlertEngine:
    """
    Monitors the portfolio for Risk Events and Thesis Breaks.
    """
    
    def __init__(self):
        self.thesis_break_score = 60
        self.stop_loss_pct = 0.10 # 10% Trailing? Or fixed? Let's use the Stop_Loss column if available.
        
    def check_portfolio(self, portfolio, current_prices, current_scores):
        """
        Scans all open positions for alerts.
        
        Args:
            portfolio (pd.DataFrame): Must contain 'Symbol', 'Entry_Price', 'Stop_Loss'.
            current_prices (dict): Symbol -> Current Price
            current_scores (dict): Symbol -> Current Score
            
        Returns:
            list of dict: List of alert objects.
        """
        alerts = []
        
        if portfolio.empty:
            return alerts
            
        for index, row in portfolio.iterrows():
            symbol = row['Symbol']
            entry_price = row.get('Entry_Price', 0)
            stop_loss = row.get('Stop_Loss', 0)
            
            curr_price = current_prices.get(symbol, 0)
            curr_score = current_scores.get(symbol, 0)
            
            if curr_price == 0: continue
            
            # 1. Check Stop Loss
            # If Stop Loss is defined and Current Price < Stop Loss
            if stop_loss > 0 and curr_price < stop_loss:
                alerts.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "symbol": symbol,
                    "type": "STOP_LOSS",
                    "priority": "CRITICAL",
                    "message": f"Price ({curr_price}) crossed Stop Loss ({stop_loss}). Exit immediately."
                })
                
            # 2. Check Thesis Break (Score Drift)
            # If Score drops below 60 (Institutional Minimum)
            if curr_score < self.thesis_break_score:
                alerts.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "symbol": symbol,
                    "type": "THESIS_BREAK",
                    "priority": "HIGH",
                    "message": f"Institutional Score dropped to {curr_score} (Below {self.thesis_break_score}). Fundamental/Momentum deterioration."
                })
                
            # 3. Check Price Drift (Crash Alert)
            # If Price drops > 5% in a day (Mock check: assuming Entry as Ref for now, ideally Day Open)
            # Let's check Drop from Entry for now as a proxy if Day Open unavailable
            drop_from_entry = (curr_price - entry_price) / entry_price
            if drop_from_entry < -0.08 and stop_loss == 0: # 8% Drop and no stop loss? Alert.
                 alerts.append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "symbol": symbol,
                    "type": "PRICE_DRIFT",
                    "priority": "MEDIUM",
                    "message": f"Down {drop_from_entry:.1%} from Entry. Review position."
                })

        return alerts
