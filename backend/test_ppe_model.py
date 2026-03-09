"""
Test script for PPE Detection Model
Tests Roboflow Construction Safety model
"""
import cv2
import numpy as np
from ultralytics import YOLO
from pathlib import Path
import json

# ============================================================================
# CONFIGURATION
# ============================================================================

# Roboflow Model Info
# 1. Go to: https://universe.roboflow.com/roboflow-100/construction-safety-gsnvb
# 2. Click "Download Dataset"
# 3. Select "YOLOv8" format
# 4. Download and extract
# 5. Put the path to best.pt here

MODEL_PATH = "path/to/construction-safety/weights/best.pt"  # UPDATE THIS

# Test images (you can add paths to images from your cameras)
TEST_IMAGES = [
    # Add your test image paths here
    # "path/to/test_image1.jpg",
]

# Classes expected (update based on actual model)
EXPECTED_CLASSES = {
    0: 'hardhat',
    1: 'mask',
    2: 'no-hardhat',
    3: 'no-mask',
    4: 'no-safety vest',
    5: 'person',
    6: 'safety cone',
    7: 'safety vest',
    8: 'machinery',
    9: 'vehicle'
}

# ============================================================================
# TEST FUNCTION
# ============================================================================

def test_ppe_model():
    """Test PPE detection model"""
    print("="*60)
    print("PPE Detection Model Test")
    print("="*60)

    # Check if model exists
    if not Path(MODEL_PATH).exists():
        print(f"❌ Model not found at: {MODEL_PATH}")
        print("\nInstructions:")
        print("1. Go to: https://universe.roboflow.com/roboflow-100/construction-safety-gsnvb")
        print("2. Click 'Download Dataset'")
        print("3. Select 'YOLOv8' format")
        print("4. Download and extract")
        print("5. Update MODEL_PATH in this script")
        return

    # Load model
    print(f"\n📦 Loading model from: {MODEL_PATH}")
    model = YOLO(MODEL_PATH)
    print("✓ Model loaded successfully")

    # Print model info
    print(f"\n📊 Model Information:")
    print(f"   Classes: {model.names}")
    print(f"   Input size: {model.model.args.get('imgsz', 640)}")

    # Test with dummy image if no test images provided
    if not TEST_IMAGES or not any(Path(img).exists() for img in TEST_IMAGES):
        print("\n⚠️  No test images found. Testing with dummy image...")
        # Create a dummy test image
        dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
        cv2.putText(dummy_img, "TEST IMAGE", (200, 320),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        results = model(dummy_img, conf=0.5, verbose=True)
        print("✓ Model runs successfully (no detections on dummy image expected)")
        return

    # Test with real images
    print(f"\n🔍 Testing with {len(TEST_IMAGES)} images...")

    for img_path in TEST_IMAGES:
        if not Path(img_path).exists():
            print(f"❌ Image not found: {img_path}")
            continue

        print(f"\n📷 Processing: {img_path}")

        # Load image
        img = cv2.imread(img_path)

        # Run detection
        results = model(img, conf=0.5, verbose=False)

        # Analyze results
        boxes = results[0].boxes

        if len(boxes) == 0:
            print("   No detections")
            continue

        print(f"   Detections: {len(boxes)}")

        # Count by class
        detections_by_class = {}
        for box in boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = model.names[cls]

            if class_name not in detections_by_class:
                detections_by_class[class_name] = []
            detections_by_class[class_name].append(conf)

        # Print summary
        for class_name, confidences in detections_by_class.items():
            avg_conf = sum(confidences) / len(confidences)
            print(f"   - {class_name}: {len(confidences)} "
                  f"(avg conf: {avg_conf:.2%})")

        # Save annotated image
        annotated = results[0].plot()
        output_path = Path(img_path).parent / f"annotated_{Path(img_path).name}"
        cv2.imwrite(str(output_path), annotated)
        print(f"   💾 Saved annotated image: {output_path}")

    print("\n" + "="*60)
    print("✓ Test completed successfully")
    print("="*60)


def download_roboflow_model(api_key=None):
    """
    Helper function to download model from Roboflow

    Args:
        api_key: Your Roboflow API key (get from roboflow.com)
    """
    if not api_key:
        print("Please provide your Roboflow API key")
        print("Get it from: https://app.roboflow.com/settings/api")
        return

    try:
        from roboflow import Roboflow

        print("Downloading model from Roboflow...")
        rf = Roboflow(api_key=api_key)
        project = rf.workspace("roboflow-100").project("construction-safety-gsnvb")
        dataset = project.version(1).download("yolov8")

        print(f"✓ Model downloaded to: {dataset.location}")
        print(f"Update MODEL_PATH to: {dataset.location}/weights/best.pt")

    except ImportError:
        print("Please install roboflow package:")
        print("pip install roboflow")
    except Exception as e:
        print(f"Error downloading model: {e}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Uncomment to download model (requires API key)
    # download_roboflow_model(api_key="YOUR_API_KEY_HERE")

    # Test the model
    test_ppe_model()
