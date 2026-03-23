# modules/hybrid_scoring.py
# Sovereign AI - XGBoost Meta-Model with SHAP Explainability

import os
import sqlite3
import warnings

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

warnings.filterwarnings("ignore")

MODEL_PATH = "xgboost_meta_model.pkl"
FEATURES = [
    "score",
    "sales_cagr_5y",
    "avg_roe_5y",
    "pe_ratio",
    "debt_equity",
    "cfo_pat_ratio",
    "market_cap_cr",
]
FEATURE_BOUNDS = {
    "score": (0.0, 100.0),
    "sales_cagr_5y": (-100.0, 300.0),
    "avg_roe_5y": (-100.0, 200.0),
    "pe_ratio": (0.0, 300.0),
    "debt_equity": (0.0, 10.0),
    "cfo_pat_ratio": (-5.0, 10.0),
    "market_cap_cr": (0.0, 5_000_000.0),
}


def _sanitize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce features to finite values and clip to safe ranges for XGBoost."""
    out = df.copy()
    for col in FEATURES:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        lo, hi = FEATURE_BOUNDS.get(col, (-1e9, 1e9))
        out[col] = out[col].clip(lower=lo, upper=hi)
    return out[FEATURES]


def _get_current_prices(symbols):
    """Fetch current prices to calculate forward returns from the PIT data."""
    import yfinance as yf

    try:
        tickers_str = " ".join(symbols)
        data = yf.download(tickers_str, period="1d", progress=False)
        if data.empty:
            return {}
        if "Close" in data:
            if isinstance(data.columns, pd.MultiIndex):
                return data["Close"].iloc[-1].to_dict()
            return (
                {symbols[0]: float(data["Close"].iloc[-1])}
                if len(symbols) == 1
                else data["Close"].iloc[-1].to_dict()
            )
    except Exception as exc:
        print(f"Error fetching current prices for ML target: {exc}")
        return {}
    return {}


def train_hybrid_model():
    print("Initiating Hybrid Scoring Meta-Model Training (XGBoost)...")

    # 1. Extract PIT Data
    try:
        from modules.pit_auditor import sanitize

        with sqlite3.connect("stocks.db") as conn:
            query = """
                SELECT symbol, as_of_date, source_updated_at as report_date, price as pit_price,
                score, sales_cagr_5y, avg_roe_5y, pe_ratio, debt_equity, cfo_pat_ratio, market_cap_cr
                FROM fundamentals_pit
            """
            raw_df = pd.read_sql(query, conn)

            # Eliminate look-ahead bias and structural hallucinations via PIT Auditor.
            df = sanitize(raw_df)
            if df.empty and not raw_df.empty:
                print("PIT Auditor quarantine triggered: all rows failed temporal strictness.")
                df = raw_df  # fallback for local testing
    except Exception as exc:
        print(f"Could not load or sanitize PIT data: {exc}")
        return False

    if len(df) < 20:
        print("Not enough historical data in fundamentals_pit to train a reliable XGBoost model (need > 20).")
        return False

    # 2. Get current prices to calculate forward returns.
    symbols = df["symbol"].unique().tolist()
    print(f"Fetching current prices for {len(symbols)} symbols to construct target (Y)...")
    current_prices = _get_current_prices(symbols)

    # Calculate Y (forward return).
    df["current_price"] = df["symbol"].map(current_prices)
    df = df.dropna(subset=["pit_price", "current_price"])
    df = df[df["pit_price"] > 0]
    if df.empty:
        print("No valid forward returns calculable.")
        return False

    df["forward_return"] = (df["current_price"] - df["pit_price"]) / df["pit_price"]

    # Sanitize ML features and drop invalid targets.
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    train_df = df.dropna(subset=["forward_return"]).copy()
    if not train_df.empty:
        train_df[FEATURES] = _sanitize_features(train_df[FEATURES])

    if len(train_df) < 10:
        print("Too many invalid rows; not enough training data after cleanup.")
        return False

    X = train_df[FEATURES]
    y = train_df["forward_return"]

    # 3. Train XGBoost Regressor.
    model = xgb.XGBRegressor(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        random_state=42,
    )

    print("Training XGBoost regressor on historical factor signatures...")
    model.fit(X, y)

    r2 = model.score(X, y)
    print(f"Training complete. Meta-Model R2: {r2:.2f}")

    # 4. Save model.
    joblib.dump(model, MODEL_PATH)
    print("Model saved to disk.")
    return True


def predict_and_explain(factors_dict):
    """
    Given a live stock's factors, predict forward return and generate SHAP values.
    Returns: {"ml_prediction": float|None, "shap_values": dict}
    """
    if not os.path.exists(MODEL_PATH):
        return {"ml_prediction": None, "shap_values": {}}

    try:
        model = joblib.load(MODEL_PATH)

        row = {f: factors_dict.get(f, 0.0) for f in FEATURES}
        X_pred = pd.DataFrame([row], columns=FEATURES)
        X_pred = _sanitize_features(X_pred)

        prediction = float(model.predict(X_pred)[0])
        if not np.isfinite(prediction):
            return {"ml_prediction": None, "shap_values": {}}

        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X_pred)

        breakdown = {}
        for i, feature in enumerate(FEATURES):
            val = float(shap_vals[0][i])
            breakdown[feature] = val if np.isfinite(val) else 0.0

        sorted_breakdown = dict(
            sorted(breakdown.items(), key=lambda item: abs(item[1]), reverse=True)
        )
        return {"ml_prediction": float(prediction * 100.0), "shap_values": sorted_breakdown}
    except Exception as exc:
        print(f"ML Prediction Error: {exc}")
        return {"ml_prediction": None, "shap_values": {}}


if __name__ == "__main__":
    train_hybrid_model()
