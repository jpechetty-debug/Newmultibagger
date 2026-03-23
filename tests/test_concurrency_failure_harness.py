import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.retry_utils import run_with_exponential_backoff


def test_concurrency_failure_injection_backoff_harness():
    async def worker(idx: int):
        state = {"attempts": 0}

        def flaky_call():
            state["attempts"] += 1
            if state["attempts"] < 3:
                raise RuntimeError("429 simulated throttle")
            return idx, state["attempts"]

        return await run_with_exponential_backoff(
            flaky_call,
            context=f"worker-{idx}",
            retry_delays=(0.001, 0.001),
            should_retry=lambda exc: "429" in str(exc),
        )

    async def run_all():
        tasks = [worker(i) for i in range(10)]
        return await asyncio.gather(*tasks)

    results = asyncio.run(run_all())
    assert [item[0] for item in results] == list(range(10))
    assert all(item[1] == 3 for item in results)


def test_failure_injection_respects_retry_budget():
    attempts = {"count": 0}

    def always_fail():
        attempts["count"] += 1
        raise RuntimeError("429 persistent throttle")

    with pytest.raises(RuntimeError):
        asyncio.run(
            run_with_exponential_backoff(
                always_fail,
                retry_delays=(0.001, 0.001),
                should_retry=lambda _exc: True,
            )
        )

    # Initial call + 2 retries
    assert attempts["count"] == 3

