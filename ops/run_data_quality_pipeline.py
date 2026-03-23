import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _latest_summary_in_runs(runs_dir: Path, exclude_run_id: str) -> Path | None:
    if not runs_dir.exists():
        return None
    run_dirs = [p for p in runs_dir.iterdir() if p.is_dir() and p.name != exclude_run_id]
    if not run_dirs:
        return None
    run_dirs = sorted(run_dirs, key=lambda p: p.name)
    for run_dir in reversed(run_dirs):
        candidate = run_dir / "cleaning_summary.json"
        if candidate.exists():
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the data quality cleaning pipeline with timestamped outputs, "
            "automatic baseline detection, and optional DB write-back."
        )
    )
    parser.add_argument("--db-path", default="stocks.db")
    parser.add_argument("--rules-path", default="ops/cleaning_rules.yaml")
    parser.add_argument("--runs-dir", default="reports/cleaned_runs")
    parser.add_argument("--as-of-date", default=None, help="Optional YYYY-MM-DD reference date.")
    parser.add_argument(
        "--write-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write cleaned/gold tables and telemetry tables to DB.",
    )
    parser.add_argument("--run-id", default=None, help="Optional run id; defaults to UTC timestamp.")
    parser.add_argument(
        "--run-backtest-compare",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Also run raw-vs-gold backtest comparison after cleaning.",
    )
    parser.add_argument("--raw-table", default="multibaggers")
    parser.add_argument("--gold-table", default="multibaggers_gold")
    parser.add_argument("--backtest-top-n", type=int, default=20)
    parser.add_argument("--backtest-period", default="5y")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = Path(args.runs_dir)
    out_dir = runs_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline_summary = _latest_summary_in_runs(runs_dir, exclude_run_id=run_id)

    cmd = [
        sys.executable,
        "ops/build_clean_dataset.py",
        "--db-path",
        args.db_path,
        "--rules-path",
        args.rules_path,
        "--out-dir",
        str(out_dir),
        "--run-id",
        run_id,
    ]
    if args.as_of_date:
        cmd.extend(["--as-of-date", args.as_of_date])
    if args.write_db:
        cmd.append("--write-db")
    if baseline_summary:
        cmd.extend(["--baseline-summary", str(baseline_summary)])

    subprocess.run(cmd, check=True)

    backtest_compare_manifest = None
    if args.run_backtest_compare:
        compare_dir = out_dir / "backtest_compare"
        compare_cmd = [
            sys.executable,
            "ops/compare_raw_vs_gold_backtest.py",
            "--db-path",
            args.db_path,
            "--raw-table",
            args.raw_table,
            "--gold-table",
            args.gold_table,
            "--top-n",
            str(args.backtest_top_n),
            "--period",
            args.backtest_period,
            "--out-dir",
            str(compare_dir),
            "--run-id",
            run_id,
        ]
        if args.as_of_date:
            compare_cmd.extend(["--as-of-date", args.as_of_date])
        if args.write_db:
            compare_cmd.append("--write-db")
        subprocess.run(compare_cmd, check=True)
        backtest_compare_manifest = {
            "enabled": True,
            "out_dir": str(compare_dir),
            "summary_path": str(compare_dir / "raw_vs_gold_backtest_summary.json"),
            "report_path": str(compare_dir / "raw_vs_gold_backtest_report.md"),
            "symbols_path": str(compare_dir / "raw_vs_gold_backtest_symbols.csv"),
        }

    summary_path = out_dir / "cleaning_summary.json"
    alerts_path = out_dir / "cleaning_alerts.json"
    summary = {}
    alerts = []
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if alerts_path.exists():
        alerts = json.loads(alerts_path.read_text(encoding="utf-8"))

    manifest = {
        "run_id": run_id,
        "run_ts_utc": datetime.now(timezone.utc).isoformat(),
        "out_dir": str(out_dir),
        "summary_path": str(summary_path),
        "alerts_path": str(alerts_path),
        "baseline_summary": str(baseline_summary) if baseline_summary else None,
        "alert_count": len(alerts) if isinstance(alerts, list) else None,
        "write_db": bool(args.write_db),
        "tables": list((summary.get("tables") or {}).keys()) if isinstance(summary, dict) else [],
        "backtest_compare": backtest_compare_manifest,
    }
    manifest_path = out_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    latest_manifest = runs_dir / "latest_run_manifest.json"
    latest_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Run complete: {run_id}")
    print(f"Output dir: {out_dir}")
    print(f"Summary: {summary_path}")
    print(f"Alerts: {alerts_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
