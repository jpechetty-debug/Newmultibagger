#!/usr/bin/env python3
"""
Sovereign AI Trading Engine - Unified CLI
Consolidates diagnostics, health checks, and database maintenance.
"""

import sys
import io
import argparse
import csv
from datetime import datetime
import sqlite3
import os
import asyncio
import pandas as pd

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure project modules are importable
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def get_db_connection(db_name="stocks.db"):
    conn = sqlite3.connect(db_name, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn

def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}")

async def cmd_db_stats(args):
    """Summarize database table counts and health."""
    print_header("Database Statistics")
    dbs = ["stocks.db", "pit_store.db", "data_cache.db"]
    
    for db_name in dbs:
        if not os.path.exists(db_name):
            print(f"⚠️  {db_name}: MISSING")
            continue
            
        try:
            conn = get_db_connection(db_name)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [t[0] for t in cursor.fetchall()]
            
            print(f"\n📂 {db_name}:")
            for t in tables:
                cursor.execute(f"SELECT count(*) FROM {t}")
                count = cursor.fetchone()[0]
                print(f"  {t:20}: {count} rows")
            
            # Specific check for symbols if requested
            if db_name == "stocks.db" and args.symbol:
                cursor.execute("SELECT symbol, updated_at, score FROM multibaggers WHERE symbol = ?", (args.symbol,))
                res = cursor.fetchone()
                if res:
                    print(f"\n  📍 {args.symbol}: Score={res['score']}, Updated={res['updated_at']}")
                else:
                    print(f"\n  📍 {args.symbol}: Not found in multibaggers")
            
            conn.close()
        except Exception as e:
            print(f"  ❌ Error reading {db_name}: {e}")

async def cmd_regime(args):
    """Check current market regime and factor votes."""
    print_header("Market Regime Diagnostic")
    try:
        from modules.market_data import MarketDataProvider
        provider = MarketDataProvider()
        result = provider.get_market_regime()
        
        print(f"Current Regime: {result['regime']}")
        print(f"Strategy Suggestion: {result['strategy_suggestion']}")
        
        details = result['details']
        print("\n--- Voting Breakdown ---")
        print(f"Votes: {result['votes']}")
        
        print("\n--- Factor Details ---")
        if 'trend_offset' in details:
            print(f"Trend (Nifty vs 200DMA): {details['trend_offset']:.2%} (Vote: {details['trend_vote']})")
        if 'vix' in details:
            print(f"Volatility (VIX): {details['vix']:.2f} (Vote: {details['vix_vote']})")
        if 'breadth_ratio' in details:
            print(f"Breadth (Nifty 30 > SMA50): {details['breadth_ratio']:.2%} (Vote: {details['breadth_vote']})")
            
    except ImportError:
        print("❌ Error: modules.market_data not found.")
    except Exception as e:
        print(f"❌ Error during regime check: {e}")

async def cmd_dups(args):
    """Identify and optionally clean duplicate entries in databases."""
    print_header("Duplicate Record Forensic")
    db_name = "stocks.db"
    if not os.path.exists(db_name):
        print(f"❌ {db_name} missing.")
        return

    conn = get_db_connection(db_name)
    cursor = conn.cursor()
    
    print("Checking 'multibaggers' for duplicate symbols...")
    cursor.execute("SELECT symbol, COUNT(*) FROM multibaggers GROUP BY symbol HAVING COUNT(*) > 1")
    dups_m = cursor.fetchall()
    if dups_m:
        print(f"  Found {len(dups_m)} duplicates:")
        for row in dups_m:
            print(f"    - {row[0]}: {row[1]} entries")
            if args.clean:
                print(f"    🧹 Cleaning {row[0]}...")
                # Keep the row with the latest updated_at
                cursor.execute("""
                    DELETE FROM multibaggers 
                    WHERE symbol = ? AND rowid NOT IN (
                        SELECT rowid FROM multibaggers 
                        WHERE symbol = ? 
                        ORDER BY updated_at DESC LIMIT 1
                    )
                """, (row[0], row[0]))
        if args.clean:
            conn.commit()
            print("  ✅ Duplicates cleaned in multibaggers.")
    else:
        print("  ✅ No duplicates in multibaggers.")
    
    print("\nChecking 'fundamentals_pit' for symbol/date collisions...")
    cursor.execute("SELECT symbol, as_of_date, COUNT(*) FROM fundamentals_pit GROUP BY symbol, as_of_date HAVING COUNT(*) > 1")
    dups_p = cursor.fetchall()
    if dups_p:
        print(f"  Found {len(dups_p)} collisions:")
        for row in dups_p:
            print(f"    - {row[0]} on {row[1]}: {row[2]} entries")
            if args.clean:
                print(f"    🧹 Cleaning collisions for {row[0]} on {row[1]}...")
                cursor.execute("""
                    DELETE FROM fundamentals_pit 
                    WHERE symbol = ? AND as_of_date = ? AND rowid NOT IN (
                        SELECT rowid FROM fundamentals_pit 
                        WHERE symbol = ? AND as_of_date = ? 
                        LIMIT 1
                    )
                """, (row[0], row[1], row[0], row[1]))
        if args.clean:
            conn.commit()
            print("  ✅ Collisions cleaned in fundamentals_pit.")
    else:
        print("  ✅ No collisions in fundamentals_pit.")
    
    conn.close()

