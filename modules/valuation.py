import numpy as np

class ValuationEngine:
    def __init__(self, data):
        """
        Initialize with financial data dictionary.
        Required keys:
        - current_price: float
        - eps_ttm: float
        - book_value_per_share: float
        - free_cash_flow_per_share: float
        - growth_rate_5y: float (percentage, e.g., 15.0)
        - beta: float (optional, default 1.0)
        """
        self.data = data
        self.risk_free_rate = 0.07  # India 10Y Bond Yield approx
        self.market_return = 0.12   # Expected Nifty Return
        
    def calculate_dcf(self, projection_years=10, terminal_growth=0.04):
        """
        Discounted Cash Flow (DCF) Model.
        """
        try:
            fcf = self.data.get('free_cash_flow_per_share', 0)
            growth_rate = self.data.get('growth_rate_5y', 10) / 100.0
            beta = self.data.get('beta', 1.0)
            
            # Cap extreme growth rates for conservatism
            growth_rate = min(growth_rate, 0.20)
            
            # Calculate WACC (Cost of Equity via CAPM)
            # Cost of Equity = Rf + Beta(Rm - Rf)
            discount_rate = self.risk_free_rate + beta * (self.market_return - self.risk_free_rate)
            
            # Simple 2-stage DCF
            future_cash_flows = []
            for i in range(1, projection_years + 1):
                # Decay growth rate linearly to terminal growth
                # current_growth = growth_rate - ((growth_rate - terminal_growth) * (i / projection_years))
                # Let's keep it simple: First 5 years high growth, next 5 linear decay
                if i <= 5:
                    g = growth_rate
                else:
                    g = growth_rate - ((growth_rate - terminal_growth) * ((i - 5) / 5))
                
                fcf = fcf * (1 + g)
                future_cash_flows.append(fcf)
                
            # Terminal Value
            terminal_value = (future_cash_flows[-1] * (1 + terminal_growth)) / (discount_rate - terminal_growth)
            
            # Discount everything back
            dcf_value = 0
            for i, cash_flow in enumerate(future_cash_flows):
                dcf_value += cash_flow / ((1 + discount_rate) ** (i + 1))
                
            dcf_value += terminal_value / ((1 + discount_rate) ** projection_years)
            return round(dcf_value, 2)
            
        except Exception:
            return 0.0

    def calculate_graham_number(self):
        """
        Graham Number = Sqrt(22.5 * EPS * BVPS)
        """
        try:
            eps = self.data.get('eps_ttm', 0)
            bvps = self.data.get('book_value_per_share', 0)
            
            if eps < 0 or bvps < 0:
                return 0.0
                
            graham_num = np.sqrt(22.5 * eps * bvps)
            return round(graham_num, 2)
        except Exception:
            return 0.0

    def calculate_epv_proxy(self):
        """
        Earnings Power Value Proxy.
        Approximated as EPS * (1 / Cost of Capital) for zero-growth scenario.
        """
        try:
            eps = self.data.get('eps_ttm', 0)
            beta = self.data.get('beta', 1.0)
            cost_of_capital = self.risk_free_rate + beta * (self.market_return - self.risk_free_rate)
            
            epv = eps / cost_of_capital
            return round(epv, 2)
        except Exception:
            return 0.0

    def get_intrinsic_value(self):
        """
        Returns consensus intrinsic value and margin of safety.
        """
        price = self.data.get('current_price', 0)
        dcf = self.calculate_dcf()
        graham = self.calculate_graham_number()
        epv = self.calculate_epv_proxy()
        
        # Weighted Consensus
        # Graham is often too conservative for growth stocks, DCF too sensitive.
        # Let's verify valid values first
        valid_models = []
        if dcf > 0: valid_models.append(dcf)
        if graham > 0: valid_models.append(graham)
        # EPV is strictly no-growth, useful floor
        
        if not valid_models:
            return {
                "intrinsic_value": 0,
                "margin_of_safety": 0,
                "components": {"dcf": 0, "graham": 0, "epv": 0},
                "verdict": "UNKNOWN"
            }
            
        consensus = sum(valid_models) / len(valid_models)
        
        # Margin of Safety
        mos = ((consensus - price) / consensus) * 100 if consensus > 0 else 0
        
        verdict = "FAIRLY VALUED"
        if mos > 20: verdict = "UNDERVALUED"
        elif mos < -20: verdict = "OVERVALUED"
        
        return {
            "intrinsic_value": round(consensus, 2),
            "margin_of_safety": round(mos, 1),
            "components": {
                "dcf": dcf,
                "graham": graham,
                "epv": epv
            },
            "verdict": verdict
        }
