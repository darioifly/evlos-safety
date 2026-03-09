"""
Worker Pool Manager for Multi-Process YOLO Detection
Manages a pool of worker processes that run YOLO inference in parallel
"""
import multiprocessing as mp
from typing import List, Dict
import threading
import time

from config import settings
from utils.logger import logger
from services.detection_worker import worker_process


class WorkerPool:
    """
    Manages a pool of YOLO detection worker processes.
    Workers run in separate processes to avoid GIL blocking.
    """

    def __init__(self, num_workers: int = None):
        """
        Initialize worker pool.

        Args:
            num_workers: Number of worker processes (default: from settings)
        """
        self.num_workers = num_workers or settings.CONSUMER_THREADS
        self.input_queue = mp.Queue(maxsize=settings.FRAME_QUEUE_SIZE)
        self.output_queue = mp.Queue(maxsize=settings.FRAME_QUEUE_SIZE)
        self.workers: List[mp.Process] = []
        self.result_handler_thread = None
        self.running = False
        self.callbacks = []

    def start(self):
        """Start worker processes and result handler"""
        if self.running:
            logger.warning("WorkerPool already running")
            return

        self.running = True

        logger.info(f"Starting WorkerPool with {self.num_workers} workers")

        # Start worker processes
        for i in range(self.num_workers):
            process = mp.Process(
                target=worker_process,
                args=(i, self.input_queue, self.output_queue),
                daemon=True,
                name=f"YOLOWorker-{i}"
            )
            process.start()
            self.workers.append(process)
            logger.info(f"Started worker process {i} (PID: {process.pid})")

        # Start result handler thread
        self.result_handler_thread = threading.Thread(
            target=self._handle_results,
            daemon=True,
            name="ResultHandler"
        )
        self.result_handler_thread.start()

        logger.info("WorkerPool started successfully")

    def stop(self):
        """Stop worker processes and result handler"""
        if not self.running:
            return

        logger.info("Stopping WorkerPool...")
        self.running = False

        # Send poison pills to workers
        for _ in range(self.num_workers):
            try:
                self.input_queue.put(None, timeout=1.0)
            except:
                pass

        # Wait for workers to finish (with timeout)
        for worker in self.workers:
            worker.join(timeout=2.0)
            if worker.is_alive():
                logger.warning(f"Worker {worker.name} did not stop gracefully, terminating")
                worker.terminate()
                worker.join(timeout=1.0)

        # Clear queues
        self._clear_queue(self.input_queue)
        self._clear_queue(self.output_queue)

        self.workers.clear()

        logger.info("WorkerPool stopped")

    def submit_batch(self, batch: List[Dict]):
        """
        Submit a batch of frames for processing.

        Args:
            batch: List of dicts with 'frame' (numpy array) and 'camera_id' (str)
        """
        if not self.running:
            logger.warning("WorkerPool not running, cannot submit batch")
            return

        try:
            # Non-blocking put with timeout
            self.input_queue.put(batch, timeout=0.1)
        except:
            logger.warning("Input queue full, dropping batch")

    def register_callback(self, callback):
        """
        Register a callback function to handle detection results.

        Args:
            callback: Function that takes List[Dict] of detection results
        """
        self.callbacks.append(callback)

    def _handle_results(self):
        """
        Result handler thread - retrieves results from workers and calls callbacks.
        Runs in a separate thread in the main process.
        """
        logger.info("Result handler started")

        while self.running:
            try:
                # Get results from workers
                try:
                    results = self.output_queue.get(timeout=0.1)
                except:
                    continue

                # Call all registered callbacks
                for callback in self.callbacks:
                    try:
                        callback(results)
                    except Exception as e:
                        logger.error(f"Error in result callback: {e}")

            except Exception as e:
                logger.error(f"Error in result handler: {e}")
                time.sleep(0.1)

        logger.info("Result handler stopped")

    def _clear_queue(self, queue: mp.Queue):
        """Clear all items from a queue"""
        try:
            while not queue.empty():
                queue.get_nowait()
        except:
            pass

    def get_stats(self) -> Dict:
        """Get worker pool statistics"""
        return {
            'num_workers': self.num_workers,
            'running': self.running,
            'input_queue_size': self.input_queue.qsize() if self.running else 0,
            'output_queue_size': self.output_queue.qsize() if self.running else 0,
            'workers_alive': sum(1 for w in self.workers if w.is_alive())
        }
