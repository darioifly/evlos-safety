"""E2E validation of the VLM verifier against real judged alert frames.

Frames chosen from the blind-judging ground truth:
  - real helmet violation (Pontinia, workers with vests, one bare head)
  - real vest violation (Dragoni, man in white shirt inside the site)
  - compliant scene (Pontinia, everyone vested+helmeted)
Expected: confirm the first two, refute the third; zone=work_area for the
work-zone frames.
"""
import sys
import time

import cv2

from integrations.vlm_verifier import vlm_verifier

CFG = {'enabled': True, 'url': 'http://127.0.0.1:11434',
       'model': 'qwen2.5vl:7b', 'timeoutSeconds': 120}

CASES = [
    ('data/static/alerts/Pontinia_2_20260609_155250_920226_full.jpg',
     ['helmet_missing'], 'ATTESO: confermata (nohat vero, gilet ok)'),
    ('data/static/alerts/Dragoni_Carrello_PTZ_20260707_113955_173242_full.jpg',
     ['vest_missing'], 'ATTESO: confermata (uomo in maglietta bianca)'),
    ('data/static/alerts/Pontinia_2_20260514_132202_971179_full.jpg',
     ['vest_missing'], 'ATTESO: RIFIUTATA (tutti conformi)'),
]

for path, due, expect in CASES:
    frame = cv2.imread(path)
    if frame is None:
        print(f"{path}: CANNOT READ")
        continue
    t0 = time.time()
    v = vlm_verifier.verify(frame, due, CFG)
    dt = time.time() - t0
    name = path.split('/')[-1]
    print(f"--- {name} ({dt:.1f}s) [{expect}]")
    if v is None:
        print("    FAIL-OPEN (nessuna risposta)")
    else:
        print(f"    confirmed={v.get('violation_confirmed')} "
              f"vest={v.get('vest_violation')} helmet={v.get('helmet_violation')} "
              f"zone={v.get('zone')} people={v.get('people')}")
        print(f"    desc: {v.get('description')}")
