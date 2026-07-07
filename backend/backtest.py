"""Backtest: replay the historical alert screenshots (each *_full.jpg = one
alert the OLD pipeline fired) through the NEW decision pipeline and classify
what would happen now.

Two GPU passes per frame:
  * old-pass: imgsz 640 (the old code ran the model on the 640x480 frame with
    default imgsz) -> reproduces the old detections (boxes >= 0.75).
  * new-pass: imgsz 1280 -> feeds ppe_logic.evaluate_ppe with the deployed
    thresholds (preset ppe_confidence 0.75 raising violation bars) and the
    strict colour override, exactly like the live worker.

Output: backtest_results.jsonl (one record per frame) + summary on stdout.
NOTE: single-frame verdicts — the live pipeline ALSO requires 3-of-5
temporal confirmation, so 'still_violation' is an upper bound on alerts.
"""
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from services import ppe_logic

ALERTS_DIR = Path('data/static/alerts')
OUT_PATH = Path('backtest_results.jsonl')

MODEL = YOLO('models/ppe/helmet_vest.pt')
MODEL_CLASSES = list(MODEL.names.values())

# Deployed thresholds: config classConfidence (novest 0.75 dal 07/07) +
# preset 7 ppe_confidence=0.75 applied as a floor on violation classes.
PRESET_PPE_CONF = 0.75
CLASS_CONF = dict(ppe_logic.DEFAULT_CLASS_CONFIDENCE)
CLASS_CONF['novest'] = max(0.75, PRESET_PPE_CONF)  # 0.75
CLASS_CONF['nohat'] = max(CLASS_CONF['nohat'], PRESET_PPE_CONF)   # 0.75
MIN_RATIO = 0.06

# Strict colour override — same ranges/threshold as the deployed worker.
HIVIS_RANGES = [
    ((5, 120, 120), (20, 255, 255)),   # orange
    ((20, 100, 140), (40, 255, 255)),  # yellow
    ((40, 100, 120), (75, 255, 255)),  # green
]
OVERRIDE_THRESHOLD = 0.20
MIN_ROI_PIXELS = 400


def has_hivis(frame, xyxy):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(int, xyxy)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return False
    roi = frame[y1:y2, x1:x2]
    total = roi.shape[0] * roi.shape[1]
    if total < MIN_ROI_PIXELS:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    count = 0
    for lo, hi in HIVIS_RANGES:
        count += cv2.countNonZero(cv2.inRange(hsv, np.array(lo), np.array(hi)))
    return count / total >= OVERRIDE_THRESHOLD


def detect(frame, imgsz):
    res = MODEL(frame, conf=0.45, imgsz=imgsz, device=0, verbose=False)
    dets = []
    for b in res[0].boxes:
        raw = MODEL.names[int(b.cls[0])]
        canon = ppe_logic.canonical_class(raw)
        if canon is None:
            continue
        dets.append({'cls_name': canon, 'conf': float(b.conf[0]),
                     'xyxy': [float(v) for v in b.xyxy[0].cpu().numpy()]})
    return dets


FNAME_RE = re.compile(r'^(?P<cam>.+)_(?P<date>\d{8})_(?P<time>\d{6})_\d+_full\.jpg$')

records = []
files = sorted(ALERTS_DIR.glob('*_full.jpg'))
print(f"processing {len(files)} frames...", flush=True)

for i, path in enumerate(files):
    m = FNAME_RE.match(path.name)
    cam = m.group('cam') if m else '?'
    date = m.group('date') if m else '?'
    hour = int(m.group('time')[:2]) if m else -1

    frame = cv2.imread(str(path))
    if frame is None:
        continue
    H = frame.shape[0]

    # --- old pass: what the old pipeline saw (>=0.75 boxes, imgsz 640)
    old_dets = detect(frame, 640)
    old_viols = sorted({
        {'novest': 'vest', 'nohat': 'helmet'}[d['cls_name']]
        for d in old_dets
        if d['cls_name'] in ('novest', 'nohat') and d['conf'] >= 0.75
    })

    # --- new pass: full new pipeline, single frame
    # (colour override DISABLED as per deployed config 07/07/2026)
    dets = detect(frame, 1280)
    overrides = 0
    r = ppe_logic.evaluate_ppe(
        dets, H, class_confidence=CLASS_CONF,
        min_person_height_ratio=MIN_RATIO,
        model_class_names=MODEL_CLASSES,
    )

    is_day = 6 <= hour < 18
    viol_dets = [d for d in dets if d['cls_name'] in ('novest', 'nohat')]
    vetoed = sum(1 for d in dets if d.get('vetoed_by_vest') or d.get('vetoed_by_hat'))

    # Primary outcome classification
    if not is_day:
        outcome = 'night_now_intrusion'
    elif r['violations']:
        outcome = 'still_violation'
    elif overrides:
        outcome = 'suppressed_color_override'
    elif vetoed:
        outcome = 'suppressed_vest_veto'
    elif r['ignored_violations'] > 0:
        outcome = 'suppressed_background_or_far'
    elif any(d['conf'] < CLASS_CONF[d['cls_name']] for d in viol_dets):
        outcome = 'suppressed_below_threshold'
    elif not viol_dets:
        outcome = 'suppressed_no_violation_detected'
    else:
        outcome = 'suppressed_other'

    records.append({
        'file': path.name, 'camera': cam, 'date': date, 'hour': hour,
        'old_violations_reproduced': old_viols,
        'new_violations': sorted(r['violations']),
        'outcome': outcome,
        'persons': r['person_count'], 'eligible': r['eligible_count'],
        'ignored_bg': r['ignored_violations'], 'overrides': overrides,
        'vetoed': vetoed,
        'viol_dets': [(d['cls_name'], round(d['conf'], 2)) for d in viol_dets],
    })
    if (i + 1) % 200 == 0:
        print(f"  {i + 1}/{len(files)}", flush=True)

with open(OUT_PATH, 'w') as f:
    for rec in records:
        f.write(json.dumps(rec) + '\n')

# --- summary
from collections import Counter
print("\n=== OUTCOME SUMMARY (all frames) ===")
for k, v in Counter(rec['outcome'] for rec in records).most_common():
    print(f"  {k}: {v}")
print("\n=== OUTCOME BY CAMERA (day frames only) ===")
by_cam = {}
for rec in records:
    if rec['outcome'] == 'night_now_intrusion':
        continue
    by_cam.setdefault(rec['camera'], Counter())[rec['outcome']] += 1
for cam, cnt in sorted(by_cam.items()):
    total = sum(cnt.values())
    still = cnt.get('still_violation', 0)
    print(f"  {cam}: {total} alerts -> still_violation {still} "
          f"({100 * still // max(1, total)}%) | " +
          ", ".join(f"{k.replace('suppressed_', 's_')}:{v}"
                    for k, v in cnt.most_common() if k != 'still_violation'))
print(f"\nresults written to {OUT_PATH}")
