import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
OPS_DIR = ROOT / "ops"
RUBRIC_PATH = OPS_DIR / "institutional_gate_rubric.json"
HISTORY_PATH = OPS_DIR / "institutional_daily_scorecard.json"
REPORT_DIR = OPS_DIR / "daily_reports"


@dataclass
class CheckResult:
    name: str
    score: float
    max_score: float
    evidence: str

    @property
    def passed(self) -> bool:
        return self.score >= self.max_score


@dataclass
class GateResult:
    gate_id: str
    gate_name: str
    score: float
    raw_score: float
    max_score: float
    cap_applied: bool
    cap_reason: str
    checks: List[CheckResult]


def load_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def contains(path: Path, pattern: str) -> bool:
    return pattern in read_text(path)


def run_cmd(args: List[str]) -> Dict:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "cmd": " ".join(args),
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "ok": proc.returncode == 0,
    }


def run_pytest(targets: List[str]) -> Dict:
    args = [sys.executable, "-m", "pytest", "-q", *targets, "-p", "no:cacheprovider"]
    return run_cmd(args)


def count_occurrences(paths: List[Path], token: str) -> int:
    total = 0
    for path in paths:
        total += read_text(path).count(token)
    return total


def clamp_score(score: float, max_score: float = 10.0) -> float:
    return round(max(0.0, min(score, max_score)), 1)


def score_from_checks(checks: List[CheckResult]) -> Tuple[float, float]:
    raw = round(sum(c.score for c in checks), 2)
    max_raw = round(sum(c.max_score for c in checks), 2)
    if max_raw == 0:
        return 0.0, 0.0
    normalized = (raw / max_raw) * 10.0
    return normalized, raw


def apply_cap(score: float, cap: float, reason: str, condition: bool) -> Tuple[float, bool, str]:
    if condition and score > cap:
        return cap, True, reason
    return score, False, ""


def evaluate_resilience(rubric_item: Dict, shared: Dict) -> GateResult:
    checks: List[CheckResult] = []
    retry_utils = ROOT / "modules" / "retry_utils.py"
    main_py = ROOT / "main.py"
    db_py = ROOT / "database.py"
    backup_bat = ROOT / "backup.bat"

    retry_text = read_text(retry_utils)
    has_backoff_core = all(
        token in retry_text
        for token in ("DEFAULT_BACKOFF_SECONDS", "(2.0, 4.0, 8.0)", "run_with_exponential_backoff")
    )
    checks.append(
        CheckResult(
            "Centralized exponential backoff utility",
            2.0 if has_backoff_core else 0.0,
            2.0,
            "modules/retry_utils.py",
        )
    )

    module_paths = [main_py, ROOT / "report_generator.py"] + sorted((ROOT / "modules").glob("*.py"))
    if retry_utils in module_paths:
        module_paths.remove(retry_utils)
    integration_count = count_occurrences(module_paths, "run_with_exponential_backoff(")
    integration_score = 2.0 if integration_count >= 8 else (1.0 if integration_count >= 5 else 0.0)
    checks.append(
        CheckResult(
            "Backoff integration coverage",
            integration_score,
            2.0,
            f"run_with_exponential_backoff occurrences: {integration_count}",
        )
    )

    main_text = read_text(main_py)
    non_blocking_patterns = [
        "async def get_multibaggers",
        "return await _run_blocking(",
        "async def get_microcaps",
        "async def update_prices_background",
    ]
    has_non_blocking = all(p in main_text for p in non_blocking_patterns)
    checks.append(
        CheckResult(
            "Non-blocking endpoint and updater flow",
            2.0 if has_non_blocking else 0.0,
            2.0,
            "main.py async endpoint patterns",
        )
    )

    lock_retry_ok = all(
        token in (main_text + read_text(db_py))
        for token in ("_run_sqlite_write_with_retry", "PRAGMA busy_timeout", "journal_mode=WAL")
    )
    checks.append(
        CheckResult(
            "SQLite lock contention hardening",
            1.0 if lock_retry_ok else 0.0,
            1.0,
            "main.py + database.py lock retry/WAL checks",
        )
    )

    api_suite = shared["commands"]["api_suite"]
    checks.append(
        CheckResult(
            "API smoke test suite",
            3.0 if api_suite["ok"] else 0.0,
            3.0,
            f"returncode={api_suite['returncode']}",
        )
    )

    has_backup = all(
        token in read_text(backup_bat)
        for token in ('copy /Y "stocks.db"', 'copy /Y "portfolio_history.db"', "exit /b 0", "exit /b 1")
    )
    checks.append(
        CheckResult(
            "Disaster backup script completeness",
            0.5 if has_backup else 0.0,
            0.5,
            "backup.bat",
        )
    )

    normalized, raw = score_from_checks(checks)

    tests_dir = ROOT / "tests"
    has_load_harness = any(
        re.search(r"(load|concurrency|throttle|failure|recovery)", p.name.lower())
        for p in tests_dir.glob("*.py")
    )
    score, capped, reason = apply_cap(
        normalized,
        float(rubric_item["hard_cap_without_evidence"]),
        rubric_item["hard_cap_reason"],
        not has_load_harness,
    )

    return GateResult(
        gate_id=rubric_item["id"],
        gate_name=rubric_item["name"],
        score=clamp_score(score),
        raw_score=round(raw, 2),
        max_score=10.0,
        cap_applied=capped,
        cap_reason=reason,
        checks=checks,
    )


