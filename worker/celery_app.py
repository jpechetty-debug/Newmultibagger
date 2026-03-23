# worker/celery_app.py
"""
Sovereign AI Trading Engine v4.0 — Celery Application Configuration
Central Celery app instance with Redis broker and result backend.

Usage:
    Start worker:   celery -A worker.celery_app worker --loglevel=info --pool=prefork -c 4
    Start beat:     celery -A worker.celery_app beat --loglevel=info
    Monitor:        celery -A worker.celery_app flower
"""
import os
from celery import Celery
from celery.schedules import crontab

# --- Redis Configuration ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_RESULT_BACKEND = os.getenv("REDIS_RESULT_BACKEND", "redis://localhost:6379/1")

# --- Celery App ---
app = Celery(
    "sovereign_worker",
    broker=REDIS_URL,
    backend=REDIS_RESULT_BACKEND,
    include=[
        "worker.tasks",
    ],
)

# --- Celery Configuration ---
app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,

    # Performance
    worker_prefetch_multiplier=1,       # Fair task distribution
    task_acks_late=True,                # Retry on worker crash
    task_reject_on_worker_lost=True,    # Re-queue if worker dies mid-task
    worker_max_tasks_per_child=50,      # Recycle workers to prevent memory leaks

    # Rate Limiting (respect API providers)
    task_default_rate_limit="10/m",     # Default: 10 tasks/minute

    # Result Expiration
    result_expires=3600,                # 1 hour

    # Retry Policy
    task_default_retry_delay=30,
    task_max_retries=3,

    # Scheduled Tasks (Beat)
    beat_schedule={
        "full-market-scan": {
            "task": "worker.tasks.run_full_scan",
            "schedule": crontab(hour="9", minute="30", day_of_week="1-5"),
            "args": (),
            "options": {"queue": "screening"},
        },
        "pit-retention-prune": {
            "task": "worker.tasks.prune_pit_data",
            "schedule": crontab(hour="2", minute="0"),
            "args": (),
            "options": {"queue": "maintenance"},
        },
        "backtest-refresh": {
            "task": "worker.tasks.run_backtest_refresh",
            "schedule": crontab(hour="6", minute="0", day_of_week="6"),
            "args": (),
            "options": {"queue": "compute"},
        },
    },

    # Task Routing
    task_routes={
        "worker.tasks.scan_single_stock": {"queue": "screening"},
        "worker.tasks.run_full_scan": {"queue": "screening"},
        "worker.tasks.generate_thesis": {"queue": "llm"},
        "worker.tasks.run_backtest_refresh": {"queue": "compute"},
        "worker.tasks.prune_pit_data": {"queue": "maintenance"},
    },
)

if __name__ == "__main__":
    app.start()
