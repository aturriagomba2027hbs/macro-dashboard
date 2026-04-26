"""
build_api_response_mini.py
Produces api_response_mini.json from api_response.json by:
  - Keeping meta, current_snapshot, heatmap_data, regime_alerts intact
  - Trimming correlation_history to the last 30 data points per pair
  - Rounding all floats to 4 decimal places to shave extra bytes

After generating the file, automatically pushes it to a public GitHub Gist
if the environment variables GIST_ID and GIST_TOKEN are set.
"""
import json
import copy
import os
import sys
import requests

# ── Resolve paths relative to this script's location ─────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH  = os.path.join(SCRIPT_DIR, 'api_response.json')
OUTPUT_PATH = os.path.join(SCRIPT_DIR, 'api_response_mini.json')

# ── Load full api_response.json ───────────────────────────────────────────────
with open(INPUT_PATH) as f:
    full = json.load(f)

mini = copy.deepcopy(full)

# ── Trim correlation_history to last 30 data points per pair ─────────────────
for pair_id, hist in mini['correlation_history'].items():
    pts     = hist['data_points']
    trimmed = pts[-30:]                      # keep the most recent 30 rows
    hist['data_points'] = trimmed
    if trimmed:
        hist['date_range']['from'] = trimmed[0]['date']
        hist['date_range']['to']   = trimmed[-1]['date']

# ── Round all floats to 4 decimal places ─────────────────────────────────────
def round_floats(obj, dp=4):
    if isinstance(obj, float):
        return round(obj, dp)
    if isinstance(obj, dict):
        return {k: round_floats(v, dp) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(i, dp) for i in obj]
    return obj

mini = round_floats(mini)

# ── Serialise with compact separators ────────────────────────────────────────
json_str = json.dumps(mini, separators=(',', ':'))

with open(OUTPUT_PATH, 'w') as f:
    f.write(json_str)

# ── Console summary ───────────────────────────────────────────────────────────
size_kb   = os.path.getsize(OUTPUT_PATH) / 1024
full_kb   = os.path.getsize(INPUT_PATH) / 1024
total_pts = sum(len(v['data_points']) for v in mini['correlation_history'].values())

print(f"Original size : {full_kb:.1f} KB")
print(f"Mini size     : {size_kb:.1f} KB  ({'PASS' if size_kb < 30 else 'FAIL'} — target < 30 KB)")
print(f"Reduction     : {(1 - size_kb/full_kb)*100:.1f}%")
print(f"\nStructure check:")
print(f"  meta fields           : {len(mini['meta'])}")
print(f"  current_snapshot pairs: {len(mini['current_snapshot']['pairs'])}")
print(f"  heatmap cells         : {len(mini['heatmap_data']['cells'])}")
print(f"  history pairs         : {len(mini['correlation_history'])}")
print(f"  history data points   : {total_pts}  ({total_pts // 6} per pair)")
print(f"  regime_alerts         : {len(mini['regime_alerts'])}")
for a in mini['regime_alerts']:
    print(f"    [{a['alert_severity'].upper()}] {a['pair_id']}  "
          f"analogs={len(a['historical_analogs'])}  "
          f"narrative_card={'yes' if a.get('narrative_card') else 'MISSING'}")

# ── Push to GitHub Gist ───────────────────────────────────────────────────────
GIST_ID    = os.environ.get('GIST_ID', '').strip()
GIST_TOKEN = os.environ.get('GIST_TOKEN', '').strip()

if not GIST_ID or not GIST_TOKEN:
    print("\nGist push skipped — GIST_ID or GIST_TOKEN not set.")
    print("Set both environment variables to enable automatic Gist publishing.")
    sys.exit(0)

print(f"\nPushing api_response_mini.json to Gist {GIST_ID} ...")

gist_url = f"https://api.github.com/gists/{GIST_ID}"
headers  = {
    "Authorization": f"token {GIST_TOKEN}",
    "Accept":        "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
payload = {
    "description": f"Macro Dashboard API — auto-updated {mini['meta']['snapshot_date']}",
    "files": {
        "api_response_mini.json": {
            "content": json_str
        }
    }
}

response = requests.patch(gist_url, headers=headers, json=payload, timeout=30)

if response.status_code == 200:
    gist_data   = response.json()
    raw_url     = gist_data['files']['api_response_mini.json']['raw_url']
    gist_html   = gist_data['html_url']
    print(f"Gist updated successfully!")
    print(f"  Gist page : {gist_html}")
    print(f"  Raw URL   : {raw_url}")
    print()
    # Print the stable raw URL (without the commit hash) for use in Lovable
    stable_raw = (
        f"https://gist.githubusercontent.com/"
        f"{gist_data['owner']['login']}/{GIST_ID}/raw/api_response_mini.json"
    )
    print(f"  Stable raw URL (use this in Lovable):")
    print(f"  {stable_raw}")
else:
    print(f"ERROR: Gist push failed — HTTP {response.status_code}")
    print(response.text)
    sys.exit(1)
