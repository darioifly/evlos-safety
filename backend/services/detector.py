"""
YOLOv8 Person Detection Service
"""
import time
from typing import List, Dict, Tuple
import numpy as np
import torch
from ultralytics import YOLO

from config import settings
from utils.logger import logger
from utils.metrics import metrics


class PersonDetector:
    """YOLOv8-based person detector with batch processing support"""

    def __init__(self):
        self.model_path = settings.YOLO_MODEL
        self.device = settings.DEVICE
        self.confidence = settings.CONFIDENCE_THRESHOLD
        self.model: Optional[YOLO] = None

        # Class ID for person in COCO dataset
        self.PERSON_CLASS_ID = 0

        self._load_model()

    def _load_model(self):
        """Load YOLOv8 model"""
        try:
            logger.info(f"Loading YOLO model: {self.model_path} on {self.device}")

            # Check CUDA availability
            if 'cuda' in self.device and not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU")
                self.device = 'cpu'
                settings.DEVICE = 'cpu'

            # Load model
            self.model = YOLO(self.model_path)
            self.model.to(self.device)

            logger.info(f"Model loaded successfully on {self.device}")

            # Test inference
            dummy_input = np.zeros((640, 640, 3), dtype=np.uint8)
            _ = self.model(dummy_input, verbose=False)
            logger.info("Model test inference successful")

        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise

    def reload_model(self, model_path: str = None, device: str = None):
        """
        Reload model with new parameters

        Args:
            model_path: Path to new model file
            device: Device to use (cuda/cpu)
        """
        if model_path:
            self.model_path = model_path
        if device:
            self.device = device

        self._load_model()
        logger.info(f"Model reloaded: {self.model_path} on {self.device}")

    def detect_batch(self, frames: List[np.ndarray], camera_ids: List[str]) -> List[Dict]:
        """
        Perform person detection on a batch of frames

        Args:
            frames: List of frames as numpy arrays
            camera_ids: List of camera IDs corresponding to frames

        Returns:
            List of detection results with camera_id, person_count, confidence, boxes
        """
        if not frames:
            return []

        start_time = time.time()

        try:
            # Run batch inference
            # NOTE: Don't pass device parameter - YOLO uses the device set during model.to(device)
            results = self.model(
                frames,
                conf=self.confidence,
                classes=[self.PERSON_CLASS_ID],  # Filter only persons
                verbose=False
            )

            # Process results
            detections = []
            for idx, (result, camera_id) in enumerate(zip(results, camera_ids)):
                detection = self._process_result(result, camera_id)
                detections.append(detection)

                # Record metrics
                if detection['person_count'] > 0:
                    metrics.record_detection(camera_id, detection['person_count'])

            # Record processing time
            processing_time = time.time() - start_time
            metrics.record_processing_time(processing_time)

            logger.debug(
                f"Processed batch of {len(frames)} frames in {processing_time:.3f}s "
                f"({len(frames)/processing_time:.1f} FPS)"
            )

            return detections

        except Exception as e:
            logger.error(f"Error in batch detection: {e}")
            metrics.record_error("detector")
            return [{'camera_id': cid, 'person_count': 0, 'confidence': 0.0, 'boxes': []}
                    for cid in camera_ids]

    def _process_result(self, result, camera_id: str) -> Dict:
        """Process a single detection result"""
        try:
            # Get detections
            boxes = result.boxes

            if boxes is None or len(boxes) == 0:
                return {
                    'camera_id': camera_id,
                    'person_count': 0,
                    'confidence': 0.0,
                    'boxes': []
                }

            # Extract person detections
            person_boxes = []
            confidences = []

            # OPTIMIZATION: Transfer all data from GPU to CPU once, not per-box
            if len(boxes) > 0:
                # Move all tensors to CPU in one go
                boxes_xyxy = boxes.xyxy.cpu().numpy()  # All boxes at once
                boxes_conf = boxes.conf.cpu().numpy()
                boxes_cls = boxes.cls.cpu().numpy()

                for i in range(len(boxes)):
                    conf = float(boxes_conf[i])
                    cls = int(boxes_cls[i])

                    # Filter only persons with sufficient confidence
                    if cls == self.PERSON_CLASS_ID and conf >= self.confidence:
                        # Get bounding box coordinates (already on CPU)
                        xyxy = boxes_xyxy[i]
                        person_boxes.append({
                            'x1': float(xyxy[0]),
                            'y1': float(xyxy[1]),
                            'x2': float(xyxy[2]),
                            'y2': float(xyxy[3]),
                            'confidence': conf
                        })
                        confidences.append(conf)

            # Calculate average confidence
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            return {
                'camera_id': camera_id,
                'person_count': len(person_boxes),
                'confidence': avg_confidence,
                'boxes': person_boxes
            }

        except Exception as e:
            logger.error(f"Error processing result for {camera_id}: {e}")
            return {
                'camera_id': camera_id,
                'person_count': 0,
                'confidence': 0.0,
                'boxes': []
            }

    def detect_single(self, frame: np.ndarray, camera_id: str) -> Dict:
        """
        Perform detection on a single frame

        Args:
            frame: Frame as numpy array
            camera_id: Camera identifier

        Returns:
            Detection result dictionary
        """
        return self.detect_batch([frame], [camera_id])[0]

    def update_confidence(self, confidence: float):
        """Update confidence threshold"""
        self.confidence = confidence
        logger.info(f"Confidence threshold updated to {confidence}")


# Global detector instance
detector = PersonDetector()
