import torch
from ultralytics import YOLO

print("=" * 50)
print("GPU CHECK")
print("=" * 50)

# PyTorch CUDA
print(f"\nPyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU count: {torch.cuda.device_count()}")
    print(f"GPU name: {torch.cuda.get_device_name(0)}")
    print(f"Current device: {torch.cuda.current_device()}")
else:
    print("CUDA NOT AVAILABLE - PyTorch is CPU-only")

# YOLO model check
print("\n" + "=" * 50)
print("YOLO MODEL CHECK")
print("=" * 50)

model = YOLO('yolov8n.pt')
print(f"\nYOLO device: {model.device}")

# Try to move to CUDA
if torch.cuda.is_available():
    model.to('cuda')
    print(f"YOLO moved to: {model.device}")
else:
    print("Cannot move YOLO to CUDA - not available")

print("\n" + "=" * 50)