def evaluate_risk(rubric_item: Dict, shared: Dict) -> GateResult:
    checks: List[CheckResult] = []
    config_text = read_text(ROOT / "config.py")
    risk_text = read_text(ROOT / "modules" / "risk.py")
    main_text = read_text(ROOT / "main.py")

    has_thresholds = all(
        token in config_text
        for token in ("DRAWDOWN_RATE_KILL_WEEKLY", "CORRELATION_REDUCE_THRESHOLD", "CORRELATION_LIQUIDATE_THRESHOLD")
    )
    checks.append(
        CheckResult(
            "Risk threshold configuration",
            2.0 if has_thresholds else 0.0,
            2.0,
            "config.py threshold constants",
        )
    )

    has_core_methods = all(
        token in risk_text
        for token in ("def check_kill_switch", "drawdown_rate_weekly", "def validate_var_budget", "def validate_correlation_risk")
    )
    checks.append(
        CheckResult(
            "Risk governor control surface",
            2.5 if has_core_methods else 0.0,
            2.5,
            "modules/risk.py",
        )
    )

    order_risk_path = all(
        token in main_text
        for token in ("/api/order", "validate_var_budget", "validate_correlation_risk", "check_kill_switch")
    )
    checks.append(
        CheckResult(
            "Pre-trade risk gating in order lifecycle",
            2.0 if order_risk_path else 0.0,
            2.0,
            "main.py /api/order",
        )
    )

    risk_suite = shared["commands"]["risk_suite"]
    checks.append(
        CheckResult(
            "Risk regression suite",
            2.5 if risk_suite["ok"] else 0.0,
            2.5,
            f"returncode={risk_suite['returncode']}",
        )
    )

    blackbox_ok = all(
        token in (risk_text + main_text)
        for token in ("rejected_trades.csv", "log_rejected_trade", "/api/rejections")
    )
    checks.append(
        CheckResult(
            "Black-box rejection telemetry",
            1.0 if blackbox_ok else 0.0,
            1.0,
            "modules/risk.py + main.py",
        )
    )

    normalized, raw = score_from_checks(checks)

    stress_text = read_text(ROOT / "modules" / "stress_test.py")
    has_full_scenario_replay = all(
        token in stress_text.lower()
        for token in ("gap", "slippage", "correlation", "vix")
    )
    score, capped, reason = apply_cap(
        normalized,
        float(rubric_item["hard_cap_without_evidence"]),
        rubric_item["hard_cap_reason"],
        not has_full_scenario_replay,
    )

    return GateResult(
        gate_id=rubric_item["id"],
        gate_name=rubric_item["name"],
        score=clamp_score(score),
        raw_score=round(raw, 2),
        max_score=10.0,
        cap_applied=capped,
        cap_reason=reason,
        checks=checks,
    )


