"""
build_api_response.py
Constructs api_response.json — the backend payload for the React dashboard.
Sources:
  - latest_snapshot.json       → current_snapshot section
  - correlation_history.json   → correlation_history section (last 90 calendar days per pair)
  - morning_briefing.json      → regime_alerts section
  - macro_regimes_kb.json      → historical_analogs detail per flagged pair

All file paths are resolved relative to this script's location so the script
works identically on a local machine, in GitHub Actions, or any other environment.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

# ── Resolve all paths relative to this script ────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _path(filename):
    return os.path.join(SCRIPT_DIR, filename)

# ── Load source files ─────────────────────────────────────────────────────────
with open(_path('latest_snapshot.json')) as f:
    snapshot_raw = json.load(f)

with open(_path('correlation_history.json')) as f:
    history_raw = json.load(f)

with open(_path('morning_briefing.json')) as f:
    briefing_raw = json.load(f)

with open(_path('macro_regimes_kb.json')) as f:
    kb_raw = json.load(f)

# ── Helpers ───────────────────────────────────────────────────────────────────
PAIR_META = {
    "oil_vs_spx": {
        "label": "Oil vs S&P 500",
        "asset_a": "WTI Crude Oil (CL=F)",
        "asset_b": "S&P 500 (^GSPC)",
        "description": "Measures the relationship between energy prices and broad US equity performance."
    },
    "gold_vs_real_yield_10y": {
        "label": "Gold vs Real Yield (10Y)",
        "asset_a": "Gold (GC=F)",
        "asset_b": "10Y TIPS Real Yield (DFII10)",
        "description": "The canonical real-rate vs. gold relationship; negative correlation is the standard regime."
    },
    "dxy_vs_em_eq": {
        "label": "DXY vs EM Equities",
        "asset_a": "US Dollar Index (DX-Y.NYB)",
        "asset_b": "Emerging Market Equities (EEM)",
        "description": "Tracks the inverse relationship between dollar strength and EM equity performance."
    },
    "vix_vs_hyg": {
        "label": "VIX vs High Yield Credit",
        "asset_a": "CBOE Volatility Index (^VIX)",
        "asset_b": "iShares HYG ETF",
        "description": "Risk sentiment barometer: rising VIX typically compresses high-yield bond prices."
    },
    "yield_spread_vs_spx": {
        "label": "Yield Spread (10Y-2Y) vs S&P 500",
        "asset_a": "10Y-2Y Treasury Spread",
        "asset_b": "S&P 500 (^GSPC)",
        "description": "Recession-cycle indicator; inversion of the spread historically precedes equity bear markets."
    },
    "oil_vs_dxy": {
        "label": "Oil vs DXY",
        "asset_a": "WTI Crude Oil (CL=F)",
        "asset_b": "US Dollar Index (DX-Y.NYB)",
        "description": "Oil is priced in USD; a stronger dollar typically suppresses oil prices."
    }
}

KB_DICT = {p['pattern_id']: p for p in kb_raw}

PAIR_TO_PATTERN = {
    "oil_vs_spx":             "oil_spx_negative",
    "gold_vs_real_yield_10y": "gold_real_yield_negative",
    "dxy_vs_em_eq":           "dxy_em_negative",
    "vix_vs_hyg":             None,
    "yield_spread_vs_spx":    "yield_curve_inverted_spx_falling",
    "oil_vs_dxy":             None,
}

def corr_direction_label(corr):
    if corr is None:
        return "N/A"
    if corr >= 0.7:
        return "Strong Positive"
    if corr >= 0.3:
        return "Moderate Positive"
    if corr >= -0.3:
        return "Neutral"
    if corr >= -0.7:
        return "Moderate Negative"
    return "Strong Negative"

def regime_shift_severity(corr_30d, corr_90d):
    if corr_30d is None or corr_90d is None:
        return None
    gap = abs(corr_30d - corr_90d)
    if gap >= 0.5:
        return "high"
    if gap >= 0.35:
        return "medium"
    return "low"

# ── Section 1: meta ───────────────────────────────────────────────────────────
snapshot_date = snapshot_raw['snapshot_date']
generated_at  = snapshot_raw['generated_at']

meta = {
    "api_version":   "1.0.0",
    "endpoint":      "/api/v1/macro-dashboard",
    "snapshot_date": snapshot_date,
    "generated_at":  generated_at,
    "data_sources": [
        {"name": "yfinance", "description": "Market prices: ^GSPC, CL=F, GC=F, DX-Y.NYB, ^VIX, EEM, HYG, TLT"},
        {"name": "FRED",     "description": "Treasury yields: DGS10, DGS2, DFII10"},
    ],
    "pairs_tracked":       6,
    "regime_alerts_count": sum(1 for p in snapshot_raw['pairs'] if p['regime_shift_flag'])
}

# ── Section 2: current_snapshot ──────────────────────────────────────────────
current_snapshot = {"date": snapshot_date, "pairs": []}

for p in snapshot_raw['pairs']:
    name = p['pair_name']
    c30  = p['corr_30d']
    c60  = p['corr_60d']
    c90  = p['corr_90d']
    flag = p['regime_shift_flag']
    gap  = round(abs(c30 - c90), 4) if c30 is not None and c90 is not None else None

    current_snapshot['pairs'].append({
        "pair_id":               name,
        "label":                 PAIR_META[name]['label'],
        "asset_a":               PAIR_META[name]['asset_a'],
        "asset_b":               PAIR_META[name]['asset_b'],
        "description":           PAIR_META[name]['description'],
        "corr_30d":              round(c30, 4) if c30 is not None else None,
        "corr_60d":              round(c60, 4) if c60 is not None else None,
        "corr_90d":              round(c90, 4) if c90 is not None else None,
        "corr_direction":        corr_direction_label(c30),
        "regime_shift_flag":     flag,
        "regime_shift_gap":      gap,
        "regime_shift_severity": regime_shift_severity(c30, c90) if flag else None
    })

# ── Section 3: correlation_history (last 90 calendar days per pair) ───────────
cutoff_date = (datetime.strptime(snapshot_date, "%Y-%m-%d") - timedelta(days=90)).strftime("%Y-%m-%d")

hist_by_pair = defaultdict(list)
for rec in history_raw:
    if rec['date'] >= cutoff_date:
        hist_by_pair[rec['pair_name']].append(rec)

for pair_name in hist_by_pair:
    hist_by_pair[pair_name].sort(key=lambda x: x['date'])

correlation_history = {}
for pair_name, records in hist_by_pair.items():
    correlation_history[pair_name] = {
        "pair_id":    pair_name,
        "label":      PAIR_META[pair_name]['label'],
        "date_range": {
            "from": records[0]['date'] if records else None,
            "to":   records[-1]['date'] if records else None
        },
        "data_points": [
            {
                "date":              r['date'],
                "corr_30d":         r['corr_30d'],
                "corr_60d":         r['corr_60d'],
                "corr_90d":         r['corr_90d'],
                "regime_shift_flag": r['regime_shift_flag']
            }
            for r in records
        ]
    }

# ── Section 4: regime_alerts ─────────────────────────────────────────────────
briefing_by_pair = {b['pair']: b for b in briefing_raw}
regime_alerts    = []

for p in snapshot_raw['pairs']:
    if not p['regime_shift_flag']:
        continue

    name       = p['pair_name']
    c30        = p['corr_30d']
    c90        = p['corr_90d']
    gap        = round(abs(c30 - c90), 4)
    sev        = regime_shift_severity(c30, c90)
    brief      = briefing_by_pair.get(name, {})
    pattern_id = PAIR_TO_PATTERN.get(name)
    pattern    = KB_DICT.get(pattern_id, {})

    analogs = [
        {
            "period":          inst['period'],
            "context":         inst['context'],
            "equity_behavior": inst['equity_behavior'],
            "rates_behavior":  inst['rates_behavior'],
            "resolution":      inst['resolution']
        }
        for inst in pattern.get('historical_instances', [])
    ]

    regime_alerts.append({
        "pair_id":                 name,
        "label":                   PAIR_META[name]['label'],
        "alert_severity":          sev,
        "regime_shift_gap":        gap,
        "current_corr_30d":        round(c30, 4),
        "current_corr_90d":        round(c90, 4),
        "regime_theme":            brief.get('regime_theme', pattern.get('macro_theme', '')),
        "plain_english_summary":   brief.get('plain_english_summary', ''),
        "watch_list":              brief.get('watch_list', pattern.get('warning_signals', [])),
        "typical_duration_months": pattern.get('typical_duration_months'),
        "historical_analogs":      analogs,
        "narrative_card": {
            "title":           f"Regime Alert: {PAIR_META[name]['label']}",
            "severity_badge":  sev.upper() if sev else "LOW",
            "body":            brief.get('plain_english_summary', ''),
            "analogs_summary": [a['period'] for a in analogs],
            "action_items":    brief.get('watch_list', [])
        }
    })

# ── Section 5: heatmap_data ───────────────────────────────────────────────────
heatmap_data = {
    "description": "30-day Pearson correlation for each tracked pair. Use pair_id as the row/column key.",
    "as_of_date":  snapshot_date,
    "cells": [
        {
            "pair_id":          p['pair_name'],
            "label":            PAIR_META[p['pair_name']]['label'],
            "asset_a":          PAIR_META[p['pair_name']]['asset_a'],
            "asset_b":          PAIR_META[p['pair_name']]['asset_b'],
            "corr_30d":         round(p['corr_30d'], 4),
            "corr_60d":         round(p['corr_60d'], 4),
            "corr_90d":         round(p['corr_90d'], 4),
            "regime_shift_flag": p['regime_shift_flag']
        }
        for p in snapshot_raw['pairs']
    ]
}

# ── Assemble and write ────────────────────────────────────────────────────────
api_response = {
    "meta":                meta,
    "current_snapshot":    current_snapshot,
    "heatmap_data":        heatmap_data,
    "correlation_history": correlation_history,
    "regime_alerts":       regime_alerts
}

output_path = _path('api_response.json')
with open(output_path, 'w') as f:
    json.dump(api_response, f, indent=2, default=str)

print(f"api_response.json written to {output_path}")

size_kb  = os.path.getsize(output_path) / 1024
total_dp = sum(len(v['data_points']) for v in correlation_history.values())
print(f"File size: {size_kb:.1f} KB")
print(f"\nSections:")
print(f"  meta                  — {len(meta)} top-level fields")
print(f"  current_snapshot      — {len(current_snapshot['pairs'])} pairs")
print(f"  heatmap_data          — {len(heatmap_data['cells'])} cells")
print(f"  correlation_history   — {len(correlation_history)} pairs, {total_dp} data points (last 90 days)")
print(f"  regime_alerts         — {len(regime_alerts)} active alerts")
for alert in regime_alerts:
    print(f"    [{alert['alert_severity'].upper()}] {alert['pair_id']}  "
          f"gap={alert['regime_shift_gap']}  analogs={len(alert['historical_analogs'])}")
