"""Does person-box SIZE separate REAL (verifiable) from UNCLEAR (too far)?

Run YOLO on each labeled live frame, record the tallest person box as a
fraction of frame height, and see where a minPersonHeightRatio threshold
would split REAL vs UNCLEAR. If size separates them, we can drop the flaky
VLM and just raise the eligibility gate.
"""
import json
import os
from collections import defaultdict

import cv2
from ultralytics import YOLO

from services import ppe_logic

GT = json.load(open('validate_gt.json'))
DIR = 'validate_frames'
MODEL = YOLO('models/ppe/helmet_vest.pt')

rows = []
for f, gt in GT.items():
    frame = cv2.imread(os.path.join(DIR, f))
    if frame is None:
        continue
    h = frame.shape[0]
    res = MODEL(frame, conf=0.45, imgsz=1280, device=0, verbose=False)
    maxr = 0.0
    for b in res[0].boxes:
        if ppe_logic.canonical_class(MODEL.names[int(b.cls[0])]) == 'person':
            x1, y1, x2, y2 = b.xyxy[0].cpu().numpy()
            maxr = max(maxr, (y2 - y1) / h)
    rows.append((gt, maxr, f))

# distribution
buckets = defaultdict(lambda: defaultdict(int))
for gt, r, f in rows:
    b = ('<0.10' if r < 0.10 else '0.10-0.15' if r < 0.15 else
         '0.15-0.25' if r < 0.25 else '0.25-0.40' if r < 0.40 else '>=0.40')
    buckets[b][gt] += 1
print("tallest-person-ratio distribution (REAL vs UNCLEAR):")
for b in ('<0.10', '0.10-0.15', '0.15-0.25', '0.25-0.40', '>=0.40'):
    print(f"  {b:>10}: REAL {buckets[b]['REAL']:2d}  UNCLEAR {buckets[b]['UNCLEAR']:2d}")

# threshold sweep: keep frames with maxr >= thr
print("\nthreshold sweep (keep alert only if tallest person >= thr):")
print("   thr   REAL_kept  UNCLEAR_kept")
for thr in (0.06, 0.10, 0.12, 0.15, 0.18, 0.22, 0.30):
    rk = sum(1 for gt, r, f in rows if gt == 'REAL' and r >= thr)
    uk = sum(1 for gt, r, f in rows if gt == 'UNCLEAR' and r >= thr)
    rt = sum(1 for gt, r, f in rows if gt == 'REAL')
    ut = sum(1 for gt, r, f in rows if gt == 'UNCLEAR')
    print(f"  {thr:.2f}   {rk:2d}/{rt} ({100*rk//rt:3d}%)  {uk:2d}/{ut} ({100*uk//ut:3d}%)")
