import pandas as pd
import config

class RiskGovernor:
    """
    The 'Sovereign' Risk Governor.
    Enforces hard limits on Capital, Sector Exposure, and Volatility.
    """
    
    def __init__(self):
        self.max_sector_exposure = config.MAX_SECTOR_EXPOSURE
        self.hard_kill_vix = config.HARD_KILL_SWITCH_VIX # Static Fallback
        self.drawdown_rate_kill_weekly = getattr(config, "DRAWDOWN_RATE_KILL_WEEKLY", 5.0)
        self.corr_reduce_threshold = getattr(config, "CORRELATION_REDUCE_THRESHOLD", 0.75)
        self.corr_liquidate_threshold = getattr(config, "CORRELATION_LIQUIDATE_THRESHOLD", 0.85)
        
        # Phase 50: Slippage Auto-Calibration
        try:
            from modules.execution_analyzer import ExecutionAnalyzer
            self.execution_analyzer = ExecutionAnalyzer()
        except ImportError:
            self.execution_analyzer = None

    def get_dynamic_slippage_bps(self, tier, theoretical_bps):
        """
        Phase 50: Returns effective slippage based on real-world p95.
        Auto-tightens if observed execution is worse than model.
        """
        if not self.execution_analyzer:
            return theoretical_bps
            
        observed_p95 = self.execution_analyzer.get_calibrated_slippage(tier)
        
        if observed_p95:
            # Safety Rule: Never go below theoretical unless validated (omitted for now)
            # We strictly take the MAX for safety.
            effective = max(theoretical_bps, observed_p95)
            if effective > theoretical_bps:
                print(f"⚠️ RISK GOVERNOR: Slippage Inflation Active for {tier}. Model: {theoretical_bps}bps -> Real: {effective:.0f}bps")
            return effective
            
        return theoretical_bps
        
    def check_kill_switch(self, current_vix, dynamic_threshold=None, drawdown_rate_weekly=None):
        """
        Hard Kill Switch: If VIX > Limit, halt all NEW buying.
        Uses Dynamic Threshold if provided, else Static.
        Returns: (is_safe, message)
        """
        if drawdown_rate_weekly is not None and drawdown_rate_weekly > self.drawdown_rate_kill_weekly:
            msg = (
                f"Kill Switch Active: Drawdown Velocity {drawdown_rate_weekly:.2f}%/week > "
                f"{self.drawdown_rate_kill_weekly:.2f}%/week"
            )
            self.log_rejected_trade("PORTFOLIO", msg, drawdown_rate_weekly)
            return False, msg

        limit = dynamic_threshold if dynamic_threshold else self.hard_kill_vix
        
        if current_vix > limit:
            self.log_rejected_trade("PORTFOLIO", f"Kill Switch Active: VIX {current_vix:.2f} > {limit:.2f}", current_vix)
            return False, f"KILL SWITCH ACTIVE: VIX ({current_vix:.2f}) > {limit:.2f}"
        return True, "Market conditions safe"

    def validate_portfolio_allocation(self, portfolio):
        """
        Checks if the proposed portfolio violates sector limits.
        
        Args:
            portfolio (list of dict): List of stocks with 'Sector' and 'Weight' (optional).
                                      If 'Weight' missing, assumes equal weight.
        """
        if not portfolio:
            return True, "Empty Portfolio"
            
        df = pd.DataFrame(portfolio)
        
        # Calculate Sector Weights
        if 'Target_Weight%' in df.columns:
            sector_weights = df.groupby('Sector')['Target_Weight%'].sum() / 100
        else:
            # Assume equal weight if not specified
            weight_per_stock = 1.0 / len(df)
            sector_weights = df['Sector'].value_counts(normalize=True)
            
        # Check Limits
        violations = []
        for sector, weight in sector_weights.items():
            if weight > self.max_sector_exposure:
                violations.append(f"{sector}: {weight:.1%} > {self.max_sector_exposure:.1%}")
                
        if violations:
            msg = f"SECTOR LIMIT BREACH: {'; '.join(violations)}"
            self.log_rejected_trade("PORTFOLIO", msg, 0.0)
            return False, msg
            
        return True, "Portfolio allocation valid"

    def calculate_max_capital_at_risk(self, total_capital, current_drawdown_pct, regime_details=None):
        """
        Level 4: Drawdown Recovery Logic (v2.9 Graduated Response)
        
        Args:
            total_capital (float): Total portfolio value.
            current_drawdown_pct (float): Current drawdown in %.
            regime_details (dict): Optional dict with 'vix' and 'regime' for context.
            
        Returns:
            float: Allowed capital deployment.
        """
        # Context extraction
        vix = 20.0
        regime = "SIDEWAYS"
        if regime_details:
            vix = regime_details.get('vix', 20.0)
            regime = regime_details.get('regime', 'SIDEWAYS')
            
        # 1. CRITICAL CRISIS (Hard Kill)
        # If DD > 15% AND Market is Panicking (VIX > 30, BEAR)
        if current_drawdown_pct > 15 and vix > 30 and regime == 'BEAR':
            print("RISK: Critical drawdown in crash mode -> HARD KILL")
            self.log_rejected_trade("PORTFOLIO", f"Hard Kill: DD {current_drawdown_pct}% + VIX {vix} (Bear)", 0.0)
            return 0.0
            
        # 2. SOFT KILL (Graduated Response)
        # If DD > 15% but Market is not broken (Normal Pullback/V-Shape)
        if current_drawdown_pct > 15:
            print("RISK: Deep drawdown -> Soft cap (50%)")
            return total_capital * 0.50
            
        # 3. WARNING ZONE
        # If DD > 10% -> Pause new entries (effectively 0 for *new* buys, but we return current cap)
        # The Orchestrator should interpret this as "Hold Existing, No New"
        # For simplicity in this function, we cap at current levels or reduced.
        if current_drawdown_pct > 10:
            print("RISK: Drawdown warning -> Capping new exposure")
            return total_capital * 0.75 # Reduce exposure slightly
            
        return total_capital

    def validate_correlation_risk(self, portfolio_avg_corr):
        """
        Level 5: Correlation Crisis Check (v2.9)
        If portfolio correlation spikes, it indicates a crash/liquidity event.
        
        Returns:
            float: Capital Reduction Factor:
                - 0.0 when lockstep correlation exceeds liquidation threshold
                - 0.8 when correlation exceeds reduction threshold
                - 1.0 otherwise
        """
        if portfolio_avg_corr > self.corr_liquidate_threshold:
            self.log_rejected_trade(
                "PORTFOLIO",
                f"Emergency Correlation {portfolio_avg_corr:.2f} > {self.corr_liquidate_threshold:.2f}",
                0.0,
            )
            print(
                f"RISK: Correlation emergency ({portfolio_avg_corr:.2f}) -> Full de-risk"
            )
            return 0.0
        elif portfolio_avg_corr > self.corr_reduce_threshold:
            self.log_rejected_trade(
                "PORTFOLIO",
                f"Crisis Correlation {portfolio_avg_corr:.2f} > {self.corr_reduce_threshold:.2f}",
                0.0,
            )
            print(
                f"RISK: Correlation spike ({portfolio_avg_corr:.2f}) -> Reducing exposure 20%"
            )
            return 0.80
        elif portfolio_avg_corr > 0.70:
            # Warning
            print(f"RISK: High correlation ({portfolio_avg_corr:.2f}) -> Monitor closely")
            return 1.0 # No portfolio-level cut, but individual penalty applies
            
        return 1.0

    def validate_var_budget(self, projected_var_pct, max_var_pct):
        """
        Pre-trade VaR gate.
        Returns: (is_safe, message)
        """
        if projected_var_pct is None:
            return True, "VaR not provided"

        if projected_var_pct > max_var_pct:
            msg = (
                f"VaR Limit Breach: {projected_var_pct:.2f}% > {max_var_pct:.2f}%"
            )
            self.log_rejected_trade("PORTFOLIO", msg, projected_var_pct)
            return False, msg
        return True, "VaR within budget"

    def get_regime_zone(self, current_vix):
        """
        Level 1: Market Regime Zoning
        Returns: (Zone Name, Capital Allocation Cap 0.0-1.0)
        """
        if current_vix < 20:
            return "GREEN", 1.0
        elif current_vix <= 25:
            return "YELLOW", 0.75
        elif current_vix <= 35:
            return "RED", 0.50
        else:
            return "BLACK", 0.0 # Total Kill Switch

        return max_size

    def check_governance_red_flags(self, stock_data):
        """
        Gate 11: Governance & Financial Integrity.
        Checks for:
        1. Debt Spikes (D/E > 2.0 except Banks)
        2. High Promoter Pledge (> 25%)
        3. Low Promoter Holding (< 10% without high inst holding)
        
        Returns: (is_safe, reason)
        """
        symbol = stock_data.get("Symbol", "Unknown")
        sector = stock_data.get("Sector", "").lower()
        
        # 1. Debt Check
        de = stock_data.get("Debt_Equity", 0)
        is_financial = "bank" in sector or "finance" in sector or "nbfc" in sector
        
        if not is_financial and de > 2.0:
            msg = f"GOVERNANCE RED FLAG: High Debt (D/E {de} > 2.0)"
            self.log_rejected_trade(symbol, msg)
            return False, msg
            
        # 2. Pledge Check
        pledge = stock_data.get("Pledge", 0) # Assuming 'Pledge' key exists or 0
        # Sometimes key might be 'Promoter_Pledge'
        
        if pledge > 25:
            msg = f"GOVERNANCE RED FLAG: Critical Pledge Levels ({pledge}%)"
            self.log_rejected_trade(symbol, msg)
            return False, msg
            
        # 3. Promoter Holding Exit
        promoter = stock_data.get("Promoter_Holding%", 0)
        inst = stock_data.get("Inst_Holding%", 0)
        
        if promoter < 5 and inst < 10: # Almost no skin in game
            msg = f"GOVERNANCE RED FLAG: Orphan Stock (Promoter {promoter}%, Inst {inst}%)"
            self.log_rejected_trade(symbol, msg)
            return False, msg
            
        return True, "Governance Clean"

    def log_rejected_trade(self, symbol, reason, price=0.0):
        """
        Phase 7: Black Box Recorder.
        Logs rejected trades/allocations to 'rejected_trades.csv'.
        
        Args:
            symbol (str): Ticker symbol or 'PORTFOLIO'
            reason (str): Why it was rejected (e.g., "Sector Cap", "Kill Switch")
            price (float): Price at rejection time (or generic value)
        """
        import csv
        import os
        from datetime import datetime
        
        file_exists = os.path.isfile('rejected_trades.csv')
        
        with open('rejected_trades.csv', 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'Symbol', 'Reason', 'Price_Context'])
                
            writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), symbol, reason, price])
        
        # Also print to console for immediate visibility
        try:
            print(f"[BLACK BOX] Rejected {symbol} -> {reason}")
        except:
            pass

