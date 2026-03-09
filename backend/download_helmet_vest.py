"""
Download HELMET + VEST Model
100% FREE - wesjos/Yolo-hard-hat-safety-vest
"""
import sys
import os
from pathlib import Path

print("="*70)
print("HELMET + VEST Detection Model")
print("="*70)
print("\n[OK] 100% FREE - No account needed")
print("[OK] Detects: Hard Hat + Safety Vest")
print("[OK] Perfect for construction site monitoring\n")

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

print("\n[*] Downloading HELMET + VEST model...")
print("Repository: wesjos/Yolo-hard-hat-safety-vest")
print("This may take 1-2 minutes...")

try:
    # Try to download model
    # First, list available files
    from huggingface_hub import list_repo_files

    print("[*] Checking available files...")
    files = list_repo_files(repo_id="wesjos/Yolo-hard-hat-safety-vest")
    print(f"[*] Found {len(files)} files in repository")

    # Look for model files
    model_files = [f for f in files if f.endswith('.pt') or f.endswith('.weights') or 'best' in f.lower()]

    if not model_files:
        print("[*] Available files:")
        for f in files[:10]:  # Show first 10
            print(f"    - {f}")

        # Try common filenames
        possible_names = ['best.pt', 'yolov8.pt', 'model.pt', 'weights.pt']
        for name in possible_names:
            if name in files:
                model_files = [name]
                break

    if model_files:
        model_file = model_files[0]
        print(f"[*] Downloading: {model_file}")

        model_path = hf_hub_download(
            repo_id="wesjos/Yolo-hard-hat-safety-vest",
            filename=model_file,
            cache_dir=str(models_dir)
        )

        # Copy to easy location
        import shutil
        final_path = models_dir / "helmet_vest.pt"
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
        print("[SUCCESS] Helmet + Vest Model ready!")
        print("="*70)
        print(f"\n[*] Model file: {final_path}")
        print(f"\n[*] Next steps:")
        print(f"    1. Test with camera images")
        print(f"    2. Integrate into video_worker.py")

    else:
        raise Exception("No model file found in repository")

except Exception as e:
    print(f"\n[ERROR] {e}")
    print("\n[*] This model might not have downloadable weights.")
    print("[*] Trying alternative approach...")

    # Alternative: Try ultralyticsplus
    try:
        print("\n[*] Trying with ultralyticsplus...")
        os.system(f"{sys.executable} -m pip install -q ultralyticsplus")

        from ultralyticsplus import YOLO as YOLO_PLUS

        model = YOLO_PLUS('wesjos/Yolo-hard-hat-safety-vest')

        # Save model
        final_path = models_dir / "helmet_vest.pt"
        model.save(str(final_path))

        print(f"\n[OK] Model loaded via ultralyticsplus!")
        print(f"[*] Classes: {list(model.names.values())}")

    except Exception as e2:
        print(f"\n[ERROR] {e2}")
        print("\n[!] ALTERNATIVE SOLUTION:")
        print("    Use the combined PPE model we already downloaded:")
        print(f"    {models_dir / 'ppe_combined.pt'}")
        print("    OR")
        print("    Use TWO models:")
        print(f"    - Helmet: {models_dir / 'ppe_detection.pt'}")
        print(f"    - Vest: Need to find another model or train custom")
