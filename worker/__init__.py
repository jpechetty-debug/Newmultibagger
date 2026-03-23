# worker/__init__.py
"""
Sovereign AI Trading Engine v4.0 — Distributed Worker Package
Provides Redis-backed Celery workers for horizontal scaling of:
  - Stock screening & scoring
  - ML inference (XGBoost + SHAP)
  - LLM thesis generation
  - Backtest execution
"""
