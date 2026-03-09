"""
Test YOLO person detection on real camera stream
Standalone script to verify YOLO works correctly without FastAPI
"""
import sys
import time
import cv2
import numpy as np
import requests
from ultralytics import YOLO
import torch

# Camera configuration (Pontinia 1 - first online camera)
CAMERA_ID = "1fcfa7bd-cc44-4d1d-2a4e-d248180effba"
CAMERA_NAME = "Pontinia 1"
STREAM_URL = f"http://192.168.1.31:7001/media/{CAMERA_ID}.mpjpeg"
NX_USERNAME = "admin"
NX_PASSWORD = "Sicurezza12!"

# YOLO configuration
MODEL_PATH = "backend/yolov8n.pt"
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
CONFIDENCE_THRESHOLD = 0.5
PERSON_CLASS_ID = 0

# Processing configuration
FRAME_SAMPLING = 30  # Process 1 every 30 frames
MAX_FRAMES = 300     # Test for ~10 seconds of video

def test_yolo_stream():
    """Test YOLO on camera stream"""
    print("=" * 60)
    print("YOLO Person Detection Stream Test")
    print("=" * 60)
    print(f"Camera: {CAMERA_NAME}")
    print(f"Stream URL: {STREAM_URL}")
    print(f"Device: {DEVICE}")
    print(f"Model: {MODEL_PATH}")
    print(f"Frame Sampling: 1/{FRAME_SAMPLING}")
    print("=" * 60)

    # Load YOLO model
    print(f"\n[1/4] Loading YOLO model...")
    model = YOLO(MODEL_PATH)
    model.to(DEVICE)
    print(f"✓ Model loaded on {DEVICE}")

    # Connect to stream
    print(f"\n[2/4] Connecting to camera stream...")
    try:
        from requests.auth import HTTPBasicAuth
        auth = HTTPBasicAuth(NX_USERNAME, NX_PASSWORD)
        response = requests.get(STREAM_URL, auth=auth, stream=True, timeout=10, verify=False)
        if response.status_code != 200:
            print(f"✗ Failed to connect: HTTP {response.status_code}")
            return
        print(f"✓ Connected to stream")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return

    # Process stream
    print(f"\n[3/4] Processing frames (sampling 1/{FRAME_SAMPLING})...")
    print("Looking for persons in video stream...")
    print("-" * 60)

    bytes_data = bytes()
    frame_count = 0
    processed_count = 0
    person_detections = []
    start_time = time.time()

    try:
        for chunk in response.iter_content(chunk_size=4096):
            if frame_count >= MAX_FRAMES:
                break

            bytes_data += chunk

            # Parse MJPEG boundaries
            a = bytes_data.find(b'\xff\xd8')  # JPEG start
            b = bytes_data.find(b'\xff\xd9')  # JPEG end

            if a != -1 and b != -1:
                jpg = bytes_data[a:b+2]
                bytes_data = bytes_data[b+2:]

                # Decode frame
                frame = cv2.imdecode(
                    np.frombuffer(jpg, dtype=np.uint8),
                    cv2.IMREAD_COLOR
                )

                if frame is not None:
                    frame_count += 1

                    # Sample frames
                    if frame_count % FRAME_SAMPLING == 0:
                        processed_count += 1

                        # Resize to standard size
                        frame = cv2.resize(frame, (640, 480))

                        # Run YOLO
                        results = model(
                            frame,
                            conf=CONFIDENCE_THRESHOLD,
                            classes=[PERSON_CLASS_ID],
                            verbose=False
                        )

                        # Check for persons
                        boxes = results[0].boxes
                        if boxes is not None and len(boxes) > 0:
                            person_count = len(boxes)
                            confidences = boxes.conf.cpu().numpy()
                            avg_conf = float(np.mean(confidences))

                            person_detections.append({
                                'frame': frame_count,
                                'processed': processed_count,
                                'count': person_count,
                                'confidence': avg_conf
                            })

                            print(f"Frame {frame_count:3d} (#{processed_count:2d}): "
                                  f"DETECTED {person_count} person(s) "
                                  f"(confidence: {avg_conf:.2f})")
                        else:
                            print(f"Frame {frame_count:3d} (#{processed_count:2d}): No persons detected")

    except KeyboardInterrupt:
        print("\n\n✓ Test interrupted by user")
    except Exception as e:
        print(f"\n✗ Error during processing: {e}")
        import traceback
        traceback.print_exc()

    # Results
    elapsed = time.time() - start_time
    print("-" * 60)
    print(f"\n[4/4] Test Results:")
    print(f"  Total frames received: {frame_count}")
    print(f"  Frames processed: {processed_count}")
    print(f"  Frames with person(s): {len(person_detections)}")
    print(f"  Processing time: {elapsed:.1f}s")
    print(f"  Average FPS: {frame_count / elapsed:.1f}")
    print(f"  Detection rate: {len(person_detections) / max(processed_count, 1) * 100:.1f}%")

    if person_detections:
        print(f"\n✓ SUCCESS: YOLO detected persons in the stream!")
        print(f"\nDetection summary:")
        for det in person_detections[:5]:  # Show first 5
            print(f"  - Frame {det['frame']}: {det['count']} person(s) "
                  f"@ {det['confidence']:.2f} confidence")
        if len(person_detections) > 5:
            print(f"  ... and {len(person_detections) - 5} more detections")
    else:
        print(f"\n⚠ WARNING: No persons detected in {processed_count} frames")
        print(f"  This could mean:")
        print(f"  - No people in camera view during test")
        print(f"  - Camera pointing at empty area")
        print(f"  - Model confidence threshold too high")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_yolo_stream()