async def cmd_tune_db(args):
    """Enable WAL mode, optimize PRAGMA settings, and VACUUM all DBs."""
    print_header("Database Tuning (WAL-Mode + Optimization)")
    dbs = ["stocks.db", "pit_store.db", "data_cache.db", "portfolio_history.db"]
    busy_timeout = 5000
    
    for db_name in dbs:
        if not os.path.exists(db_name):
            print(f"⏩ {db_name}: Skipping (not found)")
            continue
            
        try:
            conn = sqlite3.connect(db_name)
            # Enable WAL
            conn.execute("PRAGMA journal_mode=WAL")
            # Set Busy Timeout
            conn.execute(f"PRAGMA busy_timeout={busy_timeout}")
            # Optimize for multicore access
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # Maintenance
            print(f"  ⚡ Optimizing {db_name}...")
            conn.execute("PRAGMA optimize")
            print(f"  🧹 Vacuuming {db_name}...")
            conn.execute("VACUUM")
            
            res = conn.execute("PRAGMA journal_mode").fetchone()[0]
            print(f"✅ {db_name:15}: Tuned (Mode: {res.upper()})")
            conn.close()
        except Exception as e:
            print(f"❌ {db_name:15}: Failed to tune ({e})")


async def cmd_ml_ops(args):
    """Handle ML Ops automation tasks."""
    try:
        from modules.services import MLOpsService
        ml_ops = MLOpsService()
        
        if args.retrain:
            success = ml_ops.check_and_retrain(force=args.force)
            if success:
                print("✅ ML Model Retrained Successfully.")
            else:
                print("ℹ️ Retraining skipped or failed. Check logs.")
                
        if args.update:
            print("🚀 Batch updating predictions (this may take a minute)...")
            await ml_ops.update_all_predictions()
            print("✅ Prediction update complete.")
            
        if not args.retrain and not args.update:
            from modules.ml_ops import get_last_training_info
            info = get_last_training_info()
            print("\n" + "="*60)
            print(" ML Ops: Status & Monitoring")
            print("="*60)
            if info:
                print(f"Last Trained: {info['trained_at']}")
                print(f"Record Count: {info['record_count']}")
                print(f"R2 Score:     {info['r2_score']:.4f}")
            else:
                print("No training history found.")
            print("="*60 + "\n")
    except ImportError as e:
        print(f"❌ ML Ops Service unavailable: {e}")

async def cmd_audit(args):
    """Perform universe audit and Export FAIL tickers."""
    print_header(f"Universe Audit: {args.universe}")
    try:
        from modules.data_manager import data_manager
        conn = get_db_connection("stocks.db")
        df = pd.read_sql("SELECT * FROM multibaggers", conn)
        conn.close()
        
        if df.empty:
            print("⚠️ No tickers found in 'multibaggers' to audit.")
            return

        from modules.audit import audit_stock_data
        fails = []
        for _, row in df.iterrows():
            is_clean, flags = audit_stock_data(row.to_dict())
            if not is_clean:
                fails.append({"symbol": row['symbol'], "flags": flags, "score": row.get('score', 0)})
        
        print(f"Total Tickers: {len(df)}")
        print(f"FAIL Tickers:  {len(fails)}")
        
        if fails:
            print("\nTop Red Flags:")
            for f in fails[:10]:
                print(f"  🚩 {f['symbol']:12}: {f['flags']}")
            
            if args.export:
                filename = f"audit_fails_{datetime.now().strftime('%Y%m%d')}.csv"
                pd.DataFrame(fails).to_csv(filename, index=False)
                print(f"\n✅ Exported {len(fails)} fails to {filename}")
        else:
            print("✅ All tickers passed integrity audit.")
            
    except Exception as e:
        print(f"❌ Audit Error: {e}")

