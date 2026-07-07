"""Stratified sampling of backtest outcomes for visual judging.
Reads backtest_results.jsonl, picks up to N per outcome (spread across
cameras and dates deterministically), writes sample manifest."""
import json
import sys
from collections import defaultdict

N_PER_OUTCOME = 12

records = [json.loads(l) for l in open('backtest_results.jsonl', encoding='utf-8')]
by_outcome = defaultdict(list)
for r in records:
    by_outcome[r['outcome']].append(r)

manifest = {}
for outcome, recs in sorted(by_outcome.items()):
    # spread: sort by (camera, date) and take evenly spaced elements
    recs = sorted(recs, key=lambda r: (r['camera'], r['file']))
    step = max(1, len(recs) // N_PER_OUTCOME)
    picked = recs[::step][:N_PER_OUTCOME]
    manifest[outcome] = [
        {'file': r['file'], 'camera': r['camera'],
         'old': r['old_violations_reproduced'], 'new': r['new_violations'],
         'viol_dets': r['viol_dets'], 'persons': r['persons'],
         'eligible': r['eligible'], 'hour': r['hour']}
        for r in picked
    ]

json.dump(manifest, open('backtest_sample_manifest.json', 'w'), indent=1)
for outcome, items in manifest.items():
    print(f"{outcome}: {len(items)} campioni (su {len(by_outcome[outcome])})")
