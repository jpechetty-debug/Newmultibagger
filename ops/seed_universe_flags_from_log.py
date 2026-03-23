import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from screener import load_universe_flags, save_universe_flags, refresh_and_get_blocked_symbols


DELISTED_RE = re.compile(r"\$([A-Z0-9&.\-]+):\s+possibly delisted; no price data found")
NO_FUND_RE = re.compile(r"No fundamentals data found for symbol:\s*([A-Z0-9&.\-]+)")


def parse_invalid_symbols(log_text: str) -> set[str]:
    symbols = set()
    symbols.update(sym.upper() for sym in DELISTED_RE.findall(log_text))
    symbols.update(sym.upper() for sym in NO_FUND_RE.findall(log_text))
    return symbols


def read_log_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    # Last resort best-effort decode.
    return raw.decode("latin-1", errors="replace")


def main():
    if len(sys.argv) < 2:
        print("Usage: python ops/seed_universe_flags_from_log.py <scan_log_path>")
        raise SystemExit(1)

    log_path = Path(sys.argv[1]).resolve()
    if not log_path.exists():
        print(f"Log not found: {log_path}")
        raise SystemExit(1)

    text = read_log_text(log_path)
    invalid_symbols = parse_invalid_symbols(text)
    if not invalid_symbols:
        print("No invalid symbols found in log patterns.")
        raise SystemExit(0)

    flags_path = BASE_DIR / str(getattr(config, "UNIVERSE_FLAGS_PATH", "data/universe_flags.json"))
    payload = load_universe_flags(str(flags_path))
    whitelist = {str(s).upper() for s in getattr(config, "AUTO_FLAG_WHITELIST", [])}
    today = date.today()
    expires_on = (today + timedelta(days=int(getattr(config, "AUTO_FLAG_COOLDOWN_DAYS", 14)))).isoformat()
    threshold = int(getattr(config, "AUTO_FLAG_FAILURE_THRESHOLD", 1))

    updated = 0
    symbols = payload.setdefault("symbols", {})
    for sym in sorted(invalid_symbols - whitelist):
        rec = symbols.setdefault(sym, {})
        if str(rec.get("status", "active")).lower() != "inactive":
            updated += 1
        rec["status"] = "inactive"
        rec["reason"] = "log_detected_invalid_symbol"
        rec["inactive_since"] = today.isoformat()
        rec["expires_on"] = expires_on
        rec["last_failure_date"] = today.isoformat()
        rec["consecutive_failures"] = max(int(rec.get("consecutive_failures", 0) or 0), threshold)
        rec["total_failures"] = int(rec.get("total_failures", 0) or 0) + 1

    payload["updated_at"] = date.today().isoformat()
    blocked = refresh_and_get_blocked_symbols(payload, today)
    save_universe_flags(str(flags_path), payload)

    print(
        json.dumps(
            {
                "log": str(log_path),
                "invalid_detected": len(invalid_symbols),
                "newly_inactivated": updated,
                "blocked_total": len(blocked),
                "flags_path": str(flags_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
