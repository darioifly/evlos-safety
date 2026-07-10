"""Ensemble auto-labeler for the PPE fine-tune.

Produces HIGH-QUALITY YOLO labels (5-class: 0 hat,1 nohat,2 novest,3 person,
4 vest) by combining THREE PPE models + the validated teal-vest correction +
person-association filtering. Design goals:

  * Better VEST RECALL than any single model (union of vest evidence) so we
    don't teach the model that vests are background (the auto-label trap).
  * Fix the wesjos blind spot: teal/green vests (novest->vest on teal torso).
  * Drop background/unassociated violation boxes and distant-person clutter.
  * Resolve vest-vs-novest conflicts on the same torso in favour of VEST.
  * Emit an 'uncertain' flag per person so a downstream audit can exclude
    images whose labelling is not confident+complete.

Writes labels to datasets/ppe_ft/labels and copies images; also writes
label_meta.jsonl (per-image confidence/telemetry) for the audit step.
"""
import glob
import json
import os
import shutil

import cv2
import numpy as np
from ultralytics import YOLO

SRC = 'data/static/alerts'
OUT = 'datasets/ppe_ft'
CLASS = {'hat': 0, 'nohat': 1, 'novest': 2, 'person': 3, 'vest': 4}

# --- per-model class -> canonical (None = ignore)
WESJOS = {'hat': 'hat', 'nohat': 'nohat', 'vest': 'vest', 'novest': 'novest',
          'person': 'person'}
CONSTR = {'Hardhat': 'hat', 'NO-Hardhat': 'nohat', 'Safety Vest': 'vest',
          'NO-Safety Vest': 'novest', 'Person': 'person'}
WORKSP = {'head_helmet': 'hat', 'head_nohelmet': 'nohat', 'vest': 'vest',
          'person': 'person'}  # no novest class

MODELS = [
    ('models/ppe/helmet_vest.pt', WESJOS),
    ('models/ppe/construction_safety.pt', CONSTR),
    ('models/ppe/workspace_safety.pt', WORKSP),
]
CONF = 0.35
MIN_PERSON_RATIO = 0.10       # eligibility (matches deployed gate)
TEAL = [((80, 60, 60), (100, 255, 255))]
TEAL_THR = 0.35
SAME_TORSO_IOU = 0.45
ASSOC_IOU = 0.25


def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter/ua if ua > 0 else 0.0


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


def nms(boxes, thr=0.6):
    """Greedy dedup, keep highest conf."""
    boxes = sorted(boxes, key=lambda d: -d['conf'])
    keep = []
    for b in boxes:
        if all(iou(b['xyxy'], k['xyxy']) < thr for k in keep):
            keep.append(b)
    return keep


def associated(person, item):
    px1, py1, px2, py2 = person
    ph = py2-py1
    cx = (item[0]+item[2])/2; cy = (item[1]+item[3])/2
    center_in = px1 <= cx <= px2 and (py1-0.15*ph) <= cy <= py2
    return center_in or iou(person, item) > ASSOC_IOU


def detect_all(models, frame):
    """Return dict canonical -> list of {xyxy, conf, model}."""
    out = {'hat': [], 'nohat': [], 'vest': [], 'novest': [], 'person': []}
    for mi, (mdl, cmap) in enumerate(models):
        res = mdl(frame, conf=CONF, imgsz=1280, device=0, verbose=False)
        for b in res[0].boxes:
            raw = mdl.names[int(b.cls[0])]
            canon = cmap.get(raw)
            if canon:
                out[canon].append({'xyxy': [float(v) for v in b.xyxy[0].cpu().numpy()],
                                   'conf': float(b.conf[0]), 'model': mi})
    return out


VEST_CORROBORATE_CONF = 0.60


def corroborate_vests(raw_vests):
    """Keep a vest detection only if it is CORROBORATED: >=2 distinct models
    agree on that torso, OR a single model is confident (>=0.60). A lone
    weak vest detection (esp. from the vest-only workspace model) is dropped
    so it cannot wrongly override a real novest -> avoids teaching the model
    to see vests that aren't there (which would MISS real violations)."""
    kept = []
    for v in raw_vests:
        models = {w['model'] for w in raw_vests if iou(v['xyxy'], w['xyxy']) >= 0.5}
        if len(models) >= 2 or v['conf'] >= VEST_CORROBORATE_CONF:
            kept.append(v)
    return kept


