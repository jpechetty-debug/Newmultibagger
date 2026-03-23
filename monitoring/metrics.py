"""
monitoring/metrics.py
─────────────────────
Custom Prometheus metrics for the Sovereign AI Trading Engine.

Usage
-----
Import this module in main.py (after the Instrumentator setup) to register
all business-level metrics:

    from monitoring.metrics import (
        SCAN_DURATION, SCAN_STOCKS_TOTAL, SCORE_HISTOGRAM,
        REGIME_STATE, KILL_SWITCH_ACTIVE, record_scan_result,
    )

Then call the helpers at the appropriate points in the pipeline.

Metrics exposed
---------------
sovereign_scan_duration_seconds   histogram — full scan wall-clock time
sovereign_stocks_scanned_total    counter   — stocks processed per scan, by outcome
sovereign_score_distribution      histogram — per-stock scores (buckets 0–100)
sovereign_regime_state            gauge     — current regime as a labelled gauge
sovereign_kill_switch_active      gauge     — 1 if kill switch is active, 0 otherwise
sovereign_celery_task_duration_s  histogram — Celery task latency by task name
sovereign_data_quality_score      histogram — DQ scores per ticker
"""

from __future__ import annotations

import time
import functools
from contextlib import contextmanager
from typing import Callable

try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary,
        REGISTRY, CollectorRegistry,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


# ── Helpers that degrade gracefully when prometheus_client isn't installed ───

class _Noop:
    """No-op stand-in for any prometheus_client object."""
    def labels(self, **_):      return self
    def observe(self, *_):      pass
    def inc(self, *_):          pass
    def set(self, *_):          pass
    def time(self):             return _noop_ctx()

class _noop_ctx:
    def __enter__(self): return self
    def __exit__(self, *_): pass

def _make(cls, *args, **kwargs):
    if not _PROMETHEUS_AVAILABLE:
        return _Noop()
    try:
        return cls(*args, **kwargs)
    except ValueError:
        # Already registered (happens on hot-reload)
        return REGISTRY._names_to_collectors.get(args[0], _Noop())


# ── Metric definitions ────────────────────────────────────────────────────────

SCAN_DURATION: Histogram = _make(
    Histogram,
    "sovereign_scan_duration_seconds",
    "Wall-clock time for a full universe scan",
    buckets=[30, 60, 120, 300, 600, 900, 1800, 3600],
)

SCAN_STOCKS_TOTAL: Counter = _make(
    Counter,
    "sovereign_stocks_scanned_total",
    "Stocks processed per scan run",
    ["outcome"],           # labels: success | error | skipped | cached
)

SCORE_HISTOGRAM: Histogram = _make(
    Histogram,
    "sovereign_score_distribution",
    "Distribution of institutional scores (0–100)",
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)

REGIME_STATE: Gauge = _make(
    Gauge,
    "sovereign_regime_state",
    "Current market regime (1=active regime, 0=inactive)",
    ["regime"],            # labels: BULL | BEAR | SIDEWAYS | QUALITY
)

KILL_SWITCH_ACTIVE: Gauge = _make(
    Gauge,
    "sovereign_kill_switch_active",
    "1 if the VIX/drawdown kill switch is currently active",
)

CELERY_TASK_DURATION: Histogram = _make(
    Histogram,
    "sovereign_celery_task_duration_seconds",
    "Celery task latency",
    ["task_name"],
    buckets=[0.1, 0.5, 1, 5, 15, 30, 60, 120, 300],
)

DATA_QUALITY_SCORE: Histogram = _make(
    Histogram,
    "sovereign_data_quality_score",
    "Data quality scores per ticker (0–100)",
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
)

LLM_THESIS_FALLBACK: Counter = _make(
    Counter,
    "sovereign_llm_thesis_fallback_total",
    "Number of times rule-based thesis fallback was triggered",
)


# ── Convenience helpers ────────────────────────────────────────────────────────

def record_scan_result(outcome: str, score: float | None = None, dq: float | None = None):
    """
    Call after processing each stock.

    Args:
        outcome: "success" | "error" | "skipped" | "cached"
        score:   institutional score (0–100), if available
        dq:      data-quality score (0–100), if available
    """
    SCAN_STOCKS_TOTAL.labels(outcome=outcome).inc()
    if score is not None:
        SCORE_HISTOGRAM.observe(score)
    if dq is not None:
        DATA_QUALITY_SCORE.observe(dq)


def set_regime(regime: str):
    """
    Update the regime gauge. Sets active regime to 1, all others to 0.
    """
    for r in ("BULL", "BEAR", "SIDEWAYS", "QUALITY", "MOMENTUM", "VALUE"):
        REGIME_STATE.labels(regime=r).set(1 if r == regime.upper() else 0)


def set_kill_switch(active: bool):
    """Set the kill switch gauge (1=active, 0=inactive)."""
    KILL_SWITCH_ACTIVE.set(1 if active else 0)


@contextmanager
def timed_scan():
    """Context manager that records total scan duration."""
    start = time.perf_counter()
    try:
        yield
    finally:
        SCAN_DURATION.observe(time.perf_counter() - start)


def celery_task_timer(task_name: str) -> Callable:
    """
    Decorator for Celery tasks that records execution latency.

    Usage::

        from monitoring.metrics import celery_task_timer

        @app.task(name="worker.tasks.scan_single_stock")
        @celery_task_timer("scan_single_stock")
        def scan_single_stock(symbol, regime="SIDEWAYS"):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                CELERY_TASK_DURATION.labels(task_name=task_name).observe(
                    time.perf_counter() - start
                )
        return wrapper
    return decorator
