"""
pit_auditor.py

Institutional-grade Point-In-Time (PIT) data auditor designed to eliminate look-ahead bias
from fundamental datasets used in quantitative trading engines.
"""

import sqlite3
import pandas as pd
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any

# Configure logging to securely track all PIT violations
logging.basicConfig(
    filename='pit_violations.log',
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PITAuditReport:
    """Dataclass containing the analytical results of a PIT dataset audit."""
    violation_count: int
    violation_rows: List[Dict[str, Any]] = field(default_factory=list)
    bias_risk_score: float = 0.0
    recommended_action: str = "PASS"


# Release lag mapping identifying days before reports are known to the market
release_lag_map = {
    "earnings": pd.Timedelta(days=45),
    "balance_sheet": pd.Timedelta(days=60),
    "cashflow": pd.Timedelta(days=75),
    "default": pd.Timedelta(days=45)
}


def checksum(row: pd.Series) -> str:
    """
    Computes a cryptographic SHA-256 checksum for a data row to detect 
    silent, retroactive data revisions by vendors.
    
    Args:
        row: A pandas Series representing a row of fundamental data.
        
    Returns:
        Hexadecimal SHA-256 checksum string.
    """
    # Cast entirely to string format to build an unalterable hash target
    row_str = "".join(str(val) for val in row.values)
    return hashlib.sha256(row_str.encode('utf-8')).hexdigest()


class PITDataStore:
    """
    SQLite-backed transactional store for Point-In-Time (PIT) fundamental data.
    Ensures that metric values are mathematically locked to specific 'as_of' dates.
    """
    
    def __init__(self, db_path: str = "pit_store.db"):
        self.conn = sqlite3.connect(db_path)
        self._create_schema()
        
    def _create_schema(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pit_data (
                symbol TEXT,
                metric_name TEXT,
                value REAL,
                report_date TEXT,
                as_of_date TEXT,
                source TEXT,
                checksum TEXT,
                PRIMARY KEY(symbol, metric_name, report_date, as_of_date)
            )
        ''')
        self.conn.commit()
        
    def insert_record(self, symbol: str, metric_name: str, value: float, 
                      report_date: str, as_of_date: str, source: str):
        """Inserts a tightly controlled PIT record using an auto-computed checksum."""
        row_s = pd.Series([symbol, metric_name, value, report_date, as_of_date, source])
        chksum = checksum(row_s)
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO pit_data 
            (symbol, metric_name, value, report_date, as_of_date, source, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, metric_name, value, report_date, as_of_date, source, chksum))
        self.conn.commit()

    def close(self):
        self.conn.close()


def _get_lag_for_metric(metric_name: str) -> pd.Timedelta:
    """Helper method to organically route string metric names to their expected lag."""
    metric_lower = str(metric_name).lower()
    if 'eps' in metric_lower or 'revenue' in metric_lower or 'earnings' in metric_lower:
        return release_lag_map["earnings"]
    elif 'debt' in metric_lower or 'equity' in metric_lower or 'assets' in metric_lower:
        return release_lag_map["balance_sheet"]
    elif 'cash' in metric_lower or 'cfo' in metric_lower:
        return release_lag_map["cashflow"]
    return release_lag_map["default"]


def audit_dataset(df: pd.DataFrame, feature_cols: List[str] = None) -> PITAuditReport:
    """
    Audits an entire DataFrame aggressively to detect look-ahead bias by validating 
    the `as_of_date` boundary against the `report_date` mapping and expected lag.
    
    Args:
        df: Pandas DataFrame containing 'symbol', 'report_date', 'as_of_date'
        feature_cols: Target feature definitions interacting with the metric lag.
        
    Returns:
        PITAuditReport mapping total timeline violations and qualitative risk scores.
    """
    violations = []
    
    if 'report_date' not in df.columns or 'as_of_date' not in df.columns:
        logger.error("SNAPSHOT_MISSING: DataFrame missing requested timeline columns.")
        return PITAuditReport(
            violation_count=len(df), 
            bias_risk_score=100.0, 
            recommended_action="REJECT_DATASET (SNAPSHOT_MISSING)"
        )

    df_copy = df.copy()
    try:
        df_copy['report_date'] = pd.to_datetime(df_copy['report_date'])
        df_copy['as_of_date'] = pd.to_datetime(df_copy['as_of_date'])
    except Exception as e:
        logger.error(f"Date conversion failure: {e}")
        return PITAuditReport(len(df), [], 100.0, "REJECT_DATASET (INVALID_DATES)")

    for idx, row in df_copy.iterrows():
        metric = row.get('metric_name', 'default')
        lag = _get_lag_for_metric(metric)
        
        expected_public_date = row['report_date'] + lag
        
        violation_type = None
        
        # Look-Ahead Bias: Was this explicitly known to the market?
        if row['as_of_date'] < expected_public_date:
            violation_type = "FUTURE_LEAK"
            
        # Revision Ignored: Timestamp too far ahead spanning multiple missing cycles
        elif row['as_of_date'] > expected_public_date + pd.Timedelta(days=365):
            violation_type = "REVISION_IGNORED"
            
        if violation_type:
            v_dict = row.to_dict()
            # Serialize for JSON dict structure in reporting
            v_dict['as_of_date'] = str(v_dict['as_of_date'])
            v_dict['report_date'] = str(v_dict['report_date'])
            v_dict['violation_type'] = violation_type
            v_dict['expected_public_date'] = str(expected_public_date)
            violations.append(v_dict)
            
            logger.warning(
                f"PIT VIOLATION [{violation_type}]: Symbol={row.get('symbol', 'UNK')}, "
                f"AsOf={row['as_of_date']}, Report={row['report_date']}, "
                f"Expected>={expected_public_date}"
            )

    violation_count = len(violations)
    total_rows = len(df_copy)
    
    bias_risk_score = (violation_count / total_rows * 100.0) if total_rows > 0 else 0.0
    
    action = "PASS"
    if bias_risk_score > 5.0:
        action = "QUARANTINE"
    if bias_risk_score > 20.0:
        action = "REJECT_DATASET"
        
    return PITAuditReport(
        violation_count=violation_count,
        violation_rows=violations,
        bias_risk_score=bias_risk_score,
        recommended_action=action
    )


def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes the DataFrame forcibly removing rows traversing mathematical PIT horizons.
    Drops any instance of look-ahead leakage.
    
    Args:
        df: The raw ingested observation pandas DataFrame.
        
    Returns:
        Cleaned pandas DataFrame eliminating all look-ahead bias traces.
    """
    if 'report_date' not in df.columns or 'as_of_date' not in df.columns:
        return pd.DataFrame() 
        
    df_clean = df.copy()
    try:
        report_dates = pd.to_datetime(df_clean['report_date'])
        as_of_dates = pd.to_datetime(df_clean['as_of_date'])
    except Exception:
        return pd.DataFrame()
        
    if 'metric_name' in df_clean.columns:
        lags = df_clean['metric_name'].apply(_get_lag_for_metric)
    else:
        lags = release_lag_map["default"]
        
    expected_dates = report_dates + lags
    
    # Isolate valid rows preserving strict chronological truth
    mask_valid = (as_of_dates >= expected_dates) & (as_of_dates <= expected_dates + pd.Timedelta(days=365))
    
    df_sanitized = df_clean[mask_valid].copy()
    
    dropped = len(df_clean) - len(df_sanitized)
    if dropped > 0:
        logger.info(f"Sanitization activated: dropped {dropped} structurally violating rows.")
        
    return df_sanitized
