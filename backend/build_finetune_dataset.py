"""Build a YOLO fine-tuning dataset from the site's alert-frame archive.

Weak labels come from the CURRENT helmet_vest model at low confidence —
they are a STARTING POINT to be human-reviewed (CVAT / Label Studio /
Roboflow) before training. Frames are split train/val by DATE so that
near-duplicate frames of the same episode never straddle the split.

Usage (from backend/, venv):
    python build_finetune_dataset.py [--out datasets/ppe_site] [--conf 0.35]

Then (after label review):
    yolo detect train model=models/ppe/helmet_vest.pt \
        data=datasets/ppe_site/data.yaml epochs=50 imgsz=1280 batch=8
"""
import argparse
import re
import shutil
from collections import Counter
from pathlib import Path

import cv2
from ultralytics import YOLO

ALERTS_DIR = Path('data/static/alerts')
FNAME_RE = re.compile(r'^(?P<cam>.+)_(?P<date>\d{8})_(?P<time>\d{6})_')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='datasets/ppe_site')
    ap.add_argument('--conf', type=float, default=0.35)
    ap.add_argument('--imgsz', type=int, default=1280)
    args = ap.parse_args()

    out = Path(args.out)
    for split in ('train', 'val'):
        (out / 'images' / split).mkdir(parents=True, exist_ok=True)
        (out / 'labels' / split).mkdir(parents=True, exist_ok=True)

    model = YOLO('models/ppe/helmet_vest.pt')
    names = model.names  # {id: name}

    files = sorted(ALERTS_DIR.glob('*_full.jpg'))
    stats = Counter()
    class_counts = Counter()

    for i, path in enumerate(files):
        m = FNAME_RE.match(path.name)
        if not m:
            continue
        # Split by date: days ending in 0/5 -> val (~20%), rest -> train.
        split = 'val' if m.group('date')[-1] in ('0', '5') else 'train'

        frame = cv2.imread(str(path))
        if frame is None:
            stats['unreadable'] += 1
            continue
        h, w = frame.shape[:2]

        results = model(frame, conf=args.conf, imgsz=args.imgsz,
                        device=0, verbose=False)
        lines = []
        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            x1, y1, x2, y2 = map(float, box.xyxy[0].cpu().numpy())
            cx = (x1 + x2) / 2 / w
            cy = (y1 + y2) / 2 / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            class_counts[names[cls_id]] += 1

        shutil.copy2(path, out / 'images' / split / path.name)
        label_path = out / 'labels' / split / (path.stem + '.txt')
        label_path.write_text('\n'.join(lines) + ('\n' if lines else ''))
        stats[split] += 1
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(files)}", flush=True)

    # data.yaml
    yaml_lines = [
        f"path: {out.resolve().as_posix()}",
        "train: images/train",
        "val: images/val",
        "names:",
    ]
    for cls_id in sorted(names):
        yaml_lines.append(f"  {cls_id}: {names[cls_id]}")
    (out / 'data.yaml').write_text('\n'.join(yaml_lines) + '\n')

    readme = [
        "# Dataset fine-tuning PPE (weak labels)",
        "",
        f"Frame: {stats['train']} train / {stats['val']} val "
        f"(split per DATA, niente leakage tra episodi)",
        f"Etichette deboli dal modello corrente a conf>={args.conf} — "
        "DA REVISIONARE (CVAT/Label Studio/Roboflow) prima del training.",
        "",
        "Box per classe (weak):",
        *[f"  - {k}: {v}" for k, v in class_counts.most_common()],
        "",
        "Errori noti del modello da correggere in revisione:",
        "  - novest su sfondo/macchinari (falsi box)",
        "  - vest/novest coesistenti sullo stesso torso (tenere il giusto)",
        "  - nohat 0.5-0.7 spesso corretti ma sotto-confidenti",
        "",
        "Training suggerito:",
        "  yolo detect train model=models/ppe/helmet_vest.pt "
        "data=data.yaml epochs=50 imgsz=1280 batch=8 patience=15",
    ]
    (out / 'README.md').write_text('\n'.join(readme) + '\n')

    print(f"\ndone: {dict(stats)} -> {out}")
    print("class counts:", dict(class_counts.most_common()))


if __name__ == '__main__':
    main()
