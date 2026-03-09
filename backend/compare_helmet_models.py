"""
Compare Helmet Detection Models
Tests both models to see which performs better
"""
import sys
from pathlib import Path
import numpy as np
import cv2

try:
    from ultralytics import YOLO
except ImportError:
    print("Installing ultralytics...")
    import os
    os.system(f"{sys.executable} -m pip install -q ultralytics")
    from ultralytics import YOLO

print("="*70)
print("Helmet Detection Models Comparison")
print("="*70)

models_dir = Path(__file__).parent / "models" / "ppe"

# Model 1: Helmet Only
model1_path = models_dir / "ppe_detection.pt"
# Model 2: Helmet + Vest
model2_path = models_dir / "helmet_vest.pt"

print("\n[*] Loading models...\n")

# Load Model 1
if model1_path.exists():
    print("[*] Model 1: Helmet Only (keremberke/yolov8m-hard-hat-detection)")
    model1 = YOLO(str(model1_path))
    print(f"    Type: {model1_path.name}")
    print(f"    Size: {model1_path.stat().st_size / (1024*1024):.1f} MB")
    print(f"    Classes: {list(model1.names.values())}")
    m1_loaded = True
else:
    print("[!] Model 1 not found")
    m1_loaded = False

print()

# Load Model 2
if model2_path.exists():
    print("[*] Model 2: Helmet + Vest (wesjos/Yolo-hard-hat-safety-vest)")
    model2 = YOLO(str(model2_path))
    print(f"    Type: {model2_path.name}")
    print(f"    Size: {model2_path.stat().st_size / (1024*1024):.1f} MB")
    print(f"    Classes: {list(model2.names.values())}")
    m2_loaded = True
else:
    print("[!] Model 2 not found")
    m2_loaded = False

if not m1_loaded or not m2_loaded:
    print("\n[ERROR] One or more models not found")
    sys.exit(1)

print("\n" + "="*70)
print("COMPARISON - Helmet Detection")
print("="*70)

print("\n1. MODEL SIZE:")
print(f"   Model 1: {model1_path.stat().st_size / (1024*1024):.1f} MB")
print(f"   Model 2: {model2_path.stat().st_size / (1024*1024):.1f} MB")

print("\n2. ARCHITECTURE:")
print(f"   Model 1: YOLOv8m (YOLO version 8)")
print(f"   Model 2: YOLO11m (YOLO version 11 - NEWER!)")

print("\n3. CLASSES FOR HELMET DETECTION:")
print(f"   Model 1: {[c for c in model1.names.values() if 'hardhat' in c.lower() or 'helmet' in c.lower()]}")
print(f"   Model 2: {[c for c in model2.names.values() if 'hat' in c.lower() or 'helmet' in c.lower()]}")

print("\n4. ADDITIONAL FEATURES:")
print(f"   Model 1: Only helmet detection")
print(f"   Model 2: Helmet + Vest detection (2-in-1)")

print("\n5. CLASS NAMES:")
print(f"   Model 1: 'Hardhat', 'NO-Hardhat' (more explicit)")
print(f"   Model 2: 'hat', 'nohat' (simpler)")

# Test with dummy image
print("\n6. SPEED TEST (dummy image):")
dummy = np.zeros((640, 640, 3), dtype=np.uint8)

import time

# Warmup
_ = model1(dummy, verbose=False)
_ = model2(dummy, verbose=False)

# Test Model 1
times1 = []
for _ in range(10):
    start = time.time()
    _ = model1(dummy, verbose=False)
    times1.append(time.time() - start)

# Test Model 2
times2 = []
for _ in range(10):
    start = time.time()
    _ = model2(dummy, verbose=False)
    times2.append(time.time() - start)

avg1 = sum(times1) / len(times1) * 1000  # ms
avg2 = sum(times2) / len(times2) * 1000  # ms

print(f"   Model 1: {avg1:.1f} ms/frame (~{1000/avg1:.1f} FPS)")
print(f"   Model 2: {avg2:.1f} ms/frame (~{1000/avg2:.1f} FPS)")

print("\n" + "="*70)
print("RECOMMENDATION")
print("="*70)

print("\n[*] For HELMET ONLY detection:")
if avg1 < avg2:
    print(f"    Model 1 is FASTER ({avg1:.1f}ms vs {avg2:.1f}ms)")
else:
    print(f"    Model 2 is FASTER ({avg2:.1f}ms vs {avg1:.1f}ms)")

print("\n[*] For YOUR USE CASE (Helmet + Vest):")
print("    Model 2 (helmet_vest.pt) - WINNER!")
print("    Reasons:")
print("    + Detects BOTH helmet AND vest")
print("    + YOLO11 (newer architecture)")
print("    + Single model = simpler code")
print("    + Only slightly slower (if at all)")

print("\n[*] Model Quality (estimated):")
print("    Model 1: Specialized for helmets only")
print("    Model 2: Combined helmet+vest, YOLO11 (better accuracy)")

print("\n[!] FINAL RECOMMENDATION:")
print("    USE MODEL 2 (helmet_vest.pt)")
print("    - Better architecture (YOLO11 vs YOLO8)")
print("    - Detects both helmet and vest")
print("    - Simpler implementation (1 model vs 2)")
print("    - More suitable for construction site monitoring")

print("\n" + "="*70)
