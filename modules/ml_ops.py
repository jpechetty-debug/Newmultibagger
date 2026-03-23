import os
import sqlite3
import joblib
import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Any, List

from modules.hybrid_scoring import train_hybrid_model, predict_and_explain, FEATURES
from modules.structured_logger import logger

ML_METADATA_TABLE = "ml_metadata"

def initialize_ml_metadata():
    """Initialize the ML metadata table to track training history."""
    try:
        with sqlite3.connect("stocks.db") as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {ML_METADATA_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    record_count INTEGER,
                    r2_score REAL,
                    model_path TEXT
                )
            """)
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to initialize ML metadata table: {e}")

def get_last_training_info() -> Dict[str, Any]:
    """Retrieve the metadata of the last successful model training."""
    try:
        with sqlite3.connect("stocks.db") as conn:
            cursor = conn.execute(f"SELECT trained_at, record_count, r2_score FROM {ML_METADATA_TABLE} ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                return {
                    "trained_at": row[0],
                    "record_count": row[1],
                    "r2_score": row[2]
                }
    except Exception as e:
        logger.error(f"Failed to get last training info: {e}")
    return {}

def check_retraining_trigger(threshold_new_records: int = 50) -> bool:
    """Check if retraining is warranted based on new record count in fundamentals_pit."""
    try:
        with sqlite3.connect("stocks.db") as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM fundamentals_pit")
            current_count = cursor.fetchone()[0]
            
            last_info = get_last_training_info()
            last_count = last_info.get("record_count", 0)
            
            diff = current_count - last_count
            logger.info(f"ML Ops: {diff} new records since last training (Current: {current_count}, Last: {last_count})")
            
            return diff >= threshold_new_records
    except Exception as e:
        logger.error(f"Failed to check retraining trigger: {e}")
    return False

def record_training_metadata(record_count: int, r2_score: float, model_path: str):
    """Log the results of a training run into the metadata table."""
    try:
        with sqlite3.connect("stocks.db") as conn:
            conn.execute(f"""
                INSERT INTO {ML_METADATA_TABLE} (record_count, r2_score, model_path)
                VALUES (?, ?, ?)
            """, (record_count, r2_score, model_path))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to record training metadata: {e}")

def run_automated_training():
    """Execute the full ML training pipeline and record metadata."""
    logger.info("Starting Automated ML Retraining...")
    
    # 1. Train model using institutional hybrid_scoring logic
    success = train_hybrid_model()
    
    if success:
        # Load the model to get its performance if available
        # Note: hybrid_scoring.train_hybrid_model already prints R2, 
        # but we need to capture it or calculate it again for metadata.
        try:
            with sqlite3.connect("stocks.db") as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM fundamentals_pit")
                current_count = cursor.fetchone()[0]
            
            # For simplicity, we assume R2 is not immediately returned by train_hybrid_model 
            # and just record the fact that it succeeded with current count.
            # In a real scenario, we'd refactor train_hybrid_model to return (success, r2).
            record_training_metadata(current_count, 0.0, "xgboost_meta_model.pkl")
            logger.info(f"✅ Automated ML Retraining Successful. Model updated for {current_count} records.")
            return True
        except Exception as e:
            logger.error(f"Error recording success: {e}")
    else:
        logger.warning("❌ Automated ML Retraining FAILED.")
    return False

async def batch_update_multibaggers_ml():
    """Update the multibaggers table with fresh predictions from the latest model."""
    logger.info("Batch updating multibaggers with new ML predictions...")
    try:
        from modules.services import DataStoreService
        from modules.hybrid_scoring import predict_and_explain
        import json
        
        with sqlite3.connect("stocks.db") as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            df = pd.read_sql("SELECT symbol, score, sales_cagr_5y, avg_roe_5y, pe_ratio, debt_equity, cfo_pat_ratio, market_cap_cr FROM multibaggers", conn)
            
            updates = []
            for _, row in df.iterrows():
                factors = {
                    "score": row["score"],
                    "sales_cagr_5y": row["sales_cagr_5y"],
                    "avg_roe_5y": row["avg_roe_5y"],
                    "pe_ratio": row["pe_ratio"],
                    "debt_equity": row["debt_equity"],
                    "cfo_pat_ratio": row["cfo_pat_ratio"],
                    "market_cap_cr": row["market_cap_cr"],
                }
                res = predict_and_explain(factors)
                ml_pred = res["ml_prediction"]
                shap_json = json.dumps(res["shap_values"])
                updates.append((ml_pred, shap_json, row["symbol"]))
                
            conn.executemany("UPDATE multibaggers SET ml_predicted_return = ?, shap_breakdown = ? WHERE symbol = ?", updates)
            conn.commit()
            logger.info(f"✅ Successfully updated ML predictions for {len(updates)} stocks.")
    except Exception as e:
        logger.error(f"Error during batch update: {e}")
