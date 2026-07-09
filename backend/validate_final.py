"""Final end-to-end check: run the REAL evaluate_ppe (novest 0.60,
minPersonHeightRatio 0.12, same-torso veto) on the 55 labeled live frames
and compare its single-frame violation verdict to the blind-judge ground
truth. This is the actual deployed decision logic (minus temporal+VLM)."""
import json
import os
from collections import defaultdict

import cv2
from ultralytics import YOLO

from services import ppe_logic

GT = json.load(open('validate_gt.json'))
DIR = 'validate_frames'
MODEL = YOLO('models/ppe/helmet_vest.pt')
NAMES = list(MODEL.names.values())
CLASS_CONF = dict(ppe_logic.DEFAULT_CLASS_CONFIDENCE)
CLASS_CONF['novest'] = 0.60
CLASS_CONF['nohat'] = 0.70
MIN_RATIO = 0.12

conf = defaultdict(lambda: [0, 0])  # gt -> [alert, no_alert]
for f, gt in GT.items():
    frame = cv2.imread(os.path.join(DIR, f))
    if frame is None:
        continue
    res = MODEL(frame, conf=0.45, imgsz=1280, device=0, verbose=False)
    dets = []
    for b in res[0].boxes:
        c = ppe_logic.canonical_class(MODEL.names[int(b.cls[0])])
        if c:
            dets.append({'cls_name': c, 'conf': float(b.conf[0]),
                         'xyxy': [float(v) for v in b.xyxy[0].cpu().numpy()]})
    r = ppe_logic.evaluate_ppe(dets, frame.shape[0], class_confidence=CLASS_CONF,
                               min_person_height_ratio=MIN_RATIO,
                               model_class_names=NAMES)
    alert = bool(r['violations'])
    conf[gt][0 if alert else 1] += 1

print("=== FINAL pipeline (novest 0.60 + gate 0.12) single-frame vs ground truth ===")
for gt in ('REAL', 'UNCLEAR', 'FALSE'):
    a, n = conf[gt]
    t = a + n
    if t:
        print(f"  {gt}: {t} -> ALERT {a}, no-alert {n}")
r = conf['REAL']
print(f"\nREAL still alerting: {r[0]}/{sum(r)} (recall)")
u = conf['UNCLEAR']
print(f"UNCLEAR suppressed: {u[1]}/{sum(u)} (noise cut)")
