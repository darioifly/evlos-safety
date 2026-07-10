"""Recon for the fine-tune: model classes/order, the 3 PPE models' classes,
existing dataset state, GPU/training feasibility."""
import glob
import os

import torch
from ultralytics import YOLO

print("=== torch/GPU ===")
print("torch", torch.__version__, "| cuda", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0))
free, total = torch.cuda.mem_get_info()
print(f"VRAM free {free/1e9:.1f} / {total/1e9:.1f} GB")

print("\n=== primary model (helmet_vest.pt) classes (INDEX ORDER matters for training) ===")
m = YOLO('models/ppe/helmet_vest.pt')
print(m.names)

print("\n=== other downloaded PPE models ===")
for p in ['models/ppe/construction_safety.pt', 'models/ppe/workspace_safety.pt']:
    if os.path.exists(p):
        try:
            print(p, '->', YOLO(p).names)
        except Exception as e:
            print(p, 'ERR', e)
    else:
        print(p, '(assente)')
# HuggingFace cached PPE models
for d in glob.glob('models/ppe/models--*'):
    print('  HF cache:', os.path.basename(d))

print("\n=== dataset esistente ===")
for split in ('train', 'val'):
    imgs = glob.glob(f'datasets/ppe_site/images/{split}/*.jpg')
    lbls = glob.glob(f'datasets/ppe_site/labels/{split}/*.txt')
    print(f"  {split}: {len(imgs)} img, {len(lbls)} label")
if os.path.exists('datasets/ppe_site/data.yaml'):
    print("  data.yaml:")
    print('   ', open('datasets/ppe_site/data.yaml').read().replace('\n', '\n    '))

print("\n=== archivio alert (fonte frame) ===")
alerts = glob.glob('data/static/alerts/*_full.jpg')
print(f"  {len(alerts)} full frames")
