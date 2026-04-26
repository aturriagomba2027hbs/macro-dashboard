"""
Macro Data Pipeline
====================
Downloads daily closing prices for key market tickers via yfinance and
pulls Treasury / TIPS yields from the FRED API. Merges all series into
a single forward-filled DataFrame and exports to macro_data.csv.
"""

import os
import warnings
from datetime import date

import pandas as pd
import requests
import yfinance as yf
from fredapi import Fred

warnings.filterwarnings("ignore")

# ── Configuration ──────────────────────────────────────────────────────────────
START_DATE = "2000-01-01"
END_DATE   = date.today().isoformat()

# yfinance tickers  →  output column names
YFINANCE_MAP = {
    "^GSPC":    "spx",
    "CL=F":     "oil",
    "GC=F":     "gold",
    "DX-Y.NYB": "dxy",
    "^VIX":     "vix",
    "EEM":      "em_eq",
    "HYG":      "hyg",
    "TLT":      "tlt",
}

# FRED series IDs  →  output column names
FRED_MAP = {
    "DGS10":  "yield_10y",
    "DGS2":   "yield_2y",
    "DFII10": "real_yield_10y",
}

# Accept key from env; empty string → fall back to unauthenticated public endpoint
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
OUTPUT_FILE  = "macro_data.csv"

# ── Step 1 : Download yfinance data ────────────────────────────────────────────
print("=" * 60)
print("STEP 1 — Downloading market data via yfinance …")
print("=" * 60)

tickers = list(YFINANCE_MAP.keys())
raw = yf.download(
    tickers,
    start=START_DATE,
    end=END_DATE,
    auto_adjust=True,
    progress=True,
    threads=True,
)

# Extract adjusted close prices; handle both single and multi-ticker responses
if isinstance(raw.columns, pd.MultiIndex):
    close = raw["Close"].copy()
else:
    close = raw[["Close"]].copy()
    close.columns = [tickers[0]]

close.index = pd.to_datetime(close.index)
close.index.name = "date"

# Rename columns to friendly names
close.rename(columns=YFINANCE_MAP, inplace=True)
# Keep only the mapped columns (drop any extras)
close = close[[c for c in YFINANCE_MAP.values() if c in close.columns]]

print(f"\nyfinance raw shape : {close.shape}")
print(f"Date range         : {close.index.min().date()} → {close.index.max().date()}\n")

# ── Step 2 : Download FRED data ────────────────────────────────────────────────
print("=" * 60)
print("STEP 2 — Downloading yield data from FRED …")
print("=" * 60)

def fetch_fred_series(series_id: str, start: str, end: str, api_key: str) -> pd.Series:
    """Fetch a FRED series, using fredapi when a key is provided,
    otherwise falling back to the public FRED JSON REST endpoint."""
    if api_key:
        fred = Fred(api_key=api_key)
        s = fred.get_series(series_id, observation_start=start, observation_end=end)
        s.index = pd.to_datetime(s.index)
        return s
    # Public REST endpoint — no key required
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&vintage_date={end}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    from io import StringIO
    df = pd.read_csv(
        StringIO(resp.text),
        parse_dates=["observation_date"],
        index_col="observation_date",
    )
    df.index.name = "date"
    s = df.iloc[:, 0]  # value column is named after the series_id
    s = pd.to_numeric(s, errors="coerce")  # FRED uses "." for missing → NaN
    s = s.loc[start:end]
    return s

fred_frames = []

for series_id, col_name in FRED_MAP.items():
    print(f"  Fetching {series_id} → {col_name} …", end=" ")
    s = fetch_fred_series(series_id, START_DATE, END_DATE, FRED_API_KEY)
    s.name = col_name
    fred_frames.append(s)
    print(f"OK  ({len(s)} observations)")

fred_df = pd.concat(fred_frames, axis=1)
print(f"\nFRED raw shape     : {fred_df.shape}")
print(f"Date range         : {fred_df.index.min().date()} → {fred_df.index.max().date()}\n")

# ── Step 3 : Merge & forward-fill ──────────────────────────────────────────────
print("=" * 60)
print("STEP 3 — Merging and forward-filling …")
print("=" * 60)

# Build a continuous calendar-day index spanning both sources
full_idx = pd.date_range(
    start=min(close.index.min(), fred_df.index.min()),
    end=max(close.index.max(), fred_df.index.max()),
    freq="D",
    name="date",
)

merged = (
    close
    .reindex(full_idx)
    .join(fred_df.reindex(full_idx), how="outer")
    .sort_index()
    .ffill()          # forward-fill weekends / holidays / missing FRED days
)

# Enforce canonical column order
COLUMNS = ["spx", "oil", "gold", "dxy", "vix", "em_eq", "hyg", "tlt",
           "yield_10y", "yield_2y", "real_yield_10y"]
merged = merged[COLUMNS]

print(f"Merged shape       : {merged.shape}\n")

# ── Step 4 : Export ────────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 4 — Exporting to macro_data.csv …")
print("=" * 60)

merged.index.name = "date"
merged.to_csv(OUTPUT_FILE)
print(f"Saved → {OUTPUT_FILE}  ({os.path.getsize(OUTPUT_FILE) / 1_048_576:.2f} MB)\n")

# ── Step 5 : Summary ───────────────────────────────────────────────────────────
print("=" * 60)
print("SUMMARY")
print("=" * 60)

print(f"  Date range  : {merged.index.min().date()} → {merged.index.max().date()}")
print(f"  Total rows  : {len(merged):,}")
print(f"  Columns     : {len(merged.columns)}")
print()
print("  Null counts per column:")
print("  " + "-" * 30)
null_counts = merged.isnull().sum()
for col, n in null_counts.items():
    pct = n / len(merged) * 100
    flag = "  ← check" if n > 0 else ""
    print(f"  {col:<20} {n:>6,}  ({pct:5.2f}%){flag}")

print()
print("  Sample (last 5 rows):")
print(merged.tail(5).to_string())
print()
print("Pipeline complete.")
