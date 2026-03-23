import argparse
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


SECTOR_MAP = {
    "BASIC MATERIALS": "Basic Materials",
    "COMMUNICATION SERVICES": "Communication Services",
    "CONSUMER CYCLICAL": "Consumer Cyclical",
    "CONSUMER DEFENSIVE": "Consumer Defensive",
    "ENERGY": "Energy",
    "FINANCIAL SERVICES": "Financial Services",
    "HEALTHCARE": "Healthcare",
    "INDUSTRIALS": "Industrials",
    "REAL ESTATE": "Real Estate",
    "TECHNOLOGY": "Technology",
    "UNKNOWN": "Unknown",
    "UTILITIES": "Utilities",
}

DEFAULT_NUMERIC_COLUMNS = [
    "price",
    "score",
    "sales_growth",
    "sales_cagr_5y",
    "roe",
    "avg_roe_5y",
    "pe_ratio",
    "debt_equity",
    "cfo_pat_ratio",
    "market_cap_cr",
    "ml_predicted_return",
]
RULE_TYPES = {
    "inf_any_numeric",
    "threshold_upper",
    "threshold_lower",
    "threshold_abs",
    "group_percentile_upper",
    "group_percentile_abs",
    "max_age_days",
    "missing_any",
}
RULE_CATEGORIES = {"hard_fail", "warning"}
FILTER_MODES = {"hard_fail_only", "all_issues"}
DEFAULT_MONITOR_THRESHOLDS = {
    "warning_share_max_pct": 80.0,
    "hard_fail_share_max_pct": 5.0,
    "null_spike_abs_pct": 5.0,
    "hard_fail_spike_rel": 0.5,
    "rule_spike_rel": 0.5,
}


def normalize_sector(value: object) -> str:
    if pd.isna(value):
        return "Unknown"
    raw = str(value).strip()
    if not raw:
        return "Unknown"
    key = " ".join(raw.upper().split())
    if key in SECTOR_MAP:
        return SECTOR_MAP[key]
    return raw.title()


def load_table(conn: sqlite3.Connection, table_name: str) -> pd.DataFrame:
    return pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)


def _false_series(index: pd.Index) -> pd.Series:
    return pd.Series(False, index=index, dtype=bool)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _rule_columns(rule: dict[str, Any]) -> list[str]:
    cols: list[str] = []
    if isinstance(rule.get("column"), str):
        cols.append(rule["column"])
    if isinstance(rule.get("columns"), list):
        cols.extend([str(x) for x in rule["columns"] if isinstance(x, str)])
    deduped: list[str] = []
    seen: set[str] = set()
    for col in cols:
        if col not in seen:
            seen.add(col)
            deduped.append(col)
    return deduped


def _validate_rule(rule: Any, idx: int) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise ValueError(f"Invalid rule at index {idx}: expected object")
    code = rule.get("code")
    category = rule.get("category")
    rule_type = rule.get("type")
    if not isinstance(code, str) or not code.strip():
        raise ValueError(f"Invalid rule at index {idx}: 'code' is required")
    if category not in RULE_CATEGORIES:
        raise ValueError(
            f"Rule '{code}' has invalid category '{category}'. Expected one of {sorted(RULE_CATEGORIES)}"
        )
    if rule_type not in RULE_TYPES:
        raise ValueError(
            f"Rule '{code}' has invalid type '{rule_type}'. Expected one of {sorted(RULE_TYPES)}"
        )
    if rule_type in {"threshold_upper", "threshold_lower", "threshold_abs"}:
        if rule.get("threshold") is None:
            raise ValueError(f"Rule '{code}' requires 'threshold'")
        if not _rule_columns(rule):
            raise ValueError(f"Rule '{code}' requires 'column' or 'columns'")
    if rule_type in {"group_percentile_upper", "group_percentile_abs"}:
        if not _rule_columns(rule):
            raise ValueError(f"Rule '{code}' requires 'column' or 'columns'")
        pct = rule.get("percentile")
        if pct is None:
            raise ValueError(f"Rule '{code}' requires 'percentile'")
        try:
            pct_val = float(pct)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Rule '{code}' has non-numeric percentile '{pct}'") from exc
        if pct_val <= 0 or pct_val >= 1:
            raise ValueError(f"Rule '{code}' percentile must be between 0 and 1 (exclusive)")
        min_group_size = rule.get("min_group_size", 20)
        if int(min_group_size) <= 0:
            raise ValueError(f"Rule '{code}' min_group_size must be > 0")
        if rule.get("group_by") is not None and not isinstance(rule.get("group_by"), str):
            raise ValueError(f"Rule '{code}' group_by must be a string if provided")
    if rule_type == "max_age_days" and rule.get("threshold") is None:
        raise ValueError(f"Rule '{code}' requires 'threshold' (max age days)")
    return rule


