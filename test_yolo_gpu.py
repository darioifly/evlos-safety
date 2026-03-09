"""
Test if YOLO is actually using GPU for inference
"""
import torch
import numpy as np
from ultralytics import YOLO
import time

print("=" * 60)
print("YOLO GPU INFERENCE TEST")
print("=" * 60)

# Check CUDA
print(f"\n1. PyTorch CUDA Check:")
print(f"   CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"   GPU name: {torch.cuda.get_device_name(0)}")
    print(f"   Initial GPU memory: {torch.cuda.memory_allocated(0) / 1024**2:.2f} MB")

# Load model
print(f"\n2. Loading YOLO model...")
model = YOLO('yolov8n.pt')

print(f"   Model device before .to(): {model.device}")

# Move to CUDA
if torch.cuda.is_available():
    model.to('cuda:0')
    print(f"   Model device after .to('cuda:0'): {model.device}")
    print(f"   GPU memory after model load: {torch.cuda.memory_allocated(0) / 1024**2:.2f} MB")

# Create test frames
print(f"\n3. Creating test batch (8 frames, 640x480)...")
frames = [np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(8)]

# Test inference
print(f"\n4. Running inference...")
if torch.cuda.is_available():
    print(f"   GPU memory before inference: {torch.cuda.memory_allocated(0) / 1024**2:.2f} MB")

start_time = time.time()
results = model(frames, conf=0.5, classes=[0], verbose=False)
inference_time = time.time() - start_time

print(f"   Inference completed in {inference_time:.3f}s")
print(f"   FPS: {len(frames) / inference_time:.1f}")

if torch.cuda.is_available():
    print(f"   GPU memory after inference: {torch.cuda.memory_allocated(0) / 1024**2:.2f} MB")
    print(f"   GPU utilization should spike during inference!")

print(f"\n5. Results:")
print(f"   Processed {len(results)} frames")
for i, result in enumerate(results[:3]):  # Show first 3
    detections = len(result.boxes) if result.boxes is not None else 0
    print(f"   Frame {i}: {detections} detections")

# Performance check
print(f"\n6. Performance Analysis:")
if inference_time < 0.5:
    print(f"   ✓ FAST! Likely using GPU ({len(frames) / inference_time:.1f} FPS)")
else:
    print(f"   ✗ SLOW! Likely using CPU ({len(frames) / inference_time:.1f} FPS)")
    print(f"   Expected GPU: >30 FPS, Expected CPU: <5 FPS")

print("\n" + "=" * 60)
print("Run 'nvidia-smi' during this test to see GPU utilization spike!")
print("=" * 60)