def evaluate_performance(rubric_item: Dict, shared: Dict) -> GateResult:
    checks: List[CheckResult] = []
    backtest_text = read_text(ROOT / "modules" / "backtest.py")
    validation_text = read_text(ROOT / "modules" / "validation.py")
    perf_suite = shared["commands"]["perf_suite"]

    has_metrics = all(token in backtest_text for token in ("Sharpe", "max_dd", "CAGR"))
    checks.append(
        CheckResult(
            "Backtest metric surface (Sharpe/DD/CAGR)",
            2.5 if has_metrics else 0.0,
            2.5,
            "modules/backtest.py",
        )
    )

    has_regime_validation = all(
        token in validation_text for token in ("validate_robustness", "2022", "2023", "2024")
    )
    checks.append(
        CheckResult(
            "Multi-regime robustness harness",
            1.5 if has_regime_validation else 0.0,
            1.5,
            "modules/validation.py",
        )
    )

    checks.append(
        CheckResult(
            "Performance endpoint regression tests",
            2.0 if perf_suite["ok"] else 0.0,
            2.0,
            f"returncode={perf_suite['returncode']}",
        )
    )

    monte_targets = [ROOT / "modules", ROOT / "tests", ROOT]
    monte_text = ""
    for target in monte_targets:
        if target.is_file():
            monte_text += read_text(target)
        else:
            for py_file in target.rglob("*.py"):
                monte_text += read_text(py_file)
    has_monte_1000 = (
        re.search(r"monte", monte_text, re.IGNORECASE) is not None
        and re.search(r"1000", monte_text) is not None
    )
    checks.append(
        CheckResult(
            "Monte Carlo (>=1000 paths) pipeline",
            3.0 if has_monte_1000 else 0.0,
            3.0,
            "repo-wide Monte Carlo search",
        )
    )

    has_latency_alpha_model = re.search(
        r"(latency.*alpha|alpha.*latency|slippage.*latency)",
        monte_text,
        re.IGNORECASE,
    ) is not None
    checks.append(
        CheckResult(
            "Latency impact on alpha capture model",
            1.0 if has_latency_alpha_model else 0.0,
            1.0,
            "repo-wide latency/alpha search",
        )
    )

    normalized, raw = score_from_checks(checks)
    score, capped, reason = apply_cap(
        normalized,
        float(rubric_item["hard_cap_without_evidence"]),
        rubric_item["hard_cap_reason"],
        not has_monte_1000,
    )

    return GateResult(
        gate_id=rubric_item["id"],
        gate_name=rubric_item["name"],
        score=clamp_score(score),
        raw_score=round(raw, 2),
        max_score=10.0,
        cap_applied=capped,
        cap_reason=reason,
        checks=checks,
    )


def evaluate_audit(rubric_item: Dict, shared: Dict) -> GateResult:
    checks: List[CheckResult] = []
    report_text = read_text(ROOT / "report_generator.py")
    logger_text = read_text(ROOT / "modules" / "logger.py")
    backtest_engine_text = read_text(ROOT / "backtest_engine.py")
    database_text = read_text(ROOT / "database.py")
    backup_text = read_text(ROOT / "backup.bat")

    has_cache_signature = all(
        token in report_text
        for token in ("sha256", "_read_verified_cache", "_write_signed_cache", ".sha256")
    )
    checks.append(
        CheckResult(
            "Signed cache read/write integrity",
            2.0 if has_cache_signature else 0.0,
            2.0,
            "report_generator.py",
        )
    )

    has_scan_determinism = all(
        token in logger_text
        for token in ("version_hash", "_generate_version_hash", "%Y_%m_%d_%H_%M_%S_%f")
    )
    checks.append(
        CheckResult(
            "Scan log version determinism",
            2.0 if has_scan_determinism else 0.0,
            2.0,
            "modules/logger.py",
        )
    )

    has_lookahead_guard = all(
        token in backtest_engine_text for token in ("as_of_date", "lookahead bias", "Backtest aborted")
    )
    checks.append(
        CheckResult(
            "Lookahead fail-fast guard",
            2.0 if has_lookahead_guard else 0.0,
            2.0,
            "backtest_engine.py",
        )
    )

    backup_ok = all(
        token in backup_text
        for token in ('copy /Y "stocks.db"', 'copy /Y "portfolio_history.db"', "exit /b 0", "exit /b 1")
    )
    has_backups = any((ROOT / "backups").rglob("*.db"))
    checks.append(
        CheckResult(
            "Backup and restore artifact footprint",
            2.0 if (backup_ok and has_backups) else (1.0 if backup_ok else 0.0),
            2.0,
            "backup.bat + backups/",
        )
    )

    has_last_audited_flow = all(
        token in (database_text + read_text(ROOT / "main.py"))
        for token in ("last_audited", "weekly_audit_loop", "WHERE last_audited")
    )
    checks.append(
        CheckResult(
            "last_audited metadata flow",
            2.0 if has_last_audited_flow else 0.0,
            2.0,
            "database.py + main.py",
        )
    )

    normalized, raw = score_from_checks(checks)
    has_pit_db = "as_of_date" in database_text
    score, capped, reason = apply_cap(
        normalized,
        float(rubric_item["hard_cap_without_evidence"]),
        rubric_item["hard_cap_reason"],
        not has_pit_db,
    )

    return GateResult(
        gate_id=rubric_item["id"],
        gate_name=rubric_item["name"],
        score=clamp_score(score),
        raw_score=round(raw, 2),
        max_score=10.0,
        cap_applied=capped,
        cap_reason=reason,
        checks=checks,
    )


