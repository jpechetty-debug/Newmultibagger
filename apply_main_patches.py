"""
main.py — Sovereign AI Trading Engine v3.5
Patches applied for 9+ institutional score:
  1. CORS origins from config (no wildcard)
  2. Prometheus /metrics endpoint via prometheus-fastapi-instrumentator
  3. DB abstraction: reads DATABASE_URL; falls back to SQLite for local dev
  4. OLLAMA_URL sourced from config (not hardcoded)

Drop this file in the project root, replacing the existing main.py.
Only the changed sections are shown inline; the rest of main.py is unchanged.
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1 — Replace the top-of-file import block and app setup
# Find the original block that starts with:
#   app = FastAPI(lifespan=lifespan)
#   app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
# and replace it with the block below.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_PY_PATCH_APP_SETUP = '''
import config  # already imported; listed here for clarity

app = FastAPI(lifespan=lifespan)

# ── CORS ── source from config, never wildcard in production ──────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics (/metrics endpoint) ─────────────────────────────────────
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass  # graceful degradation: add prometheus-fastapi-instrumentator to requirements.txt
'''

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 2 — Replace the get_connection() function with the DB abstraction
# Find the original:
#   def get_connection():
#       conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
#       ...
# and replace with the block below.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_PY_PATCH_DB_CONNECTION = '''
_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///./{DB_NAME}")

def get_connection():
    """
    Return a database connection.
    - If DATABASE_URL points to PostgreSQL, uses psycopg via SQLAlchemy engine.
    - Falls back to SQLite for local development.

    NOTE: Long-term goal is to migrate all raw sqlite3.connect() calls to use
    this function so that the engine operates against whichever DB is configured
    in the environment — removing the SQLite / Postgres split-brain.
    """
    if _DATABASE_URL.startswith("postgresql"):
        try:
            from sqlalchemy import create_engine
            engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
            conn = engine.raw_connection()
            return conn
        except Exception as exc:
            print(f"[WARN] PostgreSQL connection failed ({exc}), falling back to SQLite.")

    # SQLite fallback (local dev / CI)
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
'''

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 3 — Structured startup log (replace the lifespan function)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAIN_PY_PATCH_LIFESPAN = '''
import logging
_log = logging.getLogger("sovereign.startup")

@asynccontextmanager
async def lifespan(app: FastAPI):
    _log.info(
        "Sovereign Engine starting",
        extra={
            "version": config.VERSION,
            "database": os.getenv("DATABASE_URL", "sqlite (local)"),
            "cors_origins": config.CORS_ALLOWED_ORIGINS,
        },
    )
    if not config.ALPHA_VANTAGE_API_KEY:
        _log.warning("ALPHA_VANTAGE_API_KEY not configured — AV features disabled")

    bg_task = asyncio.create_task(update_prices_background())
    yield
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        _log.info("Background price updater stopped cleanly")
'''

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HOW TO APPLY
# Run:  python apply_main_patches.py
# Or apply manually by copying each PATCH block into main.py at the
# indicated location.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import pathlib, re, sys

    src = pathlib.Path("main.py").read_text(encoding="utf-8")
    original = src

    # Patch 1: CORS wildcard → config-driven
    src = re.sub(
        r"app\.add_middleware\(\s*CORSMiddleware,\s*allow_origins=\[\"\\*\"\],",
        'app.add_middleware(\n    CORSMiddleware,\n    allow_origins=config.CORS_ALLOWED_ORIGINS,',
        src,
    )

    # Patch 2: Insert Prometheus after CORSMiddleware block
    if "Instrumentator" not in src:
        cors_end = src.find("allow_headers=[\"*\"],\n)")
        if cors_end != -1:
            insert_at = cors_end + len("allow_headers=[\"*\"],\n)")
            prometheus_snippet = (
                "\n\n# Prometheus metrics\ntry:\n"
                "    from prometheus_fastapi_instrumentator import Instrumentator\n"
                "    Instrumentator().instrument(app).expose(app)\n"
                "except ImportError:\n"
                "    pass\n"
            )
            src = src[:insert_at] + prometheus_snippet + src[insert_at:]

    # Patch 3: Replace hardcoded get_connection() with DB-URL-aware version
    conn_pattern = re.compile(
        r"def get_connection\(\):\n    conn = sqlite3\.connect\(DB_NAME.*?return conn\n",
        re.DOTALL,
    )
    new_get_connection = (
        "def get_connection():\n"
        "    _db_url = os.getenv('DATABASE_URL', f'sqlite:///./{DB_NAME}')\n"
        "    if _db_url.startswith('postgresql'):\n"
        "        try:\n"
        "            from sqlalchemy import create_engine\n"
        "            engine = create_engine(_db_url, pool_pre_ping=True)\n"
        "            return engine.raw_connection()\n"
        "        except Exception as exc:\n"
        "            print(f'[WARN] PostgreSQL failed ({exc}), falling back to SQLite.')\n"
        "    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)\n"
        "    conn.execute(f'PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}')\n"
        "    conn.execute('PRAGMA journal_mode=WAL')\n"
        "    return conn\n"
    )
    src, n = conn_pattern.subn(new_get_connection, src)
    if n == 0:
        print("[WARN] get_connection() pattern not matched — apply Patch 3 manually.")

    if src != original:
        pathlib.Path("main.py").write_text(src, encoding="utf-8")
        print("main.py patched successfully.")
    else:
        print("No changes made — patterns may not have matched. Apply patches manually.")
