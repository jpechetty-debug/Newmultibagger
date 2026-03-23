# db/models.py
"""
SQLAlchemy 2.0 ORM Models — Sovereign AI Trading Engine v4.0
Mirrors the existing SQLite schema for seamless PostgreSQL/TimescaleDB migration.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Text, DateTime, CheckConstraint,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Multibagger(Base):
    __tablename__ = "multibaggers"

    symbol = Column(String, primary_key=True)
    price = Column(Float)
    sector = Column(String)
    score = Column(Integer)
    f_score = Column(Integer)
    rating = Column(String)
    buy_below = Column(Float)
    stop_loss = Column(Float)
    target_1 = Column(Float)
    target_2 = Column(Float)
    sales_growth = Column(Float)
    roe = Column(Float)
    peg_ratio = Column(Float)
    debt_equity = Column(Float)
    rsi = Column(Float)
    smart_money = Column(Float)
    market_cap_cr = Column(Float)
    cfo_pat_ratio = Column(Float)
    sales_cagr_5y = Column(Float)
    avg_roe_5y = Column(Float)
    pe_ratio = Column(Float)
    down_from_52w = Column(Float)
    rs_rating = Column(Float)
    earnings_accel = Column(Integer)
    sector_leader = Column(Integer)
    graham_number = Column(Float)
    value_gap = Column(Float)
    technical_signal = Column(String)
    analyst_rating = Column(String)
    analyst_upside = Column(Float)
    promoter_holding = Column(Float)
    inst_holding = Column(Float)
    atr = Column(Float)
    stop_loss_atr = Column(Float)
    max_qty_1l = Column(Float)
    as_of_date = Column(String)
    last_audited = Column(DateTime)
    updated_at = Column(DateTime)
    conviction_score = Column(Float)
    conviction_boost = Column(Float)
    institutional_interest = Column(Integer)
    super_investors = Column(Text)
    data_quality = Column(Float)
    data_confidence = Column(Float)
    f_score_method = Column(String)
    backtest_cagr = Column(Float)
    backtest_win_rate = Column(Float)
    backtest_max_dd = Column(Float)
    backtest_sharpe = Column(Float)
    ml_predicted_return = Column(Float)
    shap_breakdown = Column(Text)

    __table_args__ = (
        CheckConstraint("pe_ratio >= -100 AND pe_ratio <= 1000"),
        CheckConstraint("roe >= -500 AND roe <= 500"),
        CheckConstraint("score >= 0 AND score <= 100"),
    )


class FundamentalsPIT(Base):
    __tablename__ = "fundamentals_pit"

    symbol = Column(String, primary_key=True)
    as_of_date = Column(String, primary_key=True)
    price = Column(Float)
    sector = Column(String)
    score = Column(Integer)
    sales_cagr_5y = Column(Float)
    avg_roe_5y = Column(Float)
    pe_ratio = Column(Float)
    debt_equity = Column(Float)
    market_cap_cr = Column(Float)
    cfo_pat_ratio = Column(Float)
    source_updated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_fundamentals_pit_as_of_date", "as_of_date"),
    )


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey("multibaggers.symbol"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    total_score = Column(Float)
    close_price = Column(Float)
    pe_ratio = Column(Float)


class FactorPenalty(Base):
    __tablename__ = "factor_penalties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey("multibaggers.symbol"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    penalty_name = Column(String)
    penalty_value = Column(Float)


class ValuationMetric(Base):
    __tablename__ = "valuation_metrics"

    symbol = Column(String, ForeignKey("multibaggers.symbol"), primary_key=True)
    dcf_value = Column(Float)
    graham_value = Column(Float)
    epv_value = Column(Float)
    intrinsic_value = Column(Float)
    margin_of_safety = Column(Float)
    verdict = Column(String)
    confidence_score = Column(Integer)
    as_of_date = Column(String)
    calculated_at = Column(DateTime)


class Microcap(Base):
    __tablename__ = "microcaps"

    symbol = Column(String, primary_key=True)
    price = Column(Float)
    score = Column(Integer)
    market_cap = Column(Float)
    sales_growth = Column(Float)
    promoter_holding = Column(Float)
    buy_zone = Column(String)
    stop_loss = Column(Float)
    target_1 = Column(Float)
    target_2 = Column(Float)
    updated_at = Column(DateTime)


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String)
    side = Column(String)
    expected_price = Column(Float)
    fill_price = Column(Float)
    slippage_bps = Column(Float)
    liquidity_tier = Column(String)
    regime = Column(String)
    vix = Column(Float)
    timestamp = Column(DateTime)
    source = Column(String)


class SlippageMetric(Base):
    __tablename__ = "slippage_metrics"

    tier = Column(String, primary_key=True)
    time_window = Column(String, primary_key=True)
    regime = Column(String, primary_key=True)
    p50_bps = Column(Float)
    p75_bps = Column(Float)
    p95_bps = Column(Float)
    count = Column(Integer)
    updated_at = Column(DateTime)


class BuyThesis(Base):
    __tablename__ = "buy_thesis"

    symbol = Column(String, primary_key=True)
    buy_date = Column(String)
    primary_driver = Column(String)
    revenue_growth_min = Column(Float)
    operating_margin_min = Column(Float)
    score_at_buy = Column(Float)
    checklist_passes_at_buy = Column(Integer)
    regime_at_buy = Column(String)
    raw_thesis_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
