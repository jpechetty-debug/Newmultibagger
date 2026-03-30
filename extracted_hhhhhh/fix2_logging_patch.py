"""
fix2_logging_patch.py
─────────────────────
Applies Fix #2: Replace all silent `except: pass` and bare print()-based
error handling with structured logging.

Run from the project root:
    python fix2_logging_patch.py

Patches three files:
    modules/data_manager.py     — bare `except: pass` on cfo_pat division
    modules/alpha_vantage.py    — bare `except Exception: pass` on budget save
    modules/market_data.py      — print(f"⚠️ ...") swallowed errors replaced
                                  with logger.warning()

Each change is surgical — only the identified bad patterns are touched.
"""

import re
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_SUFFIX = ".bak_fix2"


# ── helpers ──────────────────────────────────────────────────────────────────

def backup(path: Path) -> None:
    shutil.copy2(path, path.with_suffix(path.suffix + BACKUP_SUFFIX))
    print(f"  backed up → {path.name}{BACKUP_SUFFIX}")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"  patched  → {path}")


# ── patch 1: modules/data_manager.py ─────────────────────────────────────────
# Replace the bare `except: pass` inside PNSEAProvider.fetch_fundamentals()
# that silently swallows ZeroDivisionError on the CFO/PAT ratio calculation.

def patch_data_manager() -> None:
    path = ROOT / "modules" / "data_manager.py"
    text = path.read_text(encoding="utf-8")

    # Ensure logging is imported (it already is, but be defensive)
    if "import logging" not in text:
        text = "import logging\n" + text

    # Ensure module-level logger exists (already does: logger = getLogger(__name__))
    # so we just fix the bare except.

    OLD = """\
        cfo_pat = 0.0
        try:
            cfo_pat = raw.get(\"info\", {}).get(\"cashFlowFromOperations\", 0) / max(raw.get(\"info\", {}).get(\"netProfit\", 1), 1)
        except:
            pass"""

    NEW = """\
        cfo_pat = 0.0
        try:
            cfo_pat = raw.get(\"info\", {}).get(\"cashFlowFromOperations\", 0) / max(raw.get(\"info\", {}).get(\"netProfit\", 1), 1)
        except (ZeroDivisionError, TypeError, ValueError) as _cfo_err:
            logger.warning(\"[%s] CFO/PAT ratio calculation failed: %s\", symbol, _cfo_err)"""

    if OLD not in text:
        print(f"  WARN: expected pattern not found in {path.name} — skipping (may already be patched)")
        return

    backup(path)
    write(path, text.replace(OLD, NEW, 1))


# ── patch 2: modules/alpha_vantage.py ────────────────────────────────────────
# Add a module-level logger and replace bare `except Exception: pass` on the
# budget-save path so failures are visible.

def patch_alpha_vantage() -> None:
    path = ROOT / "modules" / "alpha_vantage.py"
    text = path.read_text(encoding="utf-8")

    # Inject logger after the existing imports block if not already present
    if "logger = logging.getLogger" not in text:
        # Find the last import line and insert after it
        import_end = max(
            (m.end() for m in re.finditer(r"^(?:import|from)\s+\S+", text, re.MULTILINE)),
            default=0,
        )
        logger_line = "\nimport logging\nlogger = logging.getLogger(__name__)\n"
        text = text[:import_end] + logger_line + text[import_end:]

    # Fix 1: budget load — FileNotFoundError is expected, JSONDecodeError should log
    OLD_LOAD = """\
    except (FileNotFoundError, json.JSONDecodeError):
        pass"""

    NEW_LOAD = """\
    except FileNotFoundError:
        pass  # no budget file yet — that's normal on first run
    except json.JSONDecodeError as _e:
        logger.warning(\"Alpha Vantage budget file is corrupt, resetting: %s\", _e)"""

    # Fix 2: budget save — bare `except Exception: pass` loses disk errors
    OLD_SAVE = """\
    except Exception:\n        pass"""

    NEW_SAVE = """\
    except Exception as _save_err:
        logger.warning(\"Alpha Vantage budget save failed: %s\", _save_err)"""

    changed = False
    if OLD_LOAD in text:
        text = text.replace(OLD_LOAD, NEW_LOAD, 1)
        changed = True
    else:
        print(f"  WARN: budget-load pattern not found in {path.name}")

    if OLD_SAVE in text:
        text = text.replace(OLD_SAVE, NEW_SAVE, 1)
        changed = True
    else:
        print(f"  WARN: budget-save pattern not found in {path.name}")

    if changed:
        backup(path)
        write(path, text)


# ── patch 3: modules/market_data.py ──────────────────────────────────────────
# Replace four print(f"⚠️ ...") error reports with logger.warning() calls.
# Also adds a module-level logger.

def patch_market_data() -> None:
    path = ROOT / "modules" / "market_data.py"
    text = path.read_text(encoding="utf-8")

    # Inject logger if missing
    if "logger = logging.getLogger" not in text:
        import_end = max(
            (m.end() for m in re.finditer(r"^(?:import|from)\s+\S+", text, re.MULTILINE)),
            default=0,
        )
        logger_line = "\nimport logging\nlogger = logging.getLogger(__name__)\n"
        text = text[:import_end] + logger_line + text[import_end:]

    # Replace emoji-prefixed print() error reports with structured logger calls.
    # Pattern: print(f"⚠️ Error ...")  →  logger.warning(...)
    # We handle the four specific occurrences identified in the audit.

    replacements = [
        # VIX fetch failure
        (
            'print(f"⚠️ Error fetching VIX: {e}")',
            'logger.warning("Market data: VIX fetch failed: %s", e)',
        ),
        # Market breadth failure
        (
            'print(f"⚠️ Error calculating breadth: {e}")',
            'logger.warning("Market data: breadth calculation failed: %s", e)',
        ),
        # HMM regime detection factor error
        (
            'print(f"⚠️ HMM Factor Error: {hmm_err}")',
            'logger.warning("Market data: HMM factor error: %s", hmm_err)',
        ),
        # Full regime detection failure
        (
            'print(f"⚠️ Error in Regime Detection (v2.9): {e}")',
            'logger.warning("Market data: regime detection failed: %s", e)',
        ),
        # Batch history failure
        (
            'print(f"⚠️ Error fetching batch history: {e}")',
            'logger.warning("Market data: batch history fetch failed: %s", e)',
        ),
    ]

    changed = False
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
            changed = True
        else:
            print(f"  WARN: pattern not found in {path.name}: {old!r}")

    if changed:
        backup(path)
        write(path, text)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("\n── Fix #2: Structured exception logging ──\n")

    print("Patching modules/data_manager.py …")
    patch_data_manager()

    print("\nPatching modules/alpha_vantage.py …")
    patch_alpha_vantage()

    print("\nPatching modules/market_data.py …")
    patch_market_data()

    print("\n✓ Done. Verify changes with: git diff modules/")
    print("  Roll back any file with: cp <file>.bak_fix2 <file>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
