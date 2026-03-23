# db/engine.py
"""
Sovereign AI Trading Engine v4.0 — Database Engine Layer
Provides dual-mode database connectivity:
  - PostgreSQL/TimescaleDB (production) via async SQLAlchemy
  - SQLite (local development) via sync SQLAlchemy
Controlled by DATABASE_URL environment variable.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from db.models import Base

# --- Configuration ---
# Production: DATABASE_URL=postgresql+psycopg://user:pass@host:5432/sovereign_db
# Local Dev:  DATABASE_URL=sqlite:///stocks.db  (or unset for default)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///stocks.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# --- Engine Factory ---
def _build_engine():
    if IS_SQLITE:
        return create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False, "timeout": 5},
            poolclass=StaticPool,
            echo=False,
        )
    else:
        return create_engine(
            DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )

engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session():
    """Yield a database session (context-managed)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_tables():
    """Create all tables from ORM models if they don't exist."""
    Base.metadata.create_all(bind=engine)
    if not IS_SQLITE:
        # Enable TimescaleDB hypertable on fundamentals_pit for time-series queries
        with engine.connect() as conn:
            try:
                conn.execute(
                    "SELECT create_hypertable('fundamentals_pit', 'created_at', "
                    "if_not_exists => TRUE, migrate_data => TRUE)"
                )
                conn.commit()
                print("TimescaleDB hypertable enabled on fundamentals_pit.")
            except Exception as e:
                print(f"TimescaleDB hypertable setup skipped: {e}")
    print(f"Database engine ready. Backend: {'PostgreSQL' if not IS_SQLITE else 'SQLite'}")


def get_engine_info() -> dict:
    """Return diagnostic info about the current database connection."""
    return {
        "url": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL,
        "backend": "PostgreSQL/TimescaleDB" if not IS_SQLITE else "SQLite/WAL",
        "pool_size": engine.pool.size() if hasattr(engine.pool, 'size') else "N/A",
    }