async def cmd_verify_field(args):
    """Verify a specific numeric field against a threshold across multibaggers."""
    print_header(f"Field Verification: {args.field} >= {args.threshold}")
    try:
        conn = get_db_connection("stocks.db")
        # Map field name to DB column if needed
        col_map = {
            "roe_5y": "avg_roe_5y",
            "sales_growth_5y": "sales_growth_5y",
            "debt_equity": "debt_equity",
            "cfo_to_pat": "cfo_pat_ratio"
        }
        col = col_map.get(args.field.lower(), args.field.lower())
        
        query = f"SELECT symbol, {col} as val, sector FROM multibaggers WHERE {col} >= ? ORDER BY {col} DESC"
        df = pd.read_sql(query, conn, params=(args.threshold,))
        conn.close()
        
        if df.empty:
            print(f"⚠️ No stocks found with {args.field} >= {args.threshold}")
        else:
            print(f"Found {len(df)} stocks passing threshold:")
            print(df.to_string(index=False))
            
    except Exception as e:
        print(f"❌ Verification Error: {e}")

async def cmd_scan(args):
    """Run universe scan smoke test or full run via subprocess."""
    print_header(f"Scan Engine: {args.universe} (Dry-Run: {args.dry_run})")
    
    if args.dry_run:
        print(f"🔭 Dry-run: Would scan {args.universe} universe but skipping execution.")
        print("Healthy scan output looks for: 'Fetched X/Y symbols', 'Validated score distribution', 'DB Write Complete'.")
        return

    universe_args = []
    if args.universe == "QUICK":
        universe_args = ["--smoke"]
    elif args.universe.upper() == "SECTORS":
        universe_args = ["--universe", "SECTORS"]

    print(f"🚀 Starting scan via subprocess...")
    import subprocess
    cmd = [sys.executable, "screener.py"] + universe_args
    try:
        process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        if process.returncode == 0:
            print(process.stdout)
            print("✅ Scan Cycle Complete.")
        else:
            print(f"❌ Scan Failed (Exit Code {process.returncode}):")
            print(process.stderr)
    except Exception as e:
        print(f"❌ Subprocess Execution Error: {e}")

async def cmd_telegram_test(args):
    """Test Telegram connectivity."""
    print_header("Telegram Alert Connectivity Test")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("⚠️  TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not found in .env")
        print("To connect Telegram, add these to your .env file:")
        print("  TELEGRAM_BOT_TOKEN=your_token_here")
        print("  TELEGRAM_CHAT_ID=your_chat_id_here")
        return

    try:
        import asyncio
        from telegram import Bot
        bot = Bot(token=token)
        print(f"🚀 Sending test alert to Chat ID: {chat_id}...")
        # Since this is an async command running in an async CLI, we can just await
        await bot.send_message(chat_id=chat_id, text="🚀 Sovereign AI: Maintenance Test Alert. Connection verified.")
        print("✅ Telegram Test Alert Sent Successfully.")
    except Exception as e:
        print(f"❌ Telegram Test Failed: {e}")

