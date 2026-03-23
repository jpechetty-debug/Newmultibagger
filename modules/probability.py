import numpy as np

class MultibaggerProbabilityModel:
    """
    Phase 15: Logistic Regression Model to predict Multibagger Probability.
    
    In a full production environment, this would load a 'model.pkl' trained on 
    10 Years of historical data (X=Attributes, Y=1 if stock did 3x).
    
    Here, we use a "Synthetically Trained" model with weights derived from 
    investment principles (mimicking a trained model).
    """
    
    def __init__(self):
        # "Learned" Coefficients (Synthetic based on factor efficacy)
        # Formula: Z = Intercept + (W1*Growth) + (W2*ROE) + ...
        # Prob = 1 / (1 + e^-Z)
        
        self.intercept = -4.5 # Base probability is low (most stocks don't multibag)
        
        self.weights = {
            "Sales_Growth": 0.08,   # High growth = High impact
            "ROE": 0.05,            # Quality matters
            "F_Score": 0.20,        # Financial strength step function
            "RS_Rating": 1.50,      # Momentum is a huge predictor
            "Debt_Equity": -0.80,   # Debt kills multibaggers
            "Margins_Expanding": 0.50, # Bonus for trend
            "Inst_Holding": 0.03    # Smart money validation
        }
        
    def predict_proba(self, features):
        """
        Returns probability (0.0 to 1.0) of being a Multibagger (3x in 5yr).
        features: dict of stock attributes
        """
        z = self.intercept
        
        # 1. Sales Growth (Capped at 50% to prevent outliers skewing)
        g = min(features.get("Sales_Growth_TTM%", 0), 50)
        z += g * self.weights["Sales_Growth"]
        
        # 2. ROE (Capped at 40)
        roe = min(features.get("ROE%", 0), 40)
        z += roe * self.weights["ROE"]
        
        # 3. F-Score (0-9)
        f = features.get("F_Score", 0)
        z += f * self.weights["F_Score"]
        
        # 4. Relative Strength
        rs = features.get("RS_Rating", 0)
        z += rs * self.weights["RS_Rating"]
        
        # 5. Debt (Penalize high debt)
        de = min(features.get("Debt_Equity", 0), 3)
        z += de * self.weights["Debt_Equity"]
        
        # 6. Margin Trend
        if features.get("Margin_Trend", False):
            z += self.weights["Margins_Expanding"]
            
        # 7. Institutional Holding
        inst = min(features.get("Inst_Holding%", 0), 40)
        z += inst * self.weights["Inst_Holding"]
        
        # Logistic Function: 1 / (1 + e^-z)
        prob = 1 / (1 + np.exp(-z))
        
        return round(prob * 100, 1) # Return as percentage

# Export a singleton
model_v1 = MultibaggerProbabilityModel()

def get_multibagger_probability(stock_data):
    """Wrapper to predict using the probability model."""
    try:
        return model_v1.predict_proba(stock_data)
    except:
        return 0.0