def load_rules_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Rules config not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError("Rules config must be a YAML object")

    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ValueError("Rules config must contain a non-empty 'rules' list")

    rules = [_validate_rule(rule, idx) for idx, rule in enumerate(rules_raw)]
    rule_codes = [rule["code"] for rule in rules]
    if len(rule_codes) != len(set(rule_codes)):
        raise ValueError("Rule codes must be unique")

    refresh_raw = raw.get("refresh") or {}
    if not isinstance(refresh_raw, dict):
        raise ValueError("'refresh' must be an object if provided")

    refresh_cfg = {
        "enabled": bool(refresh_raw.get("enabled", False)),
        "source_table": refresh_raw.get("source_table", "fundamentals_pit"),
        "source_key_column": refresh_raw.get("source_key_column", "symbol"),
        "source_date_column": refresh_raw.get("source_date_column", "as_of_date"),
        "target_key_column": refresh_raw.get("target_key_column", "symbol"),
        "target_date_column": refresh_raw.get("target_date_column", "as_of_date"),
        "target_tables": refresh_raw.get("target_tables", []),
        "min_age_days": int(refresh_raw.get("min_age_days", 7)),
        "require_newer_source": bool(refresh_raw.get("require_newer_source", True)),
        "allow_fill_missing_when_stale": bool(refresh_raw.get("allow_fill_missing_when_stale", True)),
        "overwrite_non_null": bool(refresh_raw.get("overwrite_non_null", True)),
        "update_columns": refresh_raw.get("update_columns", []),
    }
    if refresh_cfg["enabled"]:
        if not isinstance(refresh_cfg["target_tables"], list):
            raise ValueError("refresh.target_tables must be a list")
        if not isinstance(refresh_cfg["update_columns"], list):
            raise ValueError("refresh.update_columns must be a list")
        if refresh_cfg["min_age_days"] < 0:
            raise ValueError("refresh.min_age_days must be >= 0")

    monitor_raw = raw.get("monitor") or {}
    if not isinstance(monitor_raw, dict):
        raise ValueError("'monitor' must be an object if provided")
    monitor_thresholds_raw = monitor_raw.get("thresholds") or {}
    if not isinstance(monitor_thresholds_raw, dict):
        raise ValueError("monitor.thresholds must be an object")
    thresholds = dict(DEFAULT_MONITOR_THRESHOLDS)
    for key, default_value in DEFAULT_MONITOR_THRESHOLDS.items():
        val = monitor_thresholds_raw.get(key, default_value)
        thresholds[key] = float(val)
    critical_columns = monitor_raw.get("critical_columns") or {}
    if not isinstance(critical_columns, dict):
        raise ValueError("monitor.critical_columns must be an object")
    monitor_cfg = {
        "enabled": bool(monitor_raw.get("enabled", True)),
        "thresholds": thresholds,
        "critical_columns": {
            str(tbl): [str(col) for col in cols]
            for tbl, cols in critical_columns.items()
            if isinstance(cols, list)
        },
    }

    cfg: dict[str, Any] = {
        "tables": raw.get("tables") or ["multibaggers", "fundamentals_pit"],
        "normalization": raw.get("normalization") or {"sector": True},
        "numeric_columns": raw.get("numeric_columns") or DEFAULT_NUMERIC_COLUMNS,
        "filter_mode": raw.get("filter_mode") or "hard_fail_only",
        "rules": rules,
        "as_of_date": raw.get("as_of_date"),
        "refresh": refresh_cfg,
        "monitor": monitor_cfg,
    }
    if not isinstance(cfg["tables"], list) or not cfg["tables"]:
        raise ValueError("'tables' must be a non-empty list")
    if cfg["filter_mode"] not in FILTER_MODES:
        raise ValueError(f"Invalid filter_mode '{cfg['filter_mode']}'. Expected one of {sorted(FILTER_MODES)}")
    return cfg


def build_latest_source_snapshot(
    source_df: pd.DataFrame,
    *,
    key_column: str,
    date_column: str,
) -> pd.DataFrame:
    if key_column not in source_df.columns:
        raise ValueError(f"Refresh source missing key column '{key_column}'")
    if date_column not in source_df.columns:
        raise ValueError(f"Refresh source missing date column '{date_column}'")

    src = source_df.copy()
    src["_source_date_ts"] = pd.to_datetime(src[date_column], errors="coerce")
    src = src.sort_values("_source_date_ts")
    latest = src.dropna(subset=[key_column]).drop_duplicates(subset=[key_column], keep="last")
    latest = latest.set_index(key_column, drop=False)
    return latest