async def cmd_health(args):
    """System-wide health check before production runs."""
    print_header("Pipeline Health Guard")
    
    # 1. Environment Checks
    print("Environment:")
    if os.path.exists(".env"):
        print("  ✅ .env file present")
    else:
        print("  ❌ .env file missing - API calls may fail")
        
    try:
        from config import ALPHA_VANTAGE_API_KEY
        if ALPHA_VANTAGE_API_KEY and len(ALPHA_VANTAGE_API_KEY) > 5:
            print(f"  ✅ API Key: Configured (Ends in ...{ALPHA_VANTAGE_API_KEY[-3:]})")
        else:
            print("  ⚠️  API Key: Missing or invalid in config.py")
    except ImportError:
        print("  ❌ config.py: Missing")

    # 2. Dependency Checks
    print("\nCritical Modules:")
    critical_modules = ["modules.scoring", "modules.data_manager", "database", "screener", "vectorbt"]
    for mod in critical_modules:
        try:
            __import__(mod)
            print(f"  ✅ {mod:20}: Available")
        except ImportError as e:
            print(f"  ❌ {mod:20}: Missing ({e})")
            
    # 3. DB Integrity & WAL
    print("\nDatabase Integrity & Concurrency:")
    for db in ["stocks.db", "pit_store.db", "data_cache.db"]:
        if os.path.exists(db):
            try:
                conn = sqlite3.connect(db)
                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                
                status = "✅" if integrity == "ok" else "❌"
                wal_status = "WAL" if journal_mode == "wal" else journal_mode.upper()
                
                print(f"  {status} {db:15}: {wal_status} Mode (Integrity: {integrity})")
                conn.close()
            except Exception as e:
                print(f"  ❌ {db:15}: Access Error ({e})")
        else:
            print(f"  ⚠️  {db:15}: Missing (Will be created on first scan)")

    # 4. Storage Checks
    print("\nStorage Usage:")
    for db in ["stocks.db", "pit_store.db", "data_cache.db"]:
        if os.path.exists(db):
            size_mb = os.path.getsize(db) / (1024 * 1024)
            print(f"  📦 {db:15}: {size_mb:8.2f} MB")
            
    # 5. Connectivity Check (Optional/Short)
    print("\nNetwork Connectivity (Optional):")
    try:
        import yfinance as yf
        nifty = yf.Ticker("^NSEI")
        price = nifty.history(period="1d")["Close"].iloc[-1]
        print(f"  ✅ Nifty 50 Connectivity: OK (Current: {price:.2f})")
    except Exception as e:
        print(f"  ⚠️  NSE Connectivity: Failed ({e})")

def main():
    parser = argparse.ArgumentParser(description="Sovereign AI Trading Engine CLI")
    subparsers = parser.add_subparsers(dest="command")

    # db-stats
    p_stats = subparsers.add_parser("db-stats", help="Show database statistics")
    p_stats.add_argument("--symbol", help="Check specific symbol in multibaggers")

    # regime
    subparsers.add_parser("regime", help="Check current market regime")

    # dups
    p_dups = subparsers.add_parser("dups", help="Identify duplicate entries")
    p_dups.add_argument("--clean", action="store_true", help="Remove duplicate entries, keeping latest")

    # health
    subparsers.add_parser("health", help="Run system health checks")

    # tune-db
    subparsers.add_parser("tune-db", help="Enable WAL mode and optimize DBs")

    # audit
    p_audit = subparsers.add_parser("audit", help="Universe data integrity audit")
    p_audit.add_argument("--universe", default="STANDARD", help="Universe to audit")
    p_audit.add_argument("--export", action="store_true", help="Export fails to CSV")

    # scan
    p_scan = subparsers.add_parser("scan", help="Run a universe scan")
    p_scan.add_argument("--universe", default="QUICK", help="Universe to scan")
    p_scan.add_argument("--dry-run", action="store_true", help="Smoke test without DB writes")

    # telegram-test
    subparsers.add_parser("telegram-test", help="Send a test Telegram alert")

    # ml-ops
    p_ml = subparsers.add_parser("ml-ops", help="Automated ML model retraining and updates")
    p_ml.add_argument("--retrain", action="store_true", help="Trigger retraining if threshold met")
    p_ml.add_argument("--force", action="store_true", help="Force retraining regardless of threshold")
    p_ml.add_argument("--update", action="store_true", help="Batch update all predictions in multibaggers")

    # verify-field
    p_verify = subparsers.add_parser("verify-field", help="Verify field thresholds across multibaggers")
    p_verify.add_argument("--field", required=True, help="Field to verify (roe_5y, sales_growth_5y, etc.)")
    p_verify.add_argument("--threshold", type=float, required=True, help="Value threshold")

    args = parser.parse_args()

    if args.command == "db-stats":
        asyncio.run(cmd_db_stats(args))
    elif args.command == "regime":
        asyncio.run(cmd_regime(args))
    elif args.command == "dups":
        asyncio.run(cmd_dups(args))
    elif args.command == "health":
        asyncio.run(cmd_health(args))
    elif args.command == "tune-db":
        asyncio.run(cmd_tune_db(args))
    elif args.command == "audit":
        asyncio.run(cmd_audit(args))
    elif args.command == "scan":
        asyncio.run(cmd_scan(args))
    elif args.command == "verify-field":
        asyncio.run(cmd_verify_field(args))
    elif args.command == "telegram-test":
        asyncio.run(cmd_telegram_test(args))
    elif args.command == "ml-ops":
        asyncio.run(cmd_ml_ops(args))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
