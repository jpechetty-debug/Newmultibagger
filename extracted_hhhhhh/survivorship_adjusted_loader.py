"""
backtest/survivorship_adjusted_loader.py
─────────────────────────────────────────
DROP-IN REPLACEMENT for the stub that returned True for every symbol.

How it works
────────────
Priority 1 — Historical index snapshots (gold standard)
    If  data/nifty500_YYYY-MM.csv  exists for the target month, use it.
    NSE publishes monthly Nifty 500 composition on their website.
    Expected columns: Symbol (e.g. "RELIANCE") — anything extra is ignored.

Priority 2 — Master metadata CSV (listing/delisting dates)
    If  data/nse_listing_dates.csv  exists, filter by:
        Listing_Date  <= as_of_date
        Delisting_Date > as_of_date  (or blank/NaT — still active)
    Expected columns: Symbol, Listing_Date, Delisting_Date (blank = still listed)

Priority 3 — Graceful degradation
    If neither source exists, falls back to the original behaviour (return all)
    but emits a WARNING so the user knows backtest results may be inflated.

Data source for nse_listing_dates.csv
──────────────────────────────────────
NSE publishes the full list of listed and delisted stocks.
Download from: https://www.nseindia.com/market-data/securities-available-for-trading
Save as:  data/nse_listing_dates.csv
Columns required:
    Symbol          NSE ticker (e.g. RELIANCE, TCS)
    Listing_Date    YYYY-MM-DD or DD-MMM-YYYY
    Delisting_Date  YYYY-MM-DD or blank if still active
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_DATE_FORMATS = ["%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%Y%m%d"]


def _parse_date(value: str | None) -> Optional[pd.Timestamp]:
    """Try multiple date formats; return None if unparseable or blank."""
    if not value or str(value).strip().lower() in {"", "nan", "nat", "none", "null"}:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return pd.Timestamp(datetime.strptime(str(value).strip(), fmt))
        except ValueError:
            continue
    logger.debug("Could not parse date value: %r", value)
    return None


class SurvivorshipAdjustedLoader:
    """
    Loads a point-in-time universe of NSE stocks, filtering out:
      - Stocks not yet listed at `as_of_date`
      - Stocks already delisted by `as_of_date`

    Falls back gracefully when no metadata is available, but warns the user
    so they know backtest CAGR figures may be overstated.
    """

    def __init__(self, data_dir: str = "data") -> None:
        self.data_dir = Path(data_dir)
        self._listing_cache: Optional[pd.DataFrame] = None
        self._cache_path: Optional[Path] = None

    # ── public API ─────────────────────────────────────────────────────────

    def get_universe(
        self,
        as_of_date: str,
        candidates: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Return the valid universe of stocks for a specific historical date.

        Args:
            as_of_date:  ISO date string "YYYY-MM-DD"
            candidates:  Optional list of symbols to filter. If None, the full
                         metadata CSV is used as the candidate pool.

        Returns:
            List of NSE ticker strings valid at `as_of_date`.
        """
        target = pd.Timestamp(as_of_date)

        # ── Priority 1: historical index snapshot ──────────────────────────
        snapshot = self._load_index_snapshot(as_of_date)
        if snapshot is not None:
            logger.info(
                "[SurvivorshipLoader] Using index snapshot for %s — %d stocks",
                as_of_date, len(snapshot),
            )
            if candidates:
                snapshot = [s for s in snapshot if s in set(candidates)]
            return snapshot

        # ── Priority 2: listing-date metadata CSV ──────────────────────────
        listing_df = self._load_listing_metadata()
        if listing_df is not None:
            valid = self._filter_by_dates(listing_df, target, candidates)
            logger.info(
                "[SurvivorshipLoader] Date-filtered universe for %s — %d stocks (from %d candidates)",
                as_of_date, len(valid), len(candidates) if candidates else len(listing_df),
            )
            return valid

        # ── Priority 3: degraded fallback ──────────────────────────────────
        logger.warning(
            "[SurvivorshipLoader] No listing metadata found at '%s'. "
            "Returning all candidates unfiltered — backtest results MAY BE OVERSTATED. "
            "To fix: add data/nse_listing_dates.csv or data/nifty500_YYYY-MM.csv files.",
            self.data_dir,
        )
        return list(candidates) if candidates else []

    def load_delisted_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Load OHLCV history for a delisted stock from data/delisted/.
        Returns a DataFrame if the file exists, otherwise None.
        """
        delisted_dir = self.data_dir / "delisted"
        for ext in (".csv", ".parquet"):
            path = delisted_dir / f"{symbol}{ext}"
            if path.exists():
                try:
                    df = pd.read_csv(path) if ext == ".csv" else pd.read_parquet(path)
                    logger.debug("Loaded delisted data for %s from %s", symbol, path)
                    return df
                except Exception as exc:
                    logger.warning("Failed to load delisted data for %s: %s", symbol, exc)
        return None

    def get_delisted_symbols(self, as_of_date: str) -> List[str]:
        """Return symbols that were delisted on or before `as_of_date`."""
        listing_df = self._load_listing_metadata()
        if listing_df is None:
            return []
        target = pd.Timestamp(as_of_date)
        mask = listing_df["Delisting_Date"].notna() & (listing_df["Delisting_Date"] <= target)
        return listing_df.loc[mask, "Symbol"].tolist()

    # ── internal ────────────────────────────────────────────────────────────

    def _load_index_snapshot(self, as_of_date: str) -> Optional[List[str]]:
        """Try to load a saved monthly Nifty 500 composition CSV."""
        month_str = as_of_date[:7]  # "YYYY-MM"
        path = self.data_dir / f"nifty500_{month_str}.csv"
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path)
            if "Symbol" not in df.columns:
                logger.warning(
                    "Index snapshot %s has no 'Symbol' column — columns: %s",
                    path, list(df.columns),
                )
                return None
            symbols = df["Symbol"].dropna().str.strip().str.upper().tolist()
            logger.debug("Snapshot %s loaded — %d symbols", path, len(symbols))
            return symbols
        except Exception as exc:
            logger.warning("Failed to read index snapshot %s: %s", path, exc)
            return None

    def _load_listing_metadata(self) -> Optional[pd.DataFrame]:
        """Load (and cache) data/nse_listing_dates.csv."""
        path = self.data_dir / "nse_listing_dates.csv"
        if self._listing_cache is not None and self._cache_path == path:
            return self._listing_cache
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path)
            required = {"Symbol", "Listing_Date"}
            missing = required - set(df.columns)
            if missing:
                logger.error(
                    "nse_listing_dates.csv is missing required columns: %s", missing
                )
                return None

            df["Symbol"] = df["Symbol"].str.strip().str.upper()
            df["Listing_Date"] = df["Listing_Date"].apply(
                lambda v: _parse_date(str(v)) if pd.notna(v) else None
            )
            if "Delisting_Date" in df.columns:
                df["Delisting_Date"] = df["Delisting_Date"].apply(
                    lambda v: _parse_date(str(v)) if pd.notna(v) else None
                )
            else:
                df["Delisting_Date"] = None

            df = df.dropna(subset=["Listing_Date"])
            self._listing_cache = df
            self._cache_path = path
            logger.info("Loaded listing metadata: %d records from %s", len(df), path)
            return df
        except Exception as exc:
            logger.error("Failed to load nse_listing_dates.csv: %s", exc)
            return None

    def _filter_by_dates(
        self,
        listing_df: pd.DataFrame,
        target: pd.Timestamp,
        candidates: Optional[List[str]],
    ) -> List[str]:
        """
        Return symbols that were listed and not yet delisted at `target`.
        If `candidates` is provided, restrict to that set.
        """
        mask_listed = listing_df["Listing_Date"] <= target
        mask_not_delisted = (
            listing_df["Delisting_Date"].isna()
            | (listing_df["Delisting_Date"] > target)
        )
        valid_df = listing_df[mask_listed & mask_not_delisted]

        if candidates:
            candidate_set = {s.strip().upper() for s in candidates}
            valid_df = valid_df[valid_df["Symbol"].isin(candidate_set)]

        return valid_df["Symbol"].tolist()

    # ── convenience: data setup helper ─────────────────────────────────────

    @staticmethod
    def create_sample_metadata(output_path: str = "data/nse_listing_dates.csv") -> None:
        """
        Create a minimal sample nse_listing_dates.csv with Nifty 50 blue chips.
        Useful for getting started; replace with real NSE data for production.
        """
        import csv

        sample = [
            ("RELIANCE", "1977-07-08", ""),
            ("TCS", "2004-08-25", ""),
            ("INFY", "1993-02-08", ""),
            ("HDFCBANK", "1995-05-19", ""),
            ("ICICIBANK", "1997-09-17", ""),
            ("HINDUNILVR", "1958-11-20", ""),
            ("BHARTIARTL", "2002-02-18", ""),
            ("KOTAKBANK", "1995-12-20", ""),
            ("ITC", "1975-08-27", ""),
            ("LT", "1950-01-01", ""),
            # Delisted example — DO NOT include in any future universe
            ("RCOM", "2004-03-01", "2020-06-01"),
        ]

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Symbol", "Listing_Date", "Delisting_Date"])
            writer.writerows(sample)
        print(f"Sample metadata written to {output}")


# ── CLI: quick validation ────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    loader = SurvivorshipAdjustedLoader(data_dir="data")

    test_date = "2020-03-01"
    candidates = ["RELIANCE", "TCS", "RCOM", "INFY", "HDFCBANK"]

    print(f"\nUniverse at {test_date} (from {len(candidates)} candidates):")
    universe = loader.get_universe(test_date, candidates)
    print(f"  Valid: {universe}")

    delisted = loader.get_delisted_symbols(test_date)
    print(f"  Delisted by {test_date}: {delisted}")
