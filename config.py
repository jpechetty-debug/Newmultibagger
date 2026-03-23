# config.py
# Global Configuration State
import os
from dotenv import load_dotenv

load_dotenv()

# --- Manual Regime Override ---
# Options: 'BULL', 'BEAR', 'SIDEWAYS', or None (Auto-Pilot)
FORCED_REGIME = None

# --- API Keys ---
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "DKJO5HMH99VJTQ0C")

# --- System Settings ---
VERSION = "v3.0.2-single-user"
CAPITAL_LIMIT = 50000000  # 5 Cr pilot limit

# --- Model Integrity ---
# Hash generated from key model logic files by ScanLogger.
MODEL_VERSION = VERSION
MODEL_VERSION_HASH = "bc2a3187"

# --- Risk Limits ---
# Hard cap for aggregate exposure to a single sector (25%).
MAX_SECTOR_EXPOSURE = 0.25
# Stop new buying when VIX is above this static ceiling.
HARD_KILL_SWITCH_VIX = 35.0
# Dynamic kill-switch: weekly drawdown velocity trigger (% per week).
DRAWDOWN_RATE_KILL_WEEKLY = 5.0
# Correlation stress thresholds.
CORRELATION_REDUCE_THRESHOLD = 0.75
CORRELATION_LIQUIDATE_THRESHOLD = 0.85

# --- Quality Thresholds ---
MIN_MARKET_CAP_CR = 500  # Minimum market cap in Crores to filter illiquid nano-caps
MIN_DATA_QUALITY = 50    # Minimum % of critical data points required (0-100)
FULL_SCAN_MIN_PASS_RATIO = 0.20  # If pass rate drops below this, adapt threshold deterministically
FULL_SCAN_DQ_FLOOR = 30          # Lower bound for adaptive full-scan quality threshold
FULL_SCAN_DISABLE_ALPHA_VANTAGE = True  # Avoid AV quota/pacing collapse during full scans
MAX_VECTORBT_SYMBOLS = 200       # Cap expensive backtests in large-universe scans
MIN_HISTORY_BARS = 120           # Minimum 1Y bars required to treat fetch as valid
MIN_FETCH_CORE_FIELDS = 2        # Minimum core fields required for valid fetch
MIN_FETCH_CORE_FIELDS_BY_SOURCE = {
    "pnsea": 1,
    "nsepython": 2,
    "yfinance": 2,
    "unknown": 2,
    "fallback_failed": 3,
}
SPARSE_FUNDAMENTAL_SOURCES = ["pnsea"]  # Allow incomplete-but-not-empty fundamentals from sparse providers
SPARSE_SOURCE_MIN_CORE_FIELDS = 1
HARD_BLOCK_ZERO_VALUATION_FIELDS = True
DQ_ZERO_VALUATION_CAP = 20.0
FULL_SCAN_BASE_CONCURRENCY = 12
TARGET_SCAN_CONCURRENCY = 20
FULL_SCAN_RETRY_ENABLED = True
FULL_SCAN_RETRY_MIN_CONCURRENCY = 4
FULL_SCAN_RETRY_MAX_CONCURRENCY = 10
FULL_SCAN_RETRY_BACKOFF_SECONDS = 2.0
FULL_SCAN_RETRY_TRANSIENT_REASONS = [
    "fetch_failed",
    "fetch_exception",
    "no_price_history",
    "invalid_price",
]
IPO_SHORT_HISTORY_POLICY_ENABLE = True
IPO_SHORT_HISTORY_MIN_BARS = 90
IPO_SHORT_HISTORY_MIN_CORE_FIELDS = 4
IPO_SHORT_HISTORY_MAX_PRICE_AGE_DAYS = 7
IPO_SHORT_HISTORY_SOFT_FLAG = "short_history_ipo"
IPO_SHORT_HISTORY_DQ_PENALTY = 8.0

# --- Universe Hygiene (auto-flag invalid symbols) ---
AUTO_FLAG_INVALID_SYMBOLS = True
UNIVERSE_FLAGS_PATH = "data/universe_flags.json"
AUTO_FLAG_FAILURE_THRESHOLD = 2          # Default evidence threshold before temporary inactivation
AUTO_FLAG_COOLDOWN_DAYS = 14             # Retry after cooldown by auto-reactivating
AUTO_FLAG_MIN_SUCCESS_RATIO = 0.40       # Guardrail: do not flag aggressively during provider outages
AUTO_FLAG_MAX_NEW_INACTIVE_PER_RUN = 300 # Safety cap per run
AUTO_FLAG_REASON_THRESHOLDS = {
    "no_price_history": 1,
    "no_fundamentals": 1,
    "invalid_price": 2,
    "short_history": 4,
    "missing_core_fields": 2,
    "incomplete_fundamentals": 3,
    "zero_valuation_fields": 1,
    "fetch_exception": 3,
    "fetch_failed": 2,
}
AUTO_FLAG_WHITELIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
]

# --- Scoring Weights ---
# Weights are normalized to sum to 1.0 in each mode.
SCORING_WEIGHTS = {
    "balanced": {
        "w_sales": 0.15,
        "w_roe": 0.15,
        "w_cfo": 0.10,
        "w_val": 0.15,
        "w_eps": 0.10,
        "w_fscore": 0.10,
        "w_de": 0.10,
        "w_mom": 0.15,
    },
    "momentum": {
        "w_sales": 0.15,
        "w_roe": 0.10,
        "w_cfo": 0.05,
        "w_val": 0.05,
        "w_eps": 0.20,
        "w_fscore": 0.10,
        "w_de": 0.05,
        "w_mom": 0.30,
    },
    "value": {
        "w_sales": 0.10,
        "w_roe": 0.15,
        "w_cfo": 0.15,
        "w_val": 0.30,
        "w_eps": 0.10,
        "w_fscore": 0.10,
        "w_de": 0.10,
        "w_mom": 0.00,
    },
    "quality": {
        "w_sales": 0.10,
        "w_roe": 0.20,
        "w_cfo": 0.20,
        "w_val": 0.10,
        "w_eps": 0.10,
        "w_fscore": 0.15,
        "w_de": 0.10,
        "w_mom": 0.05,
    },
}