def label_frame(models, frame):
    """Return (label_lines, meta). label_lines: (cls_idx, xyxy). meta: telemetry."""
    H, W = frame.shape[:2]
    d = detect_all(models, frame)

    persons = nms(d['person'], 0.6)
    persons = [p for p in persons if (p['xyxy'][3]-p['xyxy'][1]) >= MIN_PERSON_RATIO*H]
    vests = nms(corroborate_vests(d['vest']), 0.5)  # corroborated vests only
    novests = nms(d['novest'], 0.5)
    hats = nms(d['hat'], 0.5)
    nohats = nms(d['nohat'], 0.5)

    # teal correction: novest torso that is teal -> reclassify as vest
    corrected = 0
    kept_novest = []
    for nv in novests:
        if teal_frac(frame, nv['xyxy']) >= TEAL_THR:
            vests.append(nv); corrected += 1
    novests = [nv for nv in novests if teal_frac(frame, nv['xyxy']) < TEAL_THR]

    # vest-vs-novest conflict on same torso -> keep vest
    novests = [nv for nv in novests
               if not any(iou(nv['xyxy'], v['xyxy']) >= SAME_TORSO_IOU for v in vests)]
    nohats = [nh for nh in nohats
              if not any(iou(nh['xyxy'], h['xyxy']) >= SAME_TORSO_IOU for h in hats)]

    lines = []
    for p in persons:
        lines.append(('person', p['xyxy']))

    uncertain = 0
    # only keep item boxes associated with an eligible person
    def emit(items, cls):
        nonlocal uncertain
        for it in items:
            if any(associated(p['xyxy'], it['xyxy']) for p in persons):
                lines.append((cls, it['xyxy']))
            else:
                uncertain += 1  # unassociated item = ambiguous
    emit(vests, 'vest'); emit(novests, 'novest')
    emit(hats, 'hat'); emit(nohats, 'nohat')

    # per-person completeness: a person with neither vest nor novest nearby is
    # ambiguous (missing-label risk) -> flag.
    persons_wo_vestinfo = 0
    for p in persons:
        has = any(associated(p['xyxy'], it['xyxy']) for it in vests+novests)
        if not has:
            persons_wo_vestinfo += 1

    meta = {'persons': len(persons), 'vests': len(vests), 'novests': len(novests),
            'teal_corrected': corrected, 'unassociated_items': uncertain,
            'persons_without_vest_info': persons_wo_vestinfo}
    return lines, meta


def to_yolo(box, W, H):
    x1, y1, x2, y2 = box
    return ((x1+x2)/2/W, (y1+y2)/2/H, (x2-x1)/W, (y2-y1)/H)


def main():
    models = [(YOLO(p), c) for p, c in MODELS]
    for split in ('train', 'val'):
        os.makedirs(f'{OUT}/images/{split}', exist_ok=True)
        os.makedirs(f'{OUT}/labels/{split}', exist_ok=True)
    files = sorted(glob.glob(f'{SRC}/*_full.jpg'))
    meta_f = open(f'{OUT}/label_meta.jsonl', 'w')
    import re
    fre = re.compile(r'_(\d{8})_')
    n = 0
    for i, path in enumerate(files):
        m = fre.search(os.path.basename(path))
        split = 'val' if (m and m.group(1)[-1] in '05') else 'train'
        frame = cv2.imread(path)
        if frame is None:
            continue
        H, W = frame.shape[:2]
        lines, meta = label_frame(models, frame)
        stem = os.path.splitext(os.path.basename(path))[0]
        shutil.copy2(path, f'{OUT}/images/{split}/{stem}.jpg')
        with open(f'{OUT}/labels/{split}/{stem}.txt', 'w') as f:
            for cls, box in lines:
                cx, cy, w, h = to_yolo(box, W, H)
                f.write(f"{CLASS[cls]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        meta['file'] = f'{stem}.jpg'; meta['split'] = split
        meta_f.write(json.dumps(meta) + '\n')
        n += 1
        if (i+1) % 200 == 0:
            print(f"  {i+1}/{len(files)}", flush=True)
    meta_f.close()

    # data.yaml
    with open(f'{OUT}/data.yaml', 'w') as f:
        f.write(f"path: {os.path.abspath(OUT).replace(os.sep,'/')}\n")
        f.write("train: images/train\nval: images/val\n")
        f.write("names:\n  0: hat\n  1: nohat\n  2: novest\n  3: person\n  4: vest\n")

    # summary
    metas = [json.loads(l) for l in open(f'{OUT}/label_meta.jsonl') if l.strip()]
    from collections import Counter
    tc = sum(m['teal_corrected'] for m in metas)
    amb = sum(m['persons_without_vest_info'] for m in metas)
    print(f"\ndone: {n} images labelled -> {OUT}")
    print(f"teal corrections applied: {tc}")
    print(f"persons without vest info (ambiguous): {amb}")
    print("split:", Counter(m['split'] for m in metas))


if __name__ == '__main__':
    main()
