"""
Multi-process YOLO Detection Worker
Runs in separate process to avoid GIL blocking the FastAPI server
Supports both intrusion detection (person) and PPE detection (helmet/vest)
"""
import multiprocessing as mp
import time
from typing import Dict, List
from pathlib import Path
import numpy as np
import torch
from ultralytics import YOLO

from config import settings
from utils.logger import logger
from utils.metrics import metrics


class DetectionWorker:
    """
    YOLO detection worker that runs in a separate process.
    Each worker has its own Python interpreter, GIL, and CUDA context.
    Supports both intrusion and PPE detection modes.
    """

    def __init__(self, worker_id: int, input_queue: mp.Queue, output_queue: mp.Queue):
        self.worker_id = worker_id
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.person_model = None  # Model for person detection (intrusion)
        self.ppe_model = None     # Model for PPE detection
        self.running = True
        self.PERSON_CLASS_ID = 0
        self.device = None

    def initialize(self):
        """Initialize YOLO models in worker process"""
        try:
            # Determine device
            if 'cuda' in settings.DEVICE and not torch.cuda.is_available():
                logger.warning(f"[Worker {self.worker_id}] CUDA not available, using CPU")
                self.device = 'cpu'
            else:
                self.device = settings.DEVICE

            logger.info(f"[Worker {self.worker_id}] Initializing YOLO models on {self.device}")

            # Load person detection model (for intrusion mode)
            self.person_model = YOLO(settings.YOLO_MODEL)
            self.person_model.to(self.device)
            logger.info(f"[Worker {self.worker_id}] Person model loaded on {self.device}")

            # Load PPE detection model if available
            # Priority: helmet_vest.pt (has both helmet and vest classes) > ppe_detection.pt (helmet only) > ppe_combined.pt
            ppe_model_paths = [
                Path(__file__).parent.parent / "models" / "ppe" / "helmet_vest.pt",      # Full PPE: hat, nohat, vest, novest, person
                Path(__file__).parent.parent / "models" / "ppe" / "ppe_detection.pt",    # Helmet only: Hardhat, NO-Hardhat
                Path(__file__).parent.parent / "models" / "ppe" / "ppe_combined.pt",     # Alternative PPE model
            ]

            for ppe_model_path in ppe_model_paths:
                if ppe_model_path.exists():
                    self.ppe_model = YOLO(str(ppe_model_path))
                    self.ppe_model.to(self.device)
                    # Log the classes available in this model
                    class_names = list(self.ppe_model.names.values())
                    logger.info(f"[Worker {self.worker_id}] PPE model loaded from {ppe_model_path}")
                    logger.info(f"[Worker {self.worker_id}] PPE model classes: {class_names}")
                    break

            if self.ppe_model is None:
                logger.warning(f"[Worker {self.worker_id}] No PPE model found, PPE detection will be disabled")

            # Warm-up inference
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            _ = self.person_model(dummy, verbose=False)
            if self.ppe_model:
                _ = self.ppe_model(dummy, verbose=False)
            logger.info(f"[Worker {self.worker_id}] Warm-up complete, ready for inference")

        except Exception as e:
            logger.error(f"[Worker {self.worker_id}] Failed to initialize: {e}")
            raise

    def run(self):
        """Main worker loop - runs in separate process"""
        self.initialize()

        logger.info(f"[Worker {self.worker_id}] Started processing loop")

        while self.running:
            try:
                # Get batch from queue (with timeout to allow checking self.running)
                try:
                    batch_data = self.input_queue.get(timeout=0.1)
                except mp.queues.Empty:
                    continue

                if batch_data is None:  # Poison pill to stop worker
                    logger.info(f"[Worker {self.worker_id}] Received stop signal")
                    break

                # Process batch
                detections = self._process_batch(batch_data)

                # Send results back
                self.output_queue.put(detections)

            except Exception as e:
                logger.error(f"[Worker {self.worker_id}] Error in processing loop: {e}")
                time.sleep(0.1)

        logger.info(f"[Worker {self.worker_id}] Stopped")

    def _process_batch(self, batch_data: List[Dict]) -> List[Dict]:
        """Process a batch of frames with YOLO based on detection mode"""
        try:
            start_time = time.time()
            detections = []

            for item in batch_data:
                frame = item['frame']
                camera_id = item['camera_id']
                detection_config = item.get('detection_config', {})
                detection_mode = detection_config.get('detection_mode', 'intrusion')

                if detection_mode == 'ppe' and self.ppe_model:
                    detection = self._process_ppe_frame(frame, camera_id, detection_config)
                else:
                    detection = self._process_intrusion_frame(frame, camera_id, detection_config)

                # Include frame in detection result for accurate alert screenshots
                detection['frame'] = frame
                detections.append(detection)

            # Log performance
            processing_time = time.time() - start_time
            fps = len(batch_data) / processing_time if processing_time > 0 else 0

            logger.debug(
                f"[Worker {self.worker_id}] Processed {len(batch_data)} frames "
                f"in {processing_time:.3f}s ({fps:.1f} FPS)"
            )

            return detections

        except Exception as e:
            logger.error(f"[Worker {self.worker_id}] Error processing batch: {e}")
            return [{'camera_id': item['camera_id'], 'person_count': 0, 'confidence': 0.0, 'boxes': [], 'alert_type': None}
                    for item in batch_data]

    def _process_intrusion_frame(self, frame: np.ndarray, camera_id: str, detection_config: dict) -> Dict:
        """Process frame for intrusion detection (person detection)"""
        try:
            # Get confidence threshold from config or use default
            confidence_threshold = detection_config.get('intrusion_confidence', settings.CONFIDENCE_THRESHOLD)

            # Run person detection
            results = self.person_model(
                frame,
                conf=confidence_threshold,
                classes=[self.PERSON_CLASS_ID],
                verbose=False
            )

            result = results[0]
            boxes = result.boxes

            if boxes is None or len(boxes) == 0:
                return {
                    'camera_id': camera_id,
                    'person_count': 0,
                    'confidence': 0.0,
                    'boxes': [],
                    'alert_type': None,
                    'detection_mode': 'intrusion'
                }

            person_boxes = []
            confidences = []

            # Transfer data from GPU to CPU
            boxes_xyxy = boxes.xyxy.cpu().numpy()
            boxes_conf = boxes.conf.cpu().numpy()
            boxes_cls = boxes.cls.cpu().numpy()

            for i in range(len(boxes)):
                conf = float(boxes_conf[i])
                cls = int(boxes_cls[i])

                if cls == self.PERSON_CLASS_ID and conf >= confidence_threshold:
                    xyxy = boxes_xyxy[i]
                    person_boxes.append({
                        'x1': float(xyxy[0]),
                        'y1': float(xyxy[1]),
                        'x2': float(xyxy[2]),
                        'y2': float(xyxy[3]),
                        'confidence': conf,
                        'class': 'person'
                    })
                    confidences.append(conf)

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            min_persons = detection_config.get('intrusion_min_persons', 1)

            # Determine if alert should be triggered
            alert_type = 'intrusion' if len(person_boxes) >= min_persons else None

            return {
                'camera_id': camera_id,
                'person_count': len(person_boxes),
                'confidence': avg_confidence,
                'boxes': person_boxes,
                'alert_type': alert_type,
                'detection_mode': 'intrusion'
            }

        except Exception as e:
            logger.error(f"[Worker {self.worker_id}] Error processing intrusion frame: {e}")
            return {
                'camera_id': camera_id,
                'person_count': 0,
                'confidence': 0.0,
                'boxes': [],
                'alert_type': None,
                'detection_mode': 'intrusion'
            }

    def _process_ppe_frame(self, frame: np.ndarray, camera_id: str, detection_config: dict) -> Dict:
        """Process frame for PPE detection (helmet/vest violations)"""
        try:
            # Get PPE-specific config
            confidence_threshold = detection_config.get('ppe_confidence', 0.6)
            require_helmet = detection_config.get('ppe_require_helmet', True)
            require_vest = detection_config.get('ppe_require_vest', True)

            # Run PPE detection
            results = self.ppe_model(
                frame,
                conf=confidence_threshold,
                verbose=False
            )

            result = results[0]
            boxes = result.boxes

            if boxes is None or len(boxes) == 0:
                return {
                    'camera_id': camera_id,
                    'person_count': 0,
                    'confidence': 0.0,
                    'boxes': [],
                    'alert_type': None,
                    'ppe_violations': [],
                    'detection_mode': 'ppe'
                }

            # Transfer data from GPU to CPU
            boxes_xyxy = boxes.xyxy.cpu().numpy()
            boxes_conf = boxes.conf.cpu().numpy()
            boxes_cls = boxes.cls.cpu().numpy()

            # Categorize detections
            all_boxes = []      # All detections (for logging)
            ppe_boxes = []      # Only PPE-related boxes (for screenshot drawing)
            persons = []
            helmets = []
            vests = []
            no_helmets = []
            no_vests = []
            confidences = []

            # Classes to ignore (not relevant for vest/helmet PPE detection)
            ignored_classes = {
                'machinery', 'vehicle', 'safety cone',  # construction_safety.pt
                'mask', 'no-mask',  # construction_safety.pt
                'ear', 'ear-mufs', 'face', 'face-guard', 'face-mask',  # sh17 - body parts/other PPE
                'foot', 'hands', 'head', 'tool', 'glasses', 'gloves',  # sh17 - body parts/other PPE
                'shoes', 'safety-suit', 'medical-suit'  # sh17 - other PPE
            }

            for i in range(len(boxes)):
                conf = float(boxes_conf[i])
                cls_id = int(boxes_cls[i])
                cls_name = self.ppe_model.names[cls_id].lower()

                # Skip ignored classes
                if cls_name in ignored_classes:
                    continue

                xyxy = boxes_xyxy[i]

                box_data = {
                    'x1': float(xyxy[0]),
                    'y1': float(xyxy[1]),
                    'x2': float(xyxy[2]),
                    'y2': float(xyxy[3]),
                    'confidence': conf,
                    'class': cls_name
                }
                all_boxes.append(box_data)
                confidences.append(conf)

                # Categorize by class
                if 'person' in cls_name:
                    persons.append(box_data)
                    # Don't add 'person' to ppe_boxes - we only want PPE-specific classes for display
                elif 'helmet' in cls_name or 'hat' in cls_name or 'hardhat' in cls_name:
                    if 'no' in cls_name:
                        no_helmets.append(box_data)
                    else:
                        helmets.append(box_data)
                    ppe_boxes.append(box_data)  # Add PPE class to display boxes
                elif 'vest' in cls_name:
                    if 'no' in cls_name:
                        no_vests.append(box_data)
                    else:
                        vests.append(box_data)
                    ppe_boxes.append(box_data)  # Add PPE class to display boxes

            # Check for PPE violations
            ppe_violations = []
            if require_helmet and len(no_helmets) > 0:
                ppe_violations.append('helmet_missing')
            if require_vest and len(no_vests) > 0:
                ppe_violations.append('vest_missing')

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            person_count = len(persons) if persons else max(len(no_helmets), len(no_vests), 1) if ppe_violations else 0

            # Determine alert type
            alert_type = 'ppe_violation' if ppe_violations else None

            return {
                'camera_id': camera_id,
                'person_count': person_count,
                'confidence': avg_confidence,
                'boxes': ppe_boxes if ppe_boxes else all_boxes,  # Use PPE-specific boxes for display, fallback to all
                'alert_type': alert_type,
                'ppe_violations': ppe_violations,
                'detection_mode': 'ppe',
                'helmets': len(helmets),
                'vests': len(vests),
                'no_helmets': len(no_helmets),
                'no_vests': len(no_vests)
            }

        except Exception as e:
            logger.error(f"[Worker {self.worker_id}] Error processing PPE frame: {e}")
            return {
                'camera_id': camera_id,
                'person_count': 0,
                'confidence': 0.0,
                'boxes': [],
                'alert_type': None,
                'ppe_violations': [],
                'detection_mode': 'ppe'
            }


def worker_process(worker_id: int, input_queue: mp.Queue, output_queue: mp.Queue):
    """
    Entry point for worker process.
    This function runs in a separate Python process.
    """
    try:
        worker = DetectionWorker(worker_id, input_queue, output_queue)
        worker.run()
    except KeyboardInterrupt:
        logger.info(f"[Worker {worker_id}] Interrupted")
    except Exception as e:
        logger.error(f"[Worker {worker_id}] Fatal error: {e}")