def evaluate_operations(rubric_item: Dict, shared: Dict) -> GateResult:
    checks: List[CheckResult] = []
    main_text = read_text(ROOT / "main.py")
    tracker_text = read_text(ROOT / "modules" / "tracker.py")
    execution_text = read_text(ROOT / "modules" / "execution.py")
    api_suite = shared["commands"]["api_suite"]

    has_oms_endpoints = all(
        token in main_text for token in ("/api/order", "/api/trades/open", "/api/trades/history")
    )
    checks.append(
        CheckResult(
            "Order/trade lifecycle API surface",
            2.5 if has_oms_endpoints else 0.0,
            2.5,
            "main.py",
        )
    )

    has_tracker_states = all(
        token in tracker_text for token in ("status = 'OPEN'", "status = 'CLOSED'", "log_entry", "log_exit")
    )
    has_duplicate_reject = "Position already open" in tracker_text
    tracker_score = 2.5 if (has_tracker_states and has_duplicate_reject) else 1.0 if has_tracker_states else 0.0
    checks.append(
        CheckResult(
            "State transition + duplicate order guard",
            tracker_score,
            2.5,
            "modules/tracker.py",
        )
    )

    checks.append(
        CheckResult(
            "Execution API regression suite",
            2.0 if api_suite["ok"] else 0.0,
            2.0,
            f"returncode={api_suite['returncode']}",
        )
    )

    risk_gated_order = all(
        token in main_text
        for token in ("check_kill_switch", "validate_var_budget", "validate_correlation_risk", "log_rejected_trade")
    )
    checks.append(
        CheckResult(
            "Risk-aware execution path",
            2.0 if risk_gated_order else 0.0,
            2.0,
            "main.py /api/order",
        )
    )

    has_external_ack_lifecycle = re.search(
        r"(FILLED|PARTIAL|CANCELLED|idempotency|reconcile)",
        main_text + tracker_text + execution_text,
        re.IGNORECASE,
    ) is not None
    checks.append(
        CheckResult(
            "Broker ack/reconciliation lifecycle",
            1.0 if has_external_ack_lifecycle else 0.0,
            1.0,
            "main.py + modules/tracker.py + modules/execution.py",
        )
    )

    normalized, raw = score_from_checks(checks)
    score, capped, reason = apply_cap(
        normalized,
        float(rubric_item["hard_cap_without_evidence"]),
        rubric_item["hard_cap_reason"],
        not has_external_ack_lifecycle,
    )

    return GateResult(
        gate_id=rubric_item["id"],
        gate_name=rubric_item["name"],
        score=clamp_score(score),
        raw_score=round(raw, 2),
        max_score=10.0,
        cap_applied=capped,
        cap_reason=reason,
        checks=checks,
    )


