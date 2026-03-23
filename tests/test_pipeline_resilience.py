import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.retry_utils import run_with_exponential_backoff
import config

class TestPipelineResilience(unittest.IsolatedAsyncioTestCase):
    """
    Standard unittest-based async tests for pipeline resilience.
    Avoids pytest-asyncio dependency issues.
    """

    async def test_retry_logic_transient_failure(self):
        """
        Verifies that the retry logic correctly handles transient failures
        and eventually succeeds if the data becomes available.
        """
        attempts = 0
        
        async def mock_operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                # Match "too many requests" pattern in retry_utils.py
                raise RuntimeError("429 Too Many Requests")
            return {"Symbol": "TEST.NS", "Price": 100}

        result = await run_with_exponential_backoff(
            mock_operation,
            context="test_worker",
            retry_delays=(0.001, 0.001), # Fast retries for testing
        )
        
        self.assertEqual(result["Symbol"], "TEST.NS")
        self.assertEqual(attempts, 3)

    async def test_retry_logic_max_retries_exhausted(self):
        """
        Verifies that the retry logic raises an error after exhausting
        all retry attempts for a persistent failure.
        """
        attempts = 0
        
        async def mock_persistent_fail():
            nonlocal attempts
            attempts += 1
            raise RuntimeError("429 Persistent Throttle")

        with self.assertRaises(RuntimeError):
            await run_with_exponential_backoff(
                mock_persistent_fail,
                context="persistent_fail",
                retry_delays=(0.001, 0.001),
            )
        
        self.assertEqual(attempts, 3) # Initial + 2 retries

    def test_config_short_history_policy(self):
        """
        Ensures that the IPO/short-history policy constants are correctly
        defined in config.py.
        """
        self.assertTrue(hasattr(config, "IPO_SHORT_HISTORY_POLICY_ENABLE"))
        self.assertGreater(config.IPO_SHORT_HISTORY_MIN_BARS, 0)
        self.assertGreaterEqual(config.IPO_SHORT_HISTORY_MIN_CORE_FIELDS, 2)

if __name__ == "__main__":
    unittest.main()
