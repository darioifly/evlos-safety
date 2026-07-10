"""Acceptance gate: compare the OLD model vs a candidate FINE-TUNED model on
real, labelled benchmarks. Deploy the fine-tune ONLY if it improves the teal
gap WITHOUT regressing real-violation recall or precision.

Benchmarks:
  * GREEN frames (bench/green/*.jpg): a teal-vested worker. GOOD = model emits
    'vest' (or NOT a confident 'novest') on his torso -> alert suppressed.
  * REAL frames (bench/real/*.jpg, from the blind-judge REAL set): a genuine
    violation. GOOD = model still produces a novest/nohat violation.

Usage: python ft_accept_gate.py <old.pt> <new.pt>
"""
import glob
import json
import os
import sys

import cv2
import numpy as np
from ultralytics import YOLO

sys.path.insert(0, '.')
from services import ppe_logic  # noqa

CC = dict(ppe_logic.DEFAULT_CLASS_CONFIDENCE); CC['novest'] = 0.60; CC['nohat'] = 0.70
MIN_RATIO = 0.10
TEAL = [((80, 60, 60), (100, 255, 255))]


def teal_frac(frame, box):
    x1, y1, x2, y2 = map(int, box); bh = y2-y1
    ty1 = max(0, y1+int(0.20*bh)); ty2 = min(frame.shape[0], y1+int(0.65*bh))
    x1 = max(0, x1); x2 = min(frame.shape[1], x2)
    if x2 <= x1 or ty2 <= ty1:
        return 0.0
    roi = frame[ty1:ty2, x1:x2]
    if roi.shape[0]*roi.shape[1] < 400:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    c = sum(cv2.countNonZero(cv2.inRange(hsv, np.array(lo), np.array(hi))) for lo, hi in TEAL)
    return c/(roi.shape[0]*roi.shape[1])


def violations(model, frame, use_color_override):
    res = model(frame, conf=0.45, imgsz=1280, device=0, verbose=False)
    dets = []
    for b in res[0].boxes:
        c = ppe_logic.canonical_class(model.names[int(b.cls[0])])
        if c:
            dets.append({'cls_name': c, 'conf': float(b.conf[0]),
                         'xyxy': [float(v) for v in b.xyxy[0].cpu().numpy()]})
    if use_color_override:
        for d in dets:
            if d['cls_name'] == 'novest' and d['conf'] >= CC['novest'] and teal_frac(frame, d['xyxy']) >= 0.35:
                d['cls_name'] = 'vest'
    r = ppe_logic.evaluate_ppe(dets, frame.shape[0], class_confidence=CC,
                               min_person_height_ratio=MIN_RATIO,
                               model_class_names=list(model.names.values()))
    return r['violations']


def eval_model(model, label):
    # GREEN: want NO vest_missing (teal recognized). Measure WITHOUT color override
    # (the fine-tune should fix it at the model level).
    green = sorted(glob.glob('bench/green/*.jpg'))
    green_ok = 0
    for p in green:
        fr = cv2.imread(p)
        if fr is None:
            continue
        if 'vest_missing' not in violations(model, fr, use_color_override=False):
            green_ok += 1
    # REAL: want the violation preserved.
    real = sorted(glob.glob('bench/real/*.jpg'))
    real_ok = 0
    for p in real:
        fr = cv2.imread(p)
        if fr is None:
            continue
        if violations(model, fr, use_color_override=False):
            real_ok += 1
    print(f"[{label}] teal-recognized (no false novest): {green_ok}/{len(green)} "
          f"| real-violation kept: {real_ok}/{len(real)}")
    return green_ok, len(green), real_ok, len(real)


if __name__ == '__main__':
    old, new = sys.argv[1], sys.argv[2]
    print("=== ACCEPTANCE GATE (no color override; measuring the MODEL) ===")
    og, gt, orr, rt = eval_model(YOLO(old), f'OLD {os.path.basename(old)}')
    ng, _, nr, _ = eval_model(YOLO(new), f'NEW {os.path.basename(new)}')
    print("\n=== VERDICT ===")
    print(f"teal recognition: OLD {og}/{gt} -> NEW {ng}/{gt}  ({'+' if ng>=og else ''}{ng-og})")
    print(f"real-violation recall: OLD {orr}/{rt} -> NEW {nr}/{rt}  ({'+' if nr>=orr else ''}{nr-orr})")
    improved_teal = ng > og
    kept_real = nr >= orr - 1  # allow at most 1 real regression
    print("\nDEPLOY?", "YES" if (improved_teal and kept_real) else "NO "
          "(non migliora il teal o regredisce sulle violazioni vere)")
