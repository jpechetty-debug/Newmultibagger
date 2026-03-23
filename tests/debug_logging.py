import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.risk import RiskGovernor

print("[DEBUG] importing RiskGovernor")
try:
    rg = RiskGovernor()
    print("[DEBUG] calling log_rejected_trade")
    rg.log_rejected_trade("DEBUG_TEST", "Testing logging", 123.45)
    print("[DEBUG] success")
except Exception as e:
    print(f"[DEBUG] ERROR: {e}")
