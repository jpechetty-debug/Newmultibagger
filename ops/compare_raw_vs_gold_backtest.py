import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import VectorBTEngine


VALID_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(name: str, label: str) -> str:
    if not VALID_IDENT_RE.match(name):
        raise ValueError(f"Invalid {label} '{name}'")
    return name


def normalize_symbol(symbol: str) -> str:
    s = str(symbol).strip().upper()
    if s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def _safe_float(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float("nan")
    if np.isnan(v) or np.isinf(v):
        return float("nan")
    return v


def load_top_universe(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    symbol_col: str,
    score_col: str,
    limit: int,
) -> pd.DataFrame:
    table = validate_identifier(table_name, "table name")
    symbol = validate_identifier(symbol_col, "symbol column")
    score = validate_identifier(score_col, "score column")
    query = (
        f'SELECT "{symbol}" AS symbol, CAST("{score}" AS REAL) AS score '
        f'FROM "{table}" '
        f'WHERE "{symbol}" IS NOT NULL '
        f'ORDER BY score DESC '
        f"LIMIT ?"
    )
    df = pd.read_sql_query(query, conn, params=[limit])
    if df.empty:
        return df
    df["symbol"] = df["symbol"].astype(str).map(normalize_symbol)
    df = df.drop_duplicates(subset=["symbol"], keep="first").reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    return df


def summarize_universe(metrics_df: pd.DataFrame, total_symbols: int) -> dict[str, Any]:
    ok = metrics_df[metrics_df["status"] == "OK"].copy()
    out: dict[str, Any] = {
        "symbols_in_universe": int(total_symbols),
        "symbols_with_backtest": int(len(ok)),
        "coverage_pct": round((len(ok) / total_symbols * 100.0) if total_symbols else 0.0, 2),
    }
    if ok.empty:
        out.update(
            {
                "avg_cagr_pct": None,
                "median_cagr_pct": None,
                "avg_win_rate_pct": None,
                "avg_max_drawdown_pct": None,
                "avg_sharpe": None,
                "positive_cagr_share_pct": None,
            }
        )
        return out

    out.update(
        {
            "avg_cagr_pct": round(float(ok["cagr"].mean()), 4),
            "median_cagr_pct": round(float(ok["cagr"].median()), 4),
            "avg_win_rate_pct": round(float(ok["win_rate"].mean()), 4),
            "avg_max_drawdown_pct": round(float(ok["max_drawdown"].mean()), 4),
            "avg_sharpe": round(float(ok["sharpe_ratio"].mean()), 4),
            "positive_cagr_share_pct": round(float((ok["cagr"] > 0).mean() * 100.0), 4),
        }
    )
    return out


def compute_metric_deltas(raw_metrics: dict[str, Any], gold_metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "symbols_in_universe",
        "symbols_with_backtest",
        "coverage_pct",
        "avg_cagr_pct",
        "median_cagr_pct",
        "avg_win_rate_pct",
        "avg_max_drawdown_pct",
        "avg_sharpe",
        "positive_cagr_share_pct",
    ]
    deltas: dict[str, Any] = {}
    for key in keys:
        raw_val = raw_metrics.get(key)
        gold_val = gold_metrics.get(key)
        if raw_val is None or gold_val is None:
            deltas[key] = None
            continue
        raw_f = _safe_float(raw_val)
        gold_f = _safe_float(gold_val)
        if np.isnan(raw_f) or np.isnan(gold_f):
            deltas[key] = None
            continue
        deltas[key] = round(gold_f - raw_f, 4)
    return deltas


def build_symbol_comparison(
    *,
    raw_universe: pd.DataFrame,
    gold_universe: pd.DataFrame,
    results_map: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    raw_view = raw_universe.rename(columns={"score": "raw_score", "rank": "raw_rank"})[["symbol", "raw_score", "raw_rank"]]
    gold_view = gold_universe.rename(columns={"score": "gold_score", "rank": "gold_rank"})[["symbol", "gold_score", "gold_rank"]]
    merged = pd.merge(raw_view, gold_view, on="symbol", how="outer")
    merged["in_raw"] = merged["raw_rank"].notna()
    merged["in_gold"] = merged["gold_rank"].notna()

    def extract(sym: str, key: str) -> Any:
        rec = results_map.get(sym, {})
        return rec.get(key)

    for prefix in ("raw", "gold"):
        side_mask = merged[f"in_{prefix}"]
        merged[f"{prefix}_status"] = np.where(
            side_mask,
            merged["symbol"].map(lambda s: extract(s, "status")),
            None,
        )
        merged[f"{prefix}_cagr"] = np.where(
            side_mask,
            merged["symbol"].map(lambda s: _safe_float(extract(s, "cagr"))),
            np.nan,
        )
        merged[f"{prefix}_win_rate"] = np.where(
            side_mask,
            merged["symbol"].map(lambda s: _safe_float(extract(s, "win_rate"))),
            np.nan,
        )
        merged[f"{prefix}_max_drawdown"] = np.where(
            side_mask,
            merged["symbol"].map(lambda s: _safe_float(extract(s, "max_drawdown"))),
            np.nan,
        )
        merged[f"{prefix}_sharpe"] = np.where(
            side_mask,
            merged["symbol"].map(lambda s: _safe_float(extract(s, "sharpe_ratio"))),
            np.nan,
        )

    merged["delta_cagr_gold_minus_raw"] = merged["gold_cagr"] - merged["raw_cagr"]
    merged["delta_sharpe_gold_minus_raw"] = merged["gold_sharpe"] - merged["raw_sharpe"]
    merged = merged.sort_values(["in_raw", "raw_rank", "in_gold", "gold_rank"], ascending=[False, True, False, True])
    return merged.reset_index(drop=True)


def persist_comparison_to_db(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    run_ts_utc: str,
    summary: dict[str, Any],
    symbol_df: pd.DataFrame,
) -> None:
    run_row = {
        "run_id": run_id,
        "run_ts_utc": run_ts_utc,
        "as_of_date": summary["as_of_date"],
        "raw_table": summary["raw_table"],
        "gold_table": summary["gold_table"],
        "period": summary["period"],
        "top_n": int(summary["top_n"]),
        "raw_metrics_json": json.dumps(summary["raw_metrics"], separators=(",", ":")),
        "gold_metrics_json": json.dumps(summary["gold_metrics"], separators=(",", ":")),
        "delta_metrics_json": json.dumps(summary["delta_metrics"], separators=(",", ":")),
    }
    pd.DataFrame([run_row]).to_sql("backtest_comparison_runs", conn, if_exists="append", index=False)

    if symbol_df.empty:
        return
    persist_cols = [
        "symbol",
        "in_raw",
        "in_gold",
        "raw_rank",
        "gold_rank",
        "raw_cagr",
        "gold_cagr",
        "delta_cagr_gold_minus_raw",
        "raw_sharpe",
        "gold_sharpe",
        "delta_sharpe_gold_minus_raw",
        "raw_status",
        "gold_status",
    ]
    out = symbol_df[persist_cols].copy()
    out.insert(0, "run_id", run_id)
    out.insert(1, "run_ts_utc", run_ts_utc)
    out.to_sql("backtest_comparison_symbols", conn, if_exists="append", index=False)


def build_report_markdown(summary: dict[str, Any], top_improve: pd.DataFrame, top_decline: pd.DataFrame) -> str:
    raw = summary["raw_metrics"]
    gold = summary["gold_metrics"]
    delta = summary["delta_metrics"]
    lines = [
        "# Raw vs Gold Backtest Comparison",
        "",
        f"- Run ID: `{summary['run_id']}`",
        f"- As Of Date: `{summary['as_of_date']}`",
        f"- Period: `{summary['period']}`",
        f"- Universe Size: top `{summary['top_n']}`",
        f"- Raw Table: `{summary['raw_table']}`",
        f"- Gold Table: `{summary['gold_table']}`",
        "",
        "## KPI Snapshot",
        "",
        "| Metric | Raw | Gold | Delta (Gold - Raw) |",
        "|---|---:|---:|---:|",
        f"| Coverage % | {raw['coverage_pct']} | {gold['coverage_pct']} | {delta['coverage_pct']} |",
        f"| Avg CAGR % | {raw['avg_cagr_pct']} | {gold['avg_cagr_pct']} | {delta['avg_cagr_pct']} |",
        f"| Median CAGR % | {raw['median_cagr_pct']} | {gold['median_cagr_pct']} | {delta['median_cagr_pct']} |",
        f"| Avg Win Rate % | {raw['avg_win_rate_pct']} | {gold['avg_win_rate_pct']} | {delta['avg_win_rate_pct']} |",
        f"| Avg Max Drawdown % | {raw['avg_max_drawdown_pct']} | {gold['avg_max_drawdown_pct']} | {delta['avg_max_drawdown_pct']} |",
        f"| Avg Sharpe | {raw['avg_sharpe']} | {gold['avg_sharpe']} | {delta['avg_sharpe']} |",
        "",
    ]

    if not top_improve.empty:
        lines.extend(
            [
                "## Top CAGR Improvements (Gold - Raw)",
                "",
                top_improve.to_markdown(index=False),
                "",
            ]
        )
    if not top_decline.empty:
        lines.extend(
            [
                "## Top CAGR Declines (Gold - Raw)",
                "",
                top_decline.to_markdown(index=False),
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare raw vs gold universe backtest KPIs and write delta reports."
    )
    parser.add_argument("--db-path", default="stocks.db")
    parser.add_argument("--raw-table", default="multibaggers")
    parser.add_argument("--gold-table", default="multibaggers_gold")
    parser.add_argument("--symbol-column", default="symbol")
    parser.add_argument("--score-column", default="score")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--period", default="5y")
    parser.add_argument("--as-of-date", default=None, help="Optional YYYY-MM-DD metadata only.")
    parser.add_argument("--out-dir", default="reports/backtest_compare")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--write-db", action="store_true", help="Persist comparison run and symbol deltas to SQLite.")
    args = parser.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    as_of_date = args.as_of_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_ts_utc = datetime.now(timezone.utc).isoformat()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(args.db_path) as conn:
        raw_universe = load_top_universe(
            conn,
            table_name=args.raw_table,
            symbol_col=args.symbol_column,
            score_col=args.score_column,
            limit=args.top_n,
        )
        gold_universe = load_top_universe(
            conn,
            table_name=args.gold_table,
            symbol_col=args.symbol_column,
            score_col=args.score_column,
            limit=args.top_n,
        )

    if raw_universe.empty:
        raise RuntimeError(f"No symbols found in raw table '{args.raw_table}'")
    if gold_universe.empty:
        raise RuntimeError(f"No symbols found in gold table '{args.gold_table}'")

    combined_symbols = sorted(set(raw_universe["symbol"]).union(set(gold_universe["symbol"])))
    engine = VectorBTEngine(period=args.period)
    results_map = engine.run_batch_momentum_backtest(combined_symbols)

    symbol_df = build_symbol_comparison(
        raw_universe=raw_universe,
        gold_universe=gold_universe,
        results_map=results_map,
    )

    raw_metrics = summarize_universe(
        symbol_df[symbol_df["in_raw"]][
            ["symbol", "raw_status", "raw_cagr", "raw_win_rate", "raw_max_drawdown", "raw_sharpe"]
        ].rename(
            columns={
                "raw_status": "status",
                "raw_cagr": "cagr",
                "raw_win_rate": "win_rate",
                "raw_max_drawdown": "max_drawdown",
                "raw_sharpe": "sharpe_ratio",
            }
        ),
        total_symbols=int(raw_universe["symbol"].nunique()),
    )
    gold_metrics = summarize_universe(
        symbol_df[symbol_df["in_gold"]][
            ["symbol", "gold_status", "gold_cagr", "gold_win_rate", "gold_max_drawdown", "gold_sharpe"]
        ].rename(
            columns={
                "gold_status": "status",
                "gold_cagr": "cagr",
                "gold_win_rate": "win_rate",
                "gold_max_drawdown": "max_drawdown",
                "gold_sharpe": "sharpe_ratio",
            }
        ),
        total_symbols=int(gold_universe["symbol"].nunique()),
    )
    delta_metrics = compute_metric_deltas(raw_metrics, gold_metrics)

    summary = {
        "run_id": run_id,
        "run_ts_utc": run_ts_utc,
        "as_of_date": as_of_date,
        "db_path": args.db_path,
        "raw_table": args.raw_table,
        "gold_table": args.gold_table,
        "symbol_column": args.symbol_column,
        "score_column": args.score_column,
        "top_n": args.top_n,
        "period": args.period,
        "raw_metrics": raw_metrics,
        "gold_metrics": gold_metrics,
        "delta_metrics": delta_metrics,
    }

    top_improve = symbol_df.dropna(subset=["delta_cagr_gold_minus_raw"]).sort_values(
        "delta_cagr_gold_minus_raw", ascending=False
    )[["symbol", "raw_cagr", "gold_cagr", "delta_cagr_gold_minus_raw"]].head(10)
    top_decline = symbol_df.dropna(subset=["delta_cagr_gold_minus_raw"]).sort_values(
        "delta_cagr_gold_minus_raw", ascending=True
    )[["symbol", "raw_cagr", "gold_cagr", "delta_cagr_gold_minus_raw"]].head(10)

    summary_path = out_dir / "raw_vs_gold_backtest_summary.json"
    csv_path = out_dir / "raw_vs_gold_backtest_symbols.csv"
    report_path = out_dir / "raw_vs_gold_backtest_report.md"

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    symbol_df.to_csv(csv_path, index=False)
    report_path.write_text(
        build_report_markdown(summary, top_improve=top_improve, top_decline=top_decline),
        encoding="utf-8",
    )

    if args.write_db:
        with sqlite3.connect(args.db_path) as conn:
            persist_comparison_to_db(
                conn,
                run_id=run_id,
                run_ts_utc=run_ts_utc,
                summary=summary,
                symbol_df=symbol_df,
            )

    print(f"Comparison complete. Run ID: {run_id}")
    print(f"Summary: {summary_path}")
    print(f"Symbols CSV: {csv_path}")
    print(f"Report: {report_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
