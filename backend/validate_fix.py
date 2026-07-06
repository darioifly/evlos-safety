"""E2E validation: run the REAL model on REAL past-alert frames and compare
the old decision (any novest => alert) with the new ppe_logic decision."""
import sys
import cv2
from ultralytics import YOLO

from services import ppe_logic

MODEL = YOLO('models/ppe/helmet_vest.pt')
CLASS_CONF = dict(ppe_logic.DEFAULT_CLASS_CONFIDENCE)

for path in sys.argv[1:]:
    frame = cv2.imread(path)
    if frame is None:
        print(f"{path}: CANNOT READ")
        continue
    h, w = frame.shape[:2]
    results = MODEL(frame, conf=0.45, imgsz=1280, verbose=False, device='cpu')
    dets = []
    raw = []
    for box in results[0].boxes:
        name = MODEL.names[int(box.cls[0])]
        conf = float(box.conf[0])
        raw.append(f"{name}:{conf:.2f}")
        canon = ppe_logic.canonical_class(name)
        if canon is None:
            continue
        dets.append({'cls_name': canon, 'conf': conf,
                     'xyxy': box.xyxy[0].cpu().numpy()})

    # OLD decision: alert if any novest at conf >= 0.75 (old global threshold)
    old_alert = any(d['cls_name'] == 'novest' and d['conf'] >= 0.75 for d in dets)
    old_alert = old_alert or any(d['cls_name'] == 'nohat' and d['conf'] >= 0.75 for d in dets)

    r = ppe_logic.evaluate_ppe(
        dets, h, class_confidence=CLASS_CONF,
        min_person_height_ratio=0.06,
        model_class_names=list(MODEL.names.values()),
    )
    name = path.split('\\')[-1].split('/')[-1]
    print(f"--- {name} ({w}x{h})")
    print(f"    raw: {', '.join(raw) if raw else '(nothing)'}")
    print(f"    OLD single-frame verdict: {'ALERT' if old_alert else 'no alert'}")
    print(f"    NEW single-frame verdict: {sorted(r['violations']) or 'no violation'} "
          f"(persons={r['person_count']} eligible={r['eligible_count']} "
          f"ignored_bg={r['ignored_violations']})")
    print(f"    (NEW also requires 3-of-5 frames before alerting)")
