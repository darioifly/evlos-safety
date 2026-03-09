"""
Quick PPE Model Downloader
100% FREE - No account required - Ready in 2 minutes!
"""
import sys
import os
from pathlib import Path

print("="*70)
print("FREE PPE Detection Model Downloader")
print("="*70)
print("\n[OK] 100% FREE - No account needed")
print("[OK] Download in 2 minutes")
print("[OK] Use offline forever\n")

# Install requirements
print("[*] Checking dependencies...")
try:
    from huggingface_hub import hf_hub_download
    print("[OK] huggingface_hub installed")
except ImportError:
    print("Installing huggingface_hub...")
    os.system(f"{sys.executable} -m pip install -q huggingface_hub")
    from huggingface_hub import hf_hub_download
    print("[OK] Installed")

try:
    from ultralytics import YOLO
    print("[OK] ultralytics installed")
except ImportError:
    print("Installing ultralytics...")
    os.system(f"{sys.executable} -m pip install -q ultralytics")
    from ultralytics import YOLO
    print("[OK] Installed")

# Create directory
models_dir = Path(__file__).parent / "models" / "ppe"
models_dir.mkdir(parents=True, exist_ok=True)

print("\n[*] Downloading PPE detection model...")
print("Repository: keremberke/yolov8m-hard-hat-detection")

try:
    # Download from Hugging Face (FREE, no account)
    model_path = hf_hub_download(
        repo_id="keremberke/yolov8m-hard-hat-detection",
        filename="best.pt",
        cache_dir=str(models_dir)
    )

    # Copy to easy location
    import shutil
    final_path = models_dir / "ppe_detection.pt"
    shutil.copy(model_path, final_path)

    print(f"\n[OK] Model downloaded!")
    print(f"[*] Location: {final_path}")

    # Test model
    print("\n[*] Testing model...")
    model = YOLO(str(final_path))
    print(f"[OK] Model loaded successfully!")
    print(f"\n[*] Classes detected: {list(model.names.values())}")

    # Save path
    config_path = Path(__file__).parent / "ppe_model_path.txt"
    with open(config_path, 'w') as f:
        f.write(str(final_path))

    print("\n" + "="*70)
    print("[SUCCESS] Model ready to use")
    print("="*70)
    print(f"\n[*] Model file: {final_path}")
    print(f"[*] Classes: {list(model.names.values())}")
    print(f"\n[*] Next step: Test with your camera images")
    print(f"    python test_ppe_model.py")

except Exception as e:
    print(f"\n[ERROR] {e}")
    print("\n[*] Alternative: Manual download")
    print("1. Go to: https://huggingface.co/keremberke/yolov8m-hard-hat-detection")
    print("2. Click 'Files and versions'")
    print("3. Download 'best.pt'")
    print(f"4. Save to: {models_dir / 'ppe_detection.pt'}")
