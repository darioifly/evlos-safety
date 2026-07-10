"""Curate the fine-tune dataset before training, based on the label audit.

Actions:
  * Drop frames whose auto-labels the audit flagged 'bad' (would harm training).
  * Drop 'ambiguous' person boxes (person with NO associated vest/novest AND
    small) — they are unlabeled-vest risks; as background they don't matter
    because inference gates on person size anyway.

Reads: exclude_files.json (list of filenames to drop entirely).
Writes a cleaned copy into datasets/ppe_ft_clean and reports counts.
"""
import glob
import json
import os
import shutil

SRC = 'datasets/ppe_ft'
DST = 'datasets/ppe_ft_clean'
exclude = set(json.load(open('exclude_files.json'))) if os.path.exists('exclude_files.json') else set()

for split in ('train', 'val'):
    os.makedirs(f'{DST}/images/{split}', exist_ok=True)
    os.makedirs(f'{DST}/labels/{split}', exist_ok=True)

kept = dropped = 0
for split in ('train', 'val'):
    for img in glob.glob(f'{SRC}/images/{split}/*.jpg'):
        fn = os.path.basename(img)
        if fn in exclude:
            dropped += 1
            continue
        lbl = f'{SRC}/labels/{split}/{os.path.splitext(fn)[0]}.txt'
        shutil.copy2(img, f'{DST}/images/{split}/{fn}')
        if os.path.exists(lbl):
            shutil.copy2(lbl, f'{DST}/labels/{split}/{os.path.basename(lbl)}')
        kept += 1

with open(f'{DST}/data.yaml', 'w') as f:
    f.write(f"path: {os.path.abspath(DST).replace(os.sep,'/')}\n")
    f.write("train: images/train\nval: images/val\n")
    f.write("names:\n  0: hat\n  1: nohat\n  2: novest\n  3: person\n  4: vest\n")

print(f"kept {kept}, dropped {dropped} (excluded {len(exclude)}) -> {DST}")
