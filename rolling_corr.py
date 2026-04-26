"""
Rolling Correlation & Regime Shift Detector
============================================
Reads macro_data.csv, computes 30/60/90-day rolling Pearson correlations
for six asset pairs, flags regime shifts, and exports:
  - correlation_history.json  (full time-series, one record per date per pair)
  - latest_snapshot.json      (most-recent row for all six pairs)
"""

import json
import warnings
from datetime import date

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Config ─────────────────────────────────────────────────────────────────────
INPUT_FILE       = "macro_data.csv"
HISTORY_FILE     = "correlation_history.json"
SNAPSHOT_FILE    = "latest_snapshot.json"
REGIME_THRESHOLD = 0.25          # |corr_30d - corr_90d| > threshold → flag
WINDOWS          = [30, 60, 90]  # rolling window sizes (calendar days)

# Six pairs: (col_a, col_b, display_name)
# The yield spread is a derived series, handled specially.
PAIRS = [
    ("oil",           "spx",           "oil_vs_spx"),
    ("gold",          "real_yield_10y","gold_vs_real_yield_10y"),
    ("dxy",           "em_eq",         "dxy_vs_em_eq"),
    ("vix",           "hyg",           "vix_vs_hyg"),
    ("yield_spread",  "spx",           "yield_spread_vs_spx"),
    ("oil",           "dxy",           "oil_vs_dxy"),
]

# ── Load & prepare data ────────────────────────────────────────────────────────
print("=" * 65)
print("Loading macro_data.csv …")
print("=" * 65)

df = pd.read_csv(INPUT_FILE, parse_dates=["date"], index_col="date")
df.sort_index(inplace=True)

# Derive yield spread (10y − 2y)
df["yield_spread"] = df["yield_10y"] - df["yield_2y"]

print(f"  Rows loaded      : {len(df):,}")
print(f"  Date range       : {df.index.min().date()} → {df.index.max().date()}")
print(f"  Derived columns  : yield_spread\n")

