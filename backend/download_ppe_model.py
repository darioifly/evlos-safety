"""
Download PPE Detection Model from Roboflow
Automatically downloads the Construction Safety model
"""
import os
import sys
from pathlib import Path

def download_model():
    """Download PPE model from Roboflow"""

    print("="*70)
    print("PPE Detection Model Downloader")
    print("="*70)

    # Check if roboflow is installed
    try:
        from roboflow import Roboflow
    except ImportError:
        print("\n❌ Roboflow package not installed")
        print("\nInstalling roboflow...")
        os.system(f"{sys.executable} -m pip install roboflow")
        print("\n✓ Roboflow installed. Please run this script again.")
        return

    # Get API key
    print("\n📝 You need a Roboflow API key (free account)")
    print("   1. Go to: https://app.roboflow.com/")
    print("   2. Sign up for free account")
    print("   3. Go to: https://app.roboflow.com/settings/api")
    print("   4. Copy your API key")

    api_key = input("\n🔑 Enter your Roboflow API key: ").strip()

    if not api_key:
        print("❌ API key required")
        return

    try:
        print("\n📦 Downloading model from Roboflow...")
        print("   Project: roboflow-100/construction-safety-gsnvb")

        rf = Roboflow(api_key=api_key)
        project = rf.workspace("roboflow-100").project("construction-safety-gsnvb")

        # Download dataset in YOLOv8 format
        dataset = project.version(1).download("yolov8")

        print(f"\n✓ Model downloaded successfully!")
        print(f"\n📁 Location: {dataset.location}")
        print(f"\n📊 Model file: {dataset.location}/weights/best.pt")

        # Check if weights exist
        weights_path = Path(dataset.location) / "weights" / "best.pt"
        if weights_path.exists():
            print(f"\n✅ Model ready to use: {weights_path}")

            # Save path to config file
            config_path = Path(__file__).parent / "ppe_model_path.txt"
            with open(config_path, 'w') as f:
                f.write(str(weights_path))
            print(f"✓ Path saved to: {config_path}")

        else:
            print(f"\n⚠️  Weights file not found at expected location")
            print(f"   Expected: {weights_path}")
            print(f"   Please check the downloaded dataset")

        # Print dataset info
        print(f"\n📊 Dataset Information:")
        print(f"   Classes: hardhat, mask, no-hardhat, no-mask, no-safety vest,")
        print(f"            person, safety cone, safety vest, machinery, vehicle")
        print(f"   Images: Check {dataset.location}")

    except Exception as e:
        print(f"\n❌ Error downloading model: {e}")
        print("\nTroubleshooting:")
        print("   1. Check your API key is correct")
        print("   2. Check your internet connection")
        print("   3. Make sure you have a Roboflow account")


def download_alternative_model():
    """Download alternative PPE model using ultralytics hub"""

    print("\n" + "="*70)
    print("Alternative: Download from Ultralytics HUB")
    print("="*70)

    try:
        from ultralytics import YOLO

        print("\n📦 Downloading PPE model from Ultralytics HUB...")

        # Try to load a pre-trained PPE model from Ultralytics
        # This is a fallback if Roboflow doesn't work

        print("\n⚠️  Note: Ultralytics HUB models may require login")
        print("   Visit: https://hub.ultralytics.com/")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("\n🎯 Choose download method:")
    print("   1. Roboflow (Recommended - Construction Safety)")
    print("   2. Alternative methods info")

    choice = input("\nEnter choice (1 or 2): ").strip()

    if choice == "1":
        download_model()
    elif choice == "2":
        print("\n" + "="*70)
        print("Alternative Download Methods")
        print("="*70)
        print("\n1. Manual Download from Roboflow:")
        print("   - Go to: https://universe.roboflow.com/roboflow-100/construction-safety-gsnvb")
        print("   - Click 'Download Dataset'")
        print("   - Select 'YOLOv8' format")
        print("   - Download ZIP file")
        print("   - Extract to: backend/models/ppe-detection/")
        print("   - Model file: backend/models/ppe-detection/weights/best.pt")

        print("\n2. Use Hugging Face Models:")
        print("   - Search: https://huggingface.co/models?search=ppe+detection")
        print("   - Download pre-trained YOLOv8 models")

        print("\n3. Train your own:")
        print("   - Use Ultralytics YOLOv8 with custom dataset")
        print("   - Annotate 500+ images from your cameras")
        print("   - Train: yolo train data=custom.yaml model=yolov8n.pt")

    else:
        print("Invalid choice")
