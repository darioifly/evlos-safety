"""
Download COMBINED PPE Model (Helmet + Vest + More)
100% FREE - keremberke/yolov8m-protective-equipment-detection
"""
import sys
import os
from pathlib import Path

print("="*70)
print("COMBINED PPE Detection Model (Helmet + Vest)")
print("="*70)
print("\n[OK] 100% FREE - No account needed")
print("[OK] Detects: helmet, vest, gloves, goggles, mask, shoes")
print("[OK] Also detects: no_helmet, no_vest, etc.\n")

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

print("\n[*] Downloading COMBINED PPE detection model...")
print("Repository: keremberke/yolov8m-protective-equipment-detection")
print("This may take 1-2 minutes (model size ~52MB)...")

try:
    # Download from Hugging Face (FREE, no account)
    model_path = hf_hub_download(
        repo_id="keremberke/yolov8m-protective-equipment-detection",
        filename="best.pt",
        cache_dir=str(models_dir)
    )

    # Copy to easy location
    import shutil
    final_path = models_dir / "ppe_combined.pt"
    shutil.copy(model_path, final_path)

    print(f"\n[OK] Model downloaded!")
    print(f"[*] Location: {final_path}")

    # Test model
    print("\n[*] Testing model...")
    model = YOLO(str(final_path))
    print(f"[OK] Model loaded successfully!")

    classes = list(model.names.values())
    print(f"\n[*] Classes detected ({len(classes)} total):")
    for i, cls in enumerate(classes):
        print(f"    {i}: {cls}")

    # Save path
    config_path = Path(__file__).parent / "ppe_model_path.txt"
    with open(config_path, 'w') as f:
        f.write(str(final_path))

    print("\n" + "="*70)
    print("[SUCCESS] Combined PPE Model ready to use!")
    print("="*70)
    print(f"\n[*] Model file: {final_path}")
    print(f"[*] Size: ~52 MB")
    print(f"[*] Type: YOLOv8m (medium - good balance)")
    print(f"\n[*] Key classes for your use case:")

    # Highlight important classes
    important = ['helmet', 'no_helmet', 'vest', 'no_vest', 'no-helmet', 'no-vest']
    for cls in classes:
        cls_lower = cls.lower().replace('_', '-').replace(' ', '-')
        if any(imp in cls_lower for imp in important):
            print(f"    [!] {cls}")

    print(f"\n[*] Next steps:")
    print(f"    1. Test with camera images: python test_combined_ppe.py")
    print(f"    2. Integrate into video_worker.py")
    print(f"    3. Configure dual-mode (day: PPE / night: intrusion)")

except Exception as e:
    print(f"\n[ERROR] {e}")
    print("\n[*] Alternative: Manual download")
    print("1. Go to: https://huggingface.co/keremberke/yolov8m-protective-equipment-detection")
    print("2. Click 'Files and versions'")
    print("3. Download 'best.pt'")
    print(f"4. Save to: {models_dir / 'ppe_combined.pt'}")
