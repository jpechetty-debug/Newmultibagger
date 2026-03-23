import asyncio
import inspect
from typing import Any, Awaitable, Callable, Optional, Sequence


DEFAULT_BACKOFF_SECONDS: Sequence[float] = (2.0, 4.0, 8.0)


def is_rate_limited_error(exc: Exception) -> bool:
    message = str(exc).lower()
    patterns = (
        "too many requests",
        "rate limited",
        "rate limit",
        "429",
        "throttl",
    )
    return any(pattern in message for pattern in patterns)


async def run_with_exponential_backoff(
    operation: Callable[[], Any],
    *,
    context: str = "",
    retry_delays: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
    should_retry: Optional[Callable[[Exception], bool]] = None,
) -> Any:
    """
    Execute an operation with deterministic exponential backoff.
    Retry schedule: 2s -> 4s -> 8s (default).
    """
    retry_check = should_retry or is_rate_limited_error
    retries = len(retry_delays)

    for attempt in range(retries + 1):
        try:
            result = operation()
            if inspect.isawaitable(result):
                return await result  # type: ignore[no-any-return]
            return result
        except Exception as exc:
            if attempt >= retries or not retry_check(exc):
                raise

            wait = float(retry_delays[attempt])
            if context:
                print(f"{context} rate-limited. Retrying in {wait:.0f}s.")
            await asyncio.sleep(wait)

    raise RuntimeError("Retry loop exited unexpectedly")