# ── Rolling correlation helper ─────────────────────────────────────────────────
def rolling_corr(series_a: pd.Series, series_b: pd.Series, window: int) -> pd.Series:
    """
    Compute rolling Pearson correlation using a calendar-day window.
    Both series must share the same DatetimeIndex.
    min_periods = window // 2  to allow partial windows at series inception.
    """
    return series_a.rolling(window=window, min_periods=window // 2).corr(series_b)

# ── Compute correlations for all pairs ────────────────────────────────────────
print("=" * 65)
print("Computing rolling correlations …")
print("=" * 65)

records = []   # will hold one dict per (date, pair)

for col_a, col_b, pair_name in PAIRS:
    s_a = df[col_a].copy()
    s_b = df[col_b].copy()

    corr_30 = rolling_corr(s_a, s_b, 30)
    corr_60 = rolling_corr(s_a, s_b, 60)
    corr_90 = rolling_corr(s_a, s_b, 90)

    # Regime shift flag: |30d − 90d| > threshold
    regime_flag = (corr_30 - corr_90).abs() > REGIME_THRESHOLD

    # Count flags for reporting
    n_flags = int(regime_flag.sum())
    print(f"  {pair_name:<35}  regime-shift days: {n_flags:,}")

    # Build per-row records
    pair_df = pd.DataFrame({
        "date":              corr_30.index.strftime("%Y-%m-%d"),
        "pair_name":         pair_name,
        "corr_30d":          corr_30.round(6),
        "corr_60d":          corr_60.round(6),
        "corr_90d":          corr_90.round(6),
        "regime_shift_flag": regime_flag,
    })

    # Drop rows where all three correlations are NaN (pre-inception)
    pair_df.dropna(subset=["corr_30d", "corr_60d", "corr_90d"], how="all", inplace=True)

    records.append(pair_df)

print()

# ── Build full history DataFrame ───────────────────────────────────────────────
history_df = pd.concat(records, ignore_index=True)

# Convert NaN → None for clean JSON serialisation
history_df["corr_30d"] = history_df["corr_30d"].where(history_df["corr_30d"].notna(), other=None)
history_df["corr_60d"] = history_df["corr_60d"].where(history_df["corr_60d"].notna(), other=None)
history_df["corr_90d"] = history_df["corr_90d"].where(history_df["corr_90d"].notna(), other=None)
history_df["regime_shift_flag"] = history_df["regime_shift_flag"].astype(bool)

print(f"  Total history records : {len(history_df):,}")
print(f"  Unique pairs          : {history_df['pair_name'].nunique()}")
print()

# ── Export correlation_history.json ───────────────────────────────────────────
print("=" * 65)
print(f"Exporting {HISTORY_FILE} …")
print("=" * 65)

history_records = history_df.to_dict(orient="records")
class _NaNSafeEncoder(json.JSONEncoder):
    """Serialise Python float NaN / Inf as JSON null."""
    def iterencode(self, o, _one_shot=False):
        # Patch the C-level encoder to avoid bare NaN tokens
        return super().iterencode(o, _one_shot)

    def default(self, obj):
        return str(obj)

def _nan_to_null(obj):
    """Recursively replace float NaN with None before serialisation."""
    if isinstance(obj, list):
        return [_nan_to_null(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _nan_to_null(v) for k, v in obj.items()}
    if isinstance(obj, float) and (obj != obj):  # NaN check
        return None
    return obj

with open(HISTORY_FILE, "w") as f:
    json.dump(_nan_to_null(history_records), f, indent=2, default=str)

import os
size_mb = os.path.getsize(HISTORY_FILE) / 1_048_576
print(f"  Saved {HISTORY_FILE}  ({size_mb:.2f} MB, {len(history_records):,} records)\n")

# ── Build latest_snapshot.json ────────────────────────────────────────────────
print("=" * 65)
print(f"Building {SNAPSHOT_FILE} …")
print("=" * 65)

# Latest date that has at least one non-null correlation
latest_date = history_df.dropna(subset=["corr_30d"])["date"].max()
snapshot_rows = history_df[history_df["date"] == latest_date].copy()

snapshot = {
    "snapshot_date": latest_date,
    "generated_at":  date.today().isoformat(),
    "pairs": []
}

for _, row in snapshot_rows.iterrows():
    snapshot["pairs"].append({
        "pair_name":         row["pair_name"],
        "corr_30d":          row["corr_30d"],
        "corr_60d":          row["corr_60d"],
        "corr_90d":          row["corr_90d"],
        "regime_shift_flag": bool(row["regime_shift_flag"]),
    })

with open(SNAPSHOT_FILE, "w") as f:
    json.dump(snapshot, f, indent=2, default=str)

print(f"  Saved {SNAPSHOT_FILE}")
print(f"  Snapshot date : {latest_date}\n")

# ── Console output: last 5 rows per pair ──────────────────────────────────────
print("=" * 65)
print("LAST 5 ROWS PER PAIR")
print("=" * 65)

for pair_name in [p[2] for p in PAIRS]:
    subset = history_df[history_df["pair_name"] == pair_name].tail(5)
    print(f"\n  Pair: {pair_name}")
    print("  " + "-" * 61)
    header = f"  {'date':<12} {'corr_30d':>10} {'corr_60d':>10} {'corr_90d':>10}  {'regime_shift':>12}"
    print(header)
    print("  " + "-" * 61)
    for _, r in subset.iterrows():
        c30  = f"{r['corr_30d']:>10.4f}" if r["corr_30d"] is not None else f"{'N/A':>10}"
        c60  = f"{r['corr_60d']:>10.4f}" if r["corr_60d"] is not None else f"{'N/A':>10}"
        c90  = f"{r['corr_90d']:>10.4f}" if r["corr_90d"] is not None else f"{'N/A':>10}"
        flag = "  *** TRUE ***" if r["regime_shift_flag"] else "      false"
        print(f"  {r['date']:<12} {c30} {c60} {c90} {flag}")

# ── Latest snapshot pretty-print ──────────────────────────────────────────────
print()
print("=" * 65)
print(f"LATEST SNAPSHOT  ({snapshot['snapshot_date']})")
print("=" * 65)
print(f"  {'Pair':<35} {'30d':>7} {'60d':>7} {'90d':>7}  {'Regime Shift':>12}")
print("  " + "-" * 65)
for p in snapshot["pairs"]:
    c30  = f"{p['corr_30d']:>7.4f}" if p["corr_30d"] is not None else f"{'N/A':>7}"
    c60  = f"{p['corr_60d']:>7.4f}" if p["corr_60d"] is not None else f"{'N/A':>7}"
    c90  = f"{p['corr_90d']:>7.4f}" if p["corr_90d"] is not None else f"{'N/A':>7}"
    flag = "*** TRUE ***" if p["regime_shift_flag"] else "false"
    print(f"  {p['pair_name']:<35} {c30} {c60} {c90}  {flag:>12}")

print()
print("Done.")