def refresh_stale_rows(
    df: pd.DataFrame,
    *,
    table_name: str,
    refresh_cfg: dict[str, Any],
    source_latest: pd.DataFrame | None,
    as_of_ref: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    default_summary: dict[str, Any] = {
        "enabled": bool(refresh_cfg.get("enabled", False)),
        "applied": False,
        "table_eligible": False,
        "rows_refreshed": 0,
        "rows_filled_missing_from_source": 0,
        "rows_stale_eligible": 0,
        "rows_with_source_match": 0,
        "rows_with_newer_source": 0,
        "fields_updated_total": 0,
        "field_updates_by_column": {},
    }

    if not refresh_cfg.get("enabled", False):
        return df, default_summary

    target_tables = set(str(x) for x in (refresh_cfg.get("target_tables") or []))
    if target_tables and table_name not in target_tables:
        return df, default_summary

    target_key = str(refresh_cfg.get("target_key_column", "symbol"))
    target_date_col = str(refresh_cfg.get("target_date_column", "as_of_date"))
    min_age_days = int(refresh_cfg.get("min_age_days", 7))
    require_newer_source = bool(refresh_cfg.get("require_newer_source", True))
    allow_fill_missing_when_stale = bool(refresh_cfg.get("allow_fill_missing_when_stale", True))
    overwrite_non_null = bool(refresh_cfg.get("overwrite_non_null", True))
    update_columns = [str(c) for c in (refresh_cfg.get("update_columns") or [])]

    summary = dict(default_summary)
    summary["table_eligible"] = True

    if source_latest is None or source_latest.empty:
        summary["skip_reason"] = "empty source snapshot"
        return df, summary
    if target_key not in df.columns:
        summary["skip_reason"] = f"target key column '{target_key}' missing"
        return df, summary
    if target_date_col not in df.columns:
        summary["skip_reason"] = f"target date column '{target_date_col}' missing"
        return df, summary

    src_key = str(refresh_cfg.get("source_key_column", "symbol"))
    src_date_col = str(refresh_cfg.get("source_date_column", "as_of_date"))
    src_date_ts_col = "_source_date_ts"
    if src_date_ts_col not in source_latest.columns:
        summary["skip_reason"] = f"source snapshot missing '{src_date_ts_col}'"
        return df, summary

    out = df.copy()
    tgt_date_ts = pd.to_datetime(out[target_date_col], errors="coerce")
    out[target_date_col] = tgt_date_ts.dt.strftime("%Y-%m-%d")
    tgt_age_days = (as_of_ref - tgt_date_ts).dt.days
    stale_mask = (tgt_age_days > min_age_days).fillna(False)
    summary["rows_stale_eligible"] = int(stale_mask.sum())

    source_match_mask = out[target_key].isin(source_latest.index)
    summary["rows_with_source_match"] = int(source_match_mask.sum())

    src_dates = out[target_key].map(source_latest[src_date_ts_col])
    newer_source_mask = source_match_mask & (
        tgt_date_ts.isna() | (src_dates > tgt_date_ts)
    )
    if not require_newer_source:
        newer_source_mask = source_match_mask & src_dates.notna()
    summary["rows_with_newer_source"] = int(newer_source_mask.sum())

    eligible_refresh_mask = stale_mask & newer_source_mask
    fill_missing_base = stale_mask & source_match_mask & (~newer_source_mask)

    updated_cols_text = pd.Series([""] * len(out), index=out.index, dtype=object)
    updated_col_counts = pd.Series([0] * len(out), index=out.index, dtype=int)
    rows_filled_missing = _false_series(out.index)
    field_updates_by_column: dict[str, int] = {}

    if src_date_col in source_latest.columns:
        src_dates_str = out[target_key].map(source_latest[src_date_col])
        date_changed = eligible_refresh_mask & src_dates_str.notna()
        if date_changed.any():
            out.loc[date_changed, target_date_col] = src_dates_str[date_changed].astype(str)
            updated_cols_text.loc[date_changed] = np.where(
                updated_cols_text.loc[date_changed] == "",
                target_date_col,
                updated_cols_text.loc[date_changed] + "|" + target_date_col,
            )
            updated_col_counts.loc[date_changed] += 1
            field_updates_by_column[target_date_col] = int(date_changed.sum())

    for col in update_columns:
        if col not in out.columns or col not in source_latest.columns:
            continue
        src_vals = out[target_key].map(source_latest[col])
        target_isna = out[col].isna()
        can_update = eligible_refresh_mask & src_vals.notna()
        if not overwrite_non_null:
            can_update = can_update & target_isna
        if allow_fill_missing_when_stale:
            can_update = can_update | (fill_missing_base & src_vals.notna() & target_isna)
        different = ~(out[col].eq(src_vals) | (out[col].isna() & src_vals.isna()))
        changed = can_update & different
        if not changed.any():
            continue
        rows_filled_missing = rows_filled_missing | (changed & target_isna)
        out.loc[changed, col] = src_vals[changed]
        updated_cols_text.loc[changed] = np.where(
            updated_cols_text.loc[changed] == "",
            col,
            updated_cols_text.loc[changed] + "|" + col,
        )
        updated_col_counts.loc[changed] += 1
        field_updates_by_column[col] = int(changed.sum())

    out["refresh_source_table"] = refresh_cfg.get("source_table")
    out["refresh_source_key_column"] = src_key
    out["refresh_source_date"] = src_dates.dt.strftime("%Y-%m-%d")
    out["refresh_candidate"] = eligible_refresh_mask.fillna(False)
    out["refresh_updated_columns"] = updated_cols_text
    out["refresh_updated_column_count"] = updated_col_counts
    out["refresh_filled_missing"] = rows_filled_missing
    out["refresh_applied"] = out["refresh_updated_column_count"] > 0

    summary["applied"] = True
    summary["rows_refreshed"] = int(out["refresh_applied"].sum())
    summary["rows_filled_missing_from_source"] = int(rows_filled_missing.sum())
    summary["fields_updated_total"] = int(out["refresh_updated_column_count"].sum())
    summary["field_updates_by_column"] = field_updates_by_column
    summary["update_columns_considered"] = update_columns
    return out, summary


def build_null_profile(df: pd.DataFrame, columns: list[str] | None) -> dict[str, Any]:
    if not columns:
        return {}
    profile: dict[str, Any] = {}
    n_rows = len(df)
    for col in columns:
        if col not in df.columns:
            profile[col] = {"missing_column": True}
            continue
        null_count = int(df[col].isna().sum())
        null_pct = round((null_count / n_rows * 100.0) if n_rows else 0.0, 2)
        profile[col] = {"null_count": null_count, "null_pct": null_pct}
    return profile


def load_summary_file(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _safe_pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator) * 100.0


def _alert(
    *,
    table_name: str,
    code: str,
    severity: str,
    metric: str,
    current_value: float,
    threshold: float | None,
    message: str,
    baseline_value: float | None = None,
) -> dict[str, Any]:
    return {
        "table_name": table_name,
        "code": code,
        "severity": severity,
        "metric": metric,
        "current_value": round(float(current_value), 4),
        "baseline_value": (round(float(baseline_value), 4) if baseline_value is not None else None),
        "threshold": (round(float(threshold), 4) if threshold is not None else None),
        "message": message,
    }


def build_alerts(
    current_summary: dict[str, Any],
    *,
    monitor_cfg: dict[str, Any],
    baseline_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not monitor_cfg.get("enabled", True):
        return []

    thresholds = monitor_cfg.get("thresholds", DEFAULT_MONITOR_THRESHOLDS)
    warning_share_max_pct = float(thresholds.get("warning_share_max_pct", DEFAULT_MONITOR_THRESHOLDS["warning_share_max_pct"]))
    hard_fail_share_max_pct = float(thresholds.get("hard_fail_share_max_pct", DEFAULT_MONITOR_THRESHOLDS["hard_fail_share_max_pct"]))
    null_spike_abs_pct = float(thresholds.get("null_spike_abs_pct", DEFAULT_MONITOR_THRESHOLDS["null_spike_abs_pct"]))
    hard_fail_spike_rel = float(thresholds.get("hard_fail_spike_rel", DEFAULT_MONITOR_THRESHOLDS["hard_fail_spike_rel"]))
    rule_spike_rel = float(thresholds.get("rule_spike_rel", DEFAULT_MONITOR_THRESHOLDS["rule_spike_rel"]))

    baseline_tables = (baseline_summary or {}).get("tables", {})
    critical_columns_by_table = monitor_cfg.get("critical_columns", {})
    alerts: list[dict[str, Any]] = []

    for table_name, table_summary in current_summary.get("tables", {}).items():
        rows_input = int(table_summary.get("rows_input", 0))
        row_counts = table_summary.get("row_state_counts", {})
        hard_fail_rows = int(row_counts.get("rows_with_hard_fail", 0))
        warning_rows = int(row_counts.get("rows_with_warning", 0))
        hard_fail_share_pct = _safe_pct(hard_fail_rows, rows_input)
        warning_share_pct = _safe_pct(warning_rows, rows_input)

        if hard_fail_share_pct > hard_fail_share_max_pct:
            alerts.append(
                _alert(
                    table_name=table_name,
                    code="HIGH_HARD_FAIL_SHARE",
                    severity="critical",
                    metric="hard_fail_share_pct",
                    current_value=hard_fail_share_pct,
                    threshold=hard_fail_share_max_pct,
                    message=(
                        f"Hard-fail share {hard_fail_share_pct:.2f}% exceeds "
                        f"threshold {hard_fail_share_max_pct:.2f}%."
                    ),
                )
            )
        if warning_share_pct > warning_share_max_pct:
            alerts.append(
                _alert(
                    table_name=table_name,
                    code="HIGH_WARNING_SHARE",
                    severity="warning",
                    metric="warning_share_pct",
                    current_value=warning_share_pct,
                    threshold=warning_share_max_pct,
                    message=(
                        f"Warning share {warning_share_pct:.2f}% exceeds "
                        f"threshold {warning_share_max_pct:.2f}%."
                    ),
                )
            )

        baseline_table = baseline_tables.get(table_name) if isinstance(baseline_tables, dict) else None
        if isinstance(baseline_table, dict):
            baseline_row_counts = baseline_table.get("row_state_counts", {})
            prev_rows_input = int(baseline_table.get("rows_input", 0))
            prev_hard_fail = int(baseline_row_counts.get("rows_with_hard_fail", 0))
            prev_hard_fail_share_pct = _safe_pct(prev_hard_fail, prev_rows_input)
            if prev_hard_fail_share_pct > 0:
                hard_fail_rel_change = (hard_fail_share_pct - prev_hard_fail_share_pct) / prev_hard_fail_share_pct
                if hard_fail_rel_change > hard_fail_spike_rel:
                    alerts.append(
                        _alert(
                            table_name=table_name,
                            code="HARD_FAIL_SHARE_SPIKE",
                            severity="critical",
                            metric="hard_fail_share_rel_change",
                            current_value=hard_fail_rel_change,
                            baseline_value=prev_hard_fail_share_pct,
                            threshold=hard_fail_spike_rel,
                            message=(
                                f"Hard-fail share changed from {prev_hard_fail_share_pct:.2f}% to "
                                f"{hard_fail_share_pct:.2f}% (relative {hard_fail_rel_change:.2f})."
                            ),
                        )
                    )

            current_rules = table_summary.get("rules", {})
            baseline_rules = baseline_table.get("rules", {})
            if isinstance(current_rules, dict) and isinstance(baseline_rules, dict):
                for code, rule in current_rules.items():
                    if not isinstance(rule, dict):
                        continue
                    if rule.get("category") != "hard_fail":
                        continue
                    baseline_rule = baseline_rules.get(code, {})
                    if not isinstance(baseline_rule, dict):
                        continue
                    curr_pct = float(rule.get("trigger_pct", 0.0))
                    prev_pct = float(baseline_rule.get("trigger_pct", 0.0))
                    if prev_pct <= 0:
                        continue
                    rel_change = (curr_pct - prev_pct) / prev_pct
                    if rel_change > rule_spike_rel:
                        alerts.append(
                            _alert(
                                table_name=table_name,
                                code="RULE_TRIGGER_SPIKE",
                                severity="warning",
                                metric=f"rule_trigger_rel_change:{code}",
                                current_value=rel_change,
                                baseline_value=prev_pct,
                                threshold=rule_spike_rel,
                                message=(
                                    f"Rule '{code}' trigger % changed from {prev_pct:.2f} to "
                                    f"{curr_pct:.2f} (relative {rel_change:.2f})."
                                ),
                            )
                        )

            current_null_profile = table_summary.get("null_profile", {})
            baseline_null_profile = baseline_table.get("null_profile", {})
            if isinstance(current_null_profile, dict) and isinstance(baseline_null_profile, dict):
                critical_columns = critical_columns_by_table.get(table_name, [])
                for col in critical_columns:
                    current_col = current_null_profile.get(col, {})
                    baseline_col = baseline_null_profile.get(col, {})
                    if not isinstance(current_col, dict) or not isinstance(baseline_col, dict):
                        continue
                    if "null_pct" not in current_col or "null_pct" not in baseline_col:
                        continue
                    curr_null_pct = float(current_col["null_pct"])
                    prev_null_pct = float(baseline_col["null_pct"])
                    delta_null_pct = curr_null_pct - prev_null_pct
                    if delta_null_pct > null_spike_abs_pct:
                        alerts.append(
                            _alert(
                                table_name=table_name,
                                code="NULL_SPIKE",
                                severity="warning",
                                metric=f"null_pct_delta:{col}",
                                current_value=delta_null_pct,
                                baseline_value=prev_null_pct,
                                threshold=null_spike_abs_pct,
                                message=(
                                    f"Null % for '{col}' changed from {prev_null_pct:.2f}% to "
                                    f"{curr_null_pct:.2f}% (delta {delta_null_pct:.2f}pp)."
                                ),
                            )
                        )

    return alerts


def persist_quality_telemetry(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    run_ts_utc: str,
    as_of_date: str,
    summary: dict[str, Any],
    alerts: list[dict[str, Any]],
) -> None:
    run_rows: list[dict[str, Any]] = []
    for table_name, table_summary in summary.get("tables", {}).items():
        row_counts = table_summary.get("row_state_counts", {})
        run_rows.append(
            {
                "run_id": run_id,
                "run_ts_utc": run_ts_utc,
                "as_of_date": as_of_date,
                "table_name": table_name,
                "rows_input": int(table_summary.get("rows_input", 0)),
                "rows_cleaned": int(table_summary.get("rows_cleaned", 0)),
                "rows_filtered": int(table_summary.get("rows_filtered", 0)),
                "removed_rows": int(table_summary.get("removed_rows", 0)),
                "filter_mode": str(table_summary.get("filter_mode", "")),
                "rows_with_hard_fail": int(row_counts.get("rows_with_hard_fail", 0)),
                "rows_with_warning": int(row_counts.get("rows_with_warning", 0)),
                "rows_with_any_issue": int(row_counts.get("rows_with_any_issue", 0)),
                "rules_json": json.dumps(table_summary.get("rules", {}), separators=(",", ":")),
                "null_profile_json": json.dumps(table_summary.get("null_profile", {}), separators=(",", ":")),
                "refresh_json": json.dumps(table_summary.get("refresh", {}), separators=(",", ":")),
            }
        )
    if run_rows:
        pd.DataFrame(run_rows).to_sql("data_quality_runs", conn, if_exists="append", index=False)

    if alerts:
        alert_rows = []
        for alert in alerts:
            alert_rows.append(
                {
                    "run_id": run_id,
                    "run_ts_utc": run_ts_utc,
                    "as_of_date": as_of_date,
                    "table_name": alert.get("table_name"),
                    "code": alert.get("code"),
                    "severity": alert.get("severity"),
                    "metric": alert.get("metric"),
                    "current_value": alert.get("current_value"),
                    "baseline_value": alert.get("baseline_value"),
                    "threshold": alert.get("threshold"),
                    "message": alert.get("message"),
                }
            )
        pd.DataFrame(alert_rows).to_sql("data_quality_alerts", conn, if_exists="append", index=False)


def _evaluate_rule(
    df: pd.DataFrame,
    rule: dict[str, Any],
    *,
    as_of_ref: pd.Timestamp,
    inf_any_numeric_mask: pd.Series,
) -> tuple[pd.Series, dict[str, Any]]:
    code = rule["code"]
    rule_type = rule["type"]
    meta: dict[str, Any] = {"applied": True}

    if rule_type == "inf_any_numeric":
        return inf_any_numeric_mask.copy(), meta

    if rule_type == "max_age_days":
        column = str(rule.get("column") or "as_of_date")
        if column not in df.columns:
            return _false_series(df.index), {
                "applied": False,
                "skip_reason": f"missing column '{column}'",
                "missing_columns": [column],
            }
        age_col = str(rule.get("age_output_column") or ("as_of_age_days" if column == "as_of_date" else f"{column}_age_days"))
        threshold = float(rule["threshold"])
        dt = pd.to_datetime(df[column], errors="coerce")
        if column == "as_of_date":
            df[column] = dt.dt.strftime("%Y-%m-%d")
        df[age_col] = (as_of_ref - dt).dt.days
        return (df[age_col] > threshold).fillna(False), {
            "applied": True,
            "evaluated_columns": [column],
            "threshold": threshold,
            "age_output_column": age_col,
        }

    if rule_type in {"group_percentile_upper", "group_percentile_abs"}:
        cols = _rule_columns(rule)
        existing_cols = [col for col in cols if col in df.columns]
        missing_cols = [col for col in cols if col not in df.columns]
        if not existing_cols:
            return _false_series(df.index), {
                "applied": False,
                "skip_reason": "all referenced columns are missing",
                "missing_columns": missing_cols,
            }

        percentile = float(rule["percentile"])
        group_by = str(rule.get("group_by", "sector"))
        min_group_size = int(rule.get("min_group_size", 20))
        fallback_threshold = rule.get("fallback_threshold")
        fallback_threshold_float = float(fallback_threshold) if fallback_threshold is not None else None

        if group_by in df.columns:
            group_key = df[group_by].fillna("Unknown").astype(str)
            group_by_missing = False
        else:
            group_key = pd.Series(["__ALL__"] * len(df), index=df.index, dtype=object)
            group_by_missing = True

        mask = _false_series(df.index)
        threshold_columns: list[str] = []
        evaluated_columns: list[str] = []
        for col in existing_cols:
            values = df[col].abs() if rule_type == "group_percentile_abs" else df[col]
            valid = values.notna()
            if not valid.any():
                threshold_col = f"threshold_{_slugify(code)}_{_slugify(col)}"
                df[threshold_col] = np.nan
                threshold_columns.append(threshold_col)
                evaluated_columns.append(col)
                continue

            grouped = pd.DataFrame({"group_key": group_key, "value": values})
            valid_grouped = grouped.loc[valid]
            group_q = valid_grouped.groupby("group_key")["value"].quantile(percentile)
            group_size = valid_grouped.groupby("group_key")["value"].size()
            group_q = group_q.where(group_size >= min_group_size)
            global_q = float(valid_grouped["value"].quantile(percentile))

            row_threshold = group_key.map(group_q)
            if fallback_threshold_float is not None:
                row_threshold = row_threshold.fillna(fallback_threshold_float)
            else:
                row_threshold = row_threshold.fillna(global_q)

            threshold_col = f"threshold_{_slugify(code)}_{_slugify(col)}"
            df[threshold_col] = row_threshold
            threshold_columns.append(threshold_col)
            evaluated_columns.append(col)

            mask = mask | (values > row_threshold)

        return mask.fillna(False), {
            "applied": True,
            "evaluated_columns": evaluated_columns,
            "missing_columns": missing_cols,
            "group_by": group_by,
            "group_by_missing": group_by_missing,
            "percentile": percentile,
            "min_group_size": min_group_size,
            "fallback_threshold": fallback_threshold_float,
            "threshold_columns": threshold_columns,
        }

    cols = _rule_columns(rule)
    existing_cols = [col for col in cols if col in df.columns]
    missing_cols = [col for col in cols if col not in df.columns]
    if not existing_cols:
        return _false_series(df.index), {
            "applied": False,
            "skip_reason": "all referenced columns are missing",
            "missing_columns": missing_cols,
        }

    threshold = float(rule["threshold"]) if rule.get("threshold") is not None else None
    mask = _false_series(df.index)
    if rule_type == "threshold_upper":
        for col in existing_cols:
            mask = mask | (df[col] > threshold)
    elif rule_type == "threshold_lower":
        for col in existing_cols:
            mask = mask | (df[col] < threshold)
    elif rule_type == "threshold_abs":
        for col in existing_cols:
            mask = mask | (df[col].abs() > threshold)
    elif rule_type == "missing_any":
        for col in existing_cols:
            mask = mask | df[col].isna()
    else:
        raise ValueError(f"Unsupported rule type '{rule_type}' for rule '{code}'")

    return mask.fillna(False), {
        "applied": True,
        "evaluated_columns": existing_cols,
        "missing_columns": missing_cols,
        "threshold": threshold,
    }


def _build_issue_series(
    index: pd.Index,
    rule_masks: dict[str, pd.Series],
    codes: list[str],
) -> tuple[pd.Series, pd.Series]:
    if not codes:
        empty_codes = pd.Series([""] * len(index), index=index, dtype=object)
        empty_counts = pd.Series([0] * len(index), index=index, dtype=int)
        return empty_codes, empty_counts

    matrix = np.column_stack([rule_masks[code].to_numpy(dtype=bool) for code in codes])
    issue_codes = [
        "|".join([codes[i] for i, hit in enumerate(row) if hit])
        for row in matrix
    ]
    issue_counts = matrix.sum(axis=1).astype(int)
    return pd.Series(issue_codes, index=index, dtype=object), pd.Series(issue_counts, index=index, dtype=int)


def clean_table(
    df: pd.DataFrame,
    *,
    table_name: str,
    rules_config: dict[str, Any],
    as_of_ref: pd.Timestamp,
    filter_mode: str,
    refresh_cfg: dict[str, Any] | None = None,
    source_latest: pd.DataFrame | None = None,
    monitor_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    out = df.copy()

    refresh_summary: dict[str, Any] = {"enabled": False, "applied": False}
    if refresh_cfg:
        out, refresh_summary = refresh_stale_rows(
            out,
            table_name=table_name,
            refresh_cfg=refresh_cfg,
            source_latest=source_latest,
            as_of_ref=as_of_ref,
        )

    if rules_config.get("normalization", {}).get("sector", True) and "sector" in out.columns:
        out["sector"] = out["sector"].apply(normalize_sector)

    rule_columns: set[str] = set()
    for rule in rules_config["rules"]:
        if rule["type"] in {"threshold_upper", "threshold_lower", "threshold_abs", "group_percentile_upper", "group_percentile_abs"}:
            rule_columns.update(_rule_columns(rule))
    numeric_columns = set(str(c) for c in rules_config.get("numeric_columns", []))
    candidate_numeric = [col for col in (numeric_columns | rule_columns) if col in out.columns]
    for col in candidate_numeric:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    numeric_cols = list(out.select_dtypes(include=[np.number]).columns)
    if numeric_cols:
        inf_any_numeric_mask = np.isinf(out[numeric_cols]).any(axis=1)
        out[numeric_cols] = out[numeric_cols].replace([np.inf, -np.inf], np.nan)
    else:
        inf_any_numeric_mask = _false_series(out.index)

    rule_masks: dict[str, pd.Series] = {}
    rule_meta: dict[str, dict[str, Any]] = {}
    for rule in rules_config["rules"]:
        code = rule["code"]
        mask, meta = _evaluate_rule(
            out,
            rule,
            as_of_ref=as_of_ref,
            inf_any_numeric_mask=inf_any_numeric_mask,
        )
        mask = mask.fillna(False).astype(bool)
        out[f"flag_{_slugify(code)}"] = mask
        rule_masks[code] = mask
        rule_meta[code] = meta

    hard_codes = [rule["code"] for rule in rules_config["rules"] if rule["category"] == "hard_fail"]
    warning_codes = [rule["code"] for rule in rules_config["rules"] if rule["category"] == "warning"]

    has_hard_fail = _false_series(out.index)
    for code in hard_codes:
        has_hard_fail = has_hard_fail | rule_masks[code]
    has_warning = _false_series(out.index)
    for code in warning_codes:
        has_warning = has_warning | rule_masks[code]
    has_any_issue = has_hard_fail | has_warning

    hard_codes_series, hard_count_series = _build_issue_series(out.index, rule_masks, hard_codes)
    warning_codes_series, warning_count_series = _build_issue_series(out.index, rule_masks, warning_codes)
    all_codes_order = [rule["code"] for rule in rules_config["rules"]]
    all_codes_series, all_count_series = _build_issue_series(out.index, rule_masks, all_codes_order)

    out["issue_codes_hard_fail"] = hard_codes_series
    out["issue_codes_warning"] = warning_codes_series
    out["issue_codes_all"] = all_codes_series
    out["issue_count_hard_fail"] = hard_count_series
    out["issue_count_warning"] = warning_count_series
    out["issue_count_all"] = all_count_series
    out["flag_has_hard_fail"] = has_hard_fail
    out["flag_has_warning"] = has_warning
    out["flag_any_issue"] = has_any_issue
    out["row_action"] = np.where(has_hard_fail, "DROP", np.where(has_warning, "WATCH", "KEEP"))

    if filter_mode == "all_issues":
        filtered = out.loc[~has_any_issue].copy()
    else:
        filtered = out.loc[~has_hard_fail].copy()

    rule_stats: dict[str, Any] = {}
    for rule in rules_config["rules"]:
        code = rule["code"]
        mask = rule_masks[code]
        meta = rule_meta[code]
        entry = {
            "category": rule["category"],
            "type": rule["type"],
            "trigger_count": int(mask.sum()),
            "trigger_pct": round((float(mask.mean()) * 100.0) if len(mask) else 0.0, 2),
            "applied": bool(meta.get("applied", True)),
        }
        if rule.get("threshold") is not None:
            entry["threshold"] = float(rule["threshold"])
        if rule.get("column") is not None:
            entry["column"] = rule["column"]
        if rule.get("columns") is not None:
            entry["columns"] = rule["columns"]
        if meta.get("evaluated_columns") is not None:
            entry["evaluated_columns"] = meta["evaluated_columns"]
        if meta.get("missing_columns") is not None:
            entry["missing_columns"] = meta["missing_columns"]
        if meta.get("age_output_column") is not None:
            entry["age_output_column"] = meta["age_output_column"]
        if meta.get("group_by") is not None:
            entry["group_by"] = meta["group_by"]
        if meta.get("group_by_missing") is not None:
            entry["group_by_missing"] = meta["group_by_missing"]
        if meta.get("percentile") is not None:
            entry["percentile"] = meta["percentile"]
        if meta.get("min_group_size") is not None:
            entry["min_group_size"] = meta["min_group_size"]
        if meta.get("fallback_threshold") is not None:
            entry["fallback_threshold"] = meta["fallback_threshold"]
        if meta.get("threshold_columns") is not None:
            entry["threshold_columns"] = meta["threshold_columns"]
        if meta.get("skip_reason") is not None:
            entry["skip_reason"] = meta["skip_reason"]
        rule_stats[code] = entry

    summary = {
        "rows_input": int(len(df)),
        "rows_cleaned": int(len(out)),
        "rows_filtered": int(len(filtered)),
        "removed_rows": int(len(out) - len(filtered)),
        "filter_mode": filter_mode,
        "refresh": refresh_summary,
        "null_profile": build_null_profile(out, monitor_columns),
        "row_state_counts": {
            "rows_with_hard_fail": int(has_hard_fail.sum()),
            "rows_with_warning": int(has_warning.sum()),
            "rows_with_warning_only": int((has_warning & ~has_hard_fail).sum()),
            "rows_with_any_issue": int(has_any_issue.sum()),
            "rows_without_issue": int((~has_any_issue).sum()),
        },
        "rules": rule_stats,
    }
    return out, filtered, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build cleaned datasets from stocks.db using a deterministic, YAML-driven "
            "rule pipeline. Produces explainable issue codes and per-rule stats."
        )
    )
    parser.add_argument("--db-path", default="stocks.db")
    parser.add_argument("--out-dir", default="reports/cleaned")
    parser.add_argument("--rules-path", default="ops/cleaning_rules.yaml")
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Reference date in YYYY-MM-DD. Overrides config; defaults to local current date.",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        default=None,
        help="Optional table override. Defaults to tables from rules config.",
    )
    parser.add_argument(
        "--filter-mode",
        choices=sorted(FILTER_MODES),
        default=None,
        help="Override filter mode from config.",
    )
    parser.add_argument(
        "--baseline-summary",
        default=None,
        help="Optional baseline cleaning_summary.json path for drift/null-spike alerts.",
    )
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="Write cleaned and gold datasets back to SQLite tables and persist telemetry tables.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run identifier for telemetry persistence.",
    )
    args = parser.parse_args()

    rules_path = Path(args.rules_path)
    rules_config = load_rules_config(rules_path)
    baseline_summary = load_summary_file(args.baseline_summary)
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_ts_utc = datetime.now(timezone.utc).isoformat()
    as_of_ref = (
        pd.Timestamp(args.as_of_date)
        if args.as_of_date
        else pd.Timestamp(rules_config["as_of_date"]) if rules_config.get("as_of_date")
        else pd.Timestamp(date.today())
    )
    tables = args.tables or rules_config["tables"]
    filter_mode = args.filter_mode or rules_config["filter_mode"]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "config": {
            "db_path": args.db_path,
            "rules_path": str(rules_path),
            "out_dir": str(out_dir),
            "as_of_date": as_of_ref.strftime("%Y-%m-%d"),
            "tables": tables,
            "filter_mode": filter_mode,
            "refresh": rules_config.get("refresh", {}),
            "monitor": rules_config.get("monitor", {}),
            "baseline_summary": args.baseline_summary,
            "run_id": run_id,
            "write_db": bool(args.write_db),
        },
        "tables": {},
    }

    with sqlite3.connect(args.db_path) as conn:
        refresh_cfg = rules_config.get("refresh", {})
        source_latest: pd.DataFrame | None = None
        if refresh_cfg.get("enabled", False):
            source_table = str(refresh_cfg.get("source_table", "fundamentals_pit"))
            source_df = load_table(conn, source_table)
            source_latest = build_latest_source_snapshot(
                source_df,
                key_column=str(refresh_cfg.get("source_key_column", "symbol")),
                date_column=str(refresh_cfg.get("source_date_column", "as_of_date")),
            )

        for table_name in tables:
            df = load_table(conn, table_name)
            cleaned, filtered, table_summary = clean_table(
                df,
                table_name=table_name,
                rules_config=rules_config,
                as_of_ref=as_of_ref,
                filter_mode=filter_mode,
                refresh_cfg=refresh_cfg,
                source_latest=source_latest,
                monitor_columns=rules_config.get("monitor", {}).get("critical_columns", {}).get(table_name, []),
            )

            cleaned_path = out_dir / f"{table_name}_cleaned.csv"
            filtered_path = out_dir / f"{table_name}_cleaned_filtered.csv"
            cleaned.to_csv(cleaned_path, index=False)
            filtered.to_csv(filtered_path, index=False)

            table_summary["output_files"] = {
                "cleaned": str(cleaned_path),
                "filtered": str(filtered_path),
            }
            if args.write_db:
                cleaned_table_name = f"{table_name}_cleaned"
                gold_table_name = f"{table_name}_gold"
                cleaned.to_sql(cleaned_table_name, conn, if_exists="replace", index=False)
                filtered.to_sql(gold_table_name, conn, if_exists="replace", index=False)
                table_summary["db_tables"] = {
                    "cleaned": cleaned_table_name,
                    "gold": gold_table_name,
                }
            summary["tables"][table_name] = table_summary

        alerts = build_alerts(
            summary,
            monitor_cfg=rules_config.get("monitor", {}),
            baseline_summary=baseline_summary,
        )
        severity_counts: dict[str, int] = {}
        for alert in alerts:
            sev = str(alert.get("severity", "unknown"))
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        summary["alerts"] = {
            "count": len(alerts),
            "by_severity": severity_counts,
        }
        if args.write_db:
            persist_quality_telemetry(
                conn,
                run_id=run_id,
                run_ts_utc=run_ts_utc,
                as_of_date=as_of_ref.strftime("%Y-%m-%d"),
                summary=summary,
                alerts=alerts,
            )

    summary_path = out_dir / "cleaning_summary.json"
    alerts_path = out_dir / "cleaning_alerts.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    with alerts_path.open("w", encoding="utf-8") as fh:
        json.dump(alerts, fh, indent=2)

    print(f"Cleaned datasets written to: {out_dir}")
    print(f"Summary written to: {summary_path}")
    print(f"Alerts written to: {alerts_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
