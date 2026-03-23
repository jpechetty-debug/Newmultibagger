import os
import joblib
import pandas as pd
import numpy as np
import lightgbm as lgb
from typing import List, Dict, Any

MODEL_PATH = "multibagger_lgbm_ranker.pkl"

FEATURES = [
    "score",
    "sales_cagr_5y",
    "avg_roe_5y",
    "pe_ratio",
    "debt_equity",
    "cfo_pat_ratio",
    "market_cap_cr",
    "Ret_1M",
    "Ret_3M",
    "Ret_6M",
    "Vol_Breakout",
    "Dist_From_52W_High",
    "F_Score"
]

class LightGBMRanker:
    """
    LightGBM-based ranking engine for structural multibaggers.
    """
    def __init__(self, model_path=MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self._load_model()

    def _load_model(self):
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
            except Exception as e:
                print(f"Error loading ranker model: {e}")

    def rank_stocks(self, stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ranks a list of stocks using the trained LightGBM model.
        If no model is found, it falls back to a weighted heuristic ranking.
        """
        if not stocks:
            return []

        df = pd.DataFrame(stocks)
        
        # Ensure all features exist
        for col in FEATURES:
            if col not in df.columns:
                # Map potential alias differences
                if col == "sales_cagr_5y" and "Sales_Growth_5Y%" in df.columns:
                    df[col] = df["Sales_Growth_5Y%"]
                elif col == "avg_roe_5y" and "Avg_ROE_5Y%" in df.columns:
                    df[col] = df["Avg_ROE_5Y%"]
                elif col == "pe_ratio" and "PE_Ratio" in df.columns:
                    df[col] = df["PE_Ratio"]
                elif col == "debt_equity" and "Debt_Equity" in df.columns:
                    df[col] = df["Debt_Equity"]
                elif col == "cfo_pat_ratio" and "CFO_PAT_Ratio" in df.columns:
                    df[col] = df["CFO_PAT_Ratio"]
                elif col == "market_cap_cr" and "Market_Cap_Cr" in df.columns:
                    df[col] = df["Market_Cap_Cr"]
                elif col == "score" and "Score" in df.columns:
                    df[col] = df["Score"]
                elif col == "F_Score" and "F_Score" in df.columns:
                    df[col] = df["F_Score"]
                else:
                    df[col] = 0.0
        
        # Handle NAs
        df[FEATURES] = df[FEATURES].fillna(0.0)
        
        if self.model:
            try:
                # Predicting ranking score
                X = df[FEATURES]
                df["ml_rank_score"] = self.model.predict(X)
            except Exception as e:
                print(f"Prediction error: {e}")
                self._apply_heuristic_ranking(df)
        else:
            # Fallback to heuristic ranking if no model
            self._apply_heuristic_ranking(df)
            
        # Final Sort
        df = df.sort_values(by="ml_rank_score", ascending=False)
        return df.to_dict("records")

    def _apply_heuristic_ranking(self, df: pd.DataFrame):
        """
        Advanced heuristic ranking when ML model is absent.
        Weights:
        - Fundamental Score: 40%
        - RS (6M/3M): 30%
        - Volume Breakout: 15%
        - Proximity to 52W High: 15% (Leadership)
        """
        fundamental_norm = df["score"] / 100.0
        momentum_norm = (df["Ret_6M"] * 0.6 + df["Ret_3M"] * 0.4)
        vol_norm = np.clip(df["Vol_Breakout"], 0, 3) / 3.0
        dist_norm = 1.0 - np.clip(df["Dist_From_52W_High"], 0, 1)
        
        df["ml_rank_score"] = (
            fundamental_norm * 0.40 +
            momentum_norm * 0.30 +
            vol_norm * 0.15 +
            dist_norm * 0.15
        )

    def train(self, data: pd.DataFrame, target_col: str = "forward_return"):
        """
        Trains the LightGBM ranker.
        Target should be forward returns or binary win/loss.
        """
        if data.empty:
            return False
            
        X = data[FEATURES]
        y = data[target_col]
        
        train_data = lgb.Dataset(X, label=y)
        
        params = {
            "objective": "regression",
            "metric": "rmse",
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
            "seed": 42
        }
        
        print(f"Training LightGBM Ranker on {len(data)} samples...")
        self.model = lgb.train(params, train_data, num_boost_round=100)
        
        joblib.dump(self.model, self.model_path)
        print(f"Model saved to {self.model_path}")
        return True

if __name__ == "__main__":
    # Test/Diagnostics placeholder
    ranker = LightGBMRanker()
    print("Ranker initialized.")
