"""
build_api_response_mini.py
Produces api_response_mini.json from api_response.json by:
  - Keeping meta, current_snapshot, heatmap_data, regime_alerts intact
  - Trimming correlation_history to the last 30 data points per pair
  - Rounding all floats to 4 decimal places to shave extra bytes
"""
import json, copy, os

with open('/home/ubuntu/api_response.json') as f:
    full = json.load(f)

mini = copy.deepcopy(full)

# ── Trim correlation_history to last 30 data points per pair ──────────────────
for pair_id, hist in mini['correlation_history'].items():
    pts = hist['data_points']
    trimmed = pts[-30:]                          # last 30 chronologically
    hist['data_points'] = trimmed
    if trimmed:
        hist['date_range']['from'] = trimmed[0]['date']
        hist['date_range']['to']   = trimmed[-1]['date']

# ── Round all floats to 4dp to reduce character count ─────────────────────────
def round_floats(obj, dp=4):
    if isinstance(obj, float):
        return round(obj, dp)
    if isinstance(obj, dict):
        return {k: round_floats(v, dp) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(i, dp) for i in obj]
    return obj

mini = round_floats(mini)

# ── Write with compact separators to minimise whitespace ─────────────────────
output_path = '/home/ubuntu/api_response_mini.json'
with open(output_path, 'w') as f:
    json.dump(mini, f, separators=(',', ':'))

# ── Report ────────────────────────────────────────────────────────────────────
size_kb   = os.path.getsize(output_path) / 1024
full_kb   = os.path.getsize('/home/ubuntu/api_response.json') / 1024
total_pts = sum(len(v['data_points']) for v in mini['correlation_history'].values())

print(f"Original size : {full_kb:.1f} KB")
print(f"Mini size     : {size_kb:.1f} KB  ({'PASS' if size_kb < 30 else 'FAIL'} — target < 30 KB)")
print(f"Reduction     : {(1 - size_kb/full_kb)*100:.1f}%")
print(f"\nStructure check:")
print(f"  meta fields           : {len(mini['meta'])}")
print(f"  current_snapshot pairs: {len(mini['current_snapshot']['pairs'])}")
print(f"  heatmap cells         : {len(mini['heatmap_data']['cells'])}")
print(f"  history pairs         : {len(mini['correlation_history'])}")
print(f"  history data points   : {total_pts}  ({total_pts//6} per pair)")
print(f"  regime_alerts         : {len(mini['regime_alerts'])}")
for a in mini['regime_alerts']:
    print(f"    [{a['alert_severity'].upper()}] {a['pair_id']}  "
          f"analogs={len(a['historical_analogs'])}  "
          f"narrative_card={'yes' if a.get('narrative_card') else 'MISSING'}")