def build_markdown_report(
    date_str: str,
    composite: float,
    weighted_gap: float,
    results: List[GateResult],
    commands: Dict[str, Dict],
) -> str:
    lines: List[str] = []
    lines.append(f"# Institutional Sprint Daily Scorecard - {date_str}")
    lines.append("")
    lines.append(f"- Composite Score: **{composite:.1f}/10**")
    lines.append(f"- Distance to 9.0 target: **{weighted_gap:.1f}**")
    lines.append("")
    lines.append("| Gate | Score | Cap |")
    lines.append("| :--- | ---: | :--- |")
    for result in results:
        cap = "YES" if result.cap_applied else "NO"
        lines.append(f"| {result.gate_name} | {result.score:.1f} | {cap} |")
    lines.append("")
    lines.append("## Gate Findings")
    for result in results:
        lines.append(f"### {result.gate_name} ({result.score:.1f}/10)")
        if result.cap_applied and result.cap_reason:
            lines.append(f"- Cap Applied: {result.cap_reason}")
        for check in result.checks:
            lines.append(
                f"- {check.name}: {check.score:.1f}/{check.max_score:.1f} ({check.evidence})"
            )
        lines.append("")
    lines.append("## Command Evidence")
    for key, cmd in commands.items():
        lines.append(f"- {key}: `returncode={cmd['returncode']}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily institutional sprint scorer.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--no-record", action="store_true", help="Do not write history/report files.")
    parser.add_argument("--print-json", action="store_true", help="Print score payload as JSON.")
    args = parser.parse_args()

    rubric = load_json(RUBRIC_PATH)
    gate_map = {g["id"]: g for g in rubric["gates"]}

    shared = {
        "commands": {
            "compile_suite": run_cmd(
                [
                    sys.executable,
                    "-m",
                    "py_compile",
                    "main.py",
                    "config.py",
                    "report_generator.py",
                    "modules/risk.py",
                    "modules/retry_utils.py",
                    "modules/tracker.py",
                ]
            ),
            "api_suite": run_pytest(
                [
                    "tests/test_api.py",
                    "tests/test_api_extended_endpoints.py",
                    "tests/test_price_fundamentals_api.py",
                ]
            ),
            "risk_suite": run_pytest(
                [
                    "tests/test_blackbox.py",
                    "tests/check_v29_refinements.py",
                    "tests/audit_sensitivity.py",
                ]
            ),
            "perf_suite": run_pytest(["tests/test_price_fundamentals_api.py"]),
        }
    }

    results = [
        evaluate_resilience(gate_map["resilience"], shared),
        evaluate_risk(gate_map["risk"], shared),
        evaluate_performance(gate_map["performance"], shared),
        evaluate_audit(gate_map["audit"], shared),
        evaluate_operations(gate_map["operations"], shared),
    ]

    weighted = 0.0
    weighted_gap = 0.0
    for result in results:
        weight = gate_map[result.gate_id]["weight"]
        weighted += result.score * weight
        weighted_gap += max(0.0, 9.0 - result.score) * weight
    composite_score = clamp_score(weighted)
    weighted_gap = round(weighted_gap, 2)

    verdict = "GREEN" if composite_score >= 8.5 else ("YELLOW" if composite_score >= 7.0 else "RED")

    payload = {
        "date": args.date,
        "composite_score": composite_score,
        "target_score": 9.0,
        "weighted_gap_to_target": weighted_gap,
        "verdict": verdict,
        "gates": {
            result.gate_id: {
                "name": result.gate_name,
                "score": result.score,
                "raw_score": result.raw_score,
                "max_score": result.max_score,
                "cap_applied": result.cap_applied,
                "cap_reason": result.cap_reason,
                "checks": [
                    {
                        "name": c.name,
                        "score": round(c.score, 2),
                        "max_score": round(c.max_score, 2),
                        "passed": c.passed,
                        "evidence": c.evidence,
                    }
                    for c in result.checks
                ],
            }
            for result in results
        },
        "commands": shared["commands"],
    }

    report_md = build_markdown_report(args.date, composite_score, weighted_gap, results, shared["commands"])

    if not args.no_record:
        history = load_json(HISTORY_PATH)
        history_list = history.get("history", [])
        history_list = [entry for entry in history_list if entry.get("date") != args.date]
        history_list.append(payload)
        history["history"] = sorted(history_list, key=lambda x: x.get("date", ""))
        save_json(HISTORY_PATH, history)

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"{args.date}.md"
        report_path.write_text(report_md, encoding="utf-8")

    if args.print_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"{args.date} composite={composite_score:.1f}/10 verdict={verdict}")
        for result in results:
            cap_note = " cap" if result.cap_applied else ""
            print(f"- {result.gate_name}: {result.score:.1f}/10{cap_note}")


if __name__ == "__main__":
    main()
