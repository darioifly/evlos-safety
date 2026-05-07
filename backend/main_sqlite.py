"""
FastAPI Main Application - SQLite Version
Reads data from SQLite database written by separate video_worker.py process
This process ONLY handles HTTP/WebSocket requests - NO video processing!
"""
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from config import settings
from utils.logger import logger
from utils.screenshot import cleanup_screenshot_dir
from database import db
from services.nx_witness import NxWitnessClient
from services.video_worker_manager import VideoWorkerManager
from routers import evlos, presets
from integrations.evlos_client import evlos_client

# WebSocket check interval for real-time surveillance (100ms = 0.1s)
WEBSOCKET_CHECK_INTERVAL = 0.1  # Very fast for real-time alerts!

# Global NxWitness client and video worker manager
nx_client = None
worker_manager = None

# Process start time (monotonic). Used by /api/health/details and snapshot age.
app_started_at: float = time.monotonic()


# F-001: shared camera-status snapshot, refreshed by ONE background task,
# read by all connected WebSocket clients. Replaces per-client NxWitness polling.
class CameraStatusSnapshot:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.cameras: dict = {}
        self.last_updated: float = 0.0  # time.monotonic()
        self.last_nx_latency_ms: Optional[float] = None
        self.last_error: Optional[str] = None


camera_snapshot = CameraStatusSnapshot()


async def _refresh_camera_snapshot_once() -> None:
    """Perform ONE refresh of the shared camera snapshot.

    Called from a background loop and from tests.
    """
    t0 = time.monotonic()
    try:
        nx_cameras = await asyncio.to_thread(nx_client.get_cameras)
        nx_latency_ms = (time.monotonic() - t0) * 1000.0

        db_cameras = db.get_all_camera_status()
        db_cameras_map = {cam['camera_id']: cam for cam in db_cameras}

        merged: dict = {}
        for nx_cam in nx_cameras:
            cam_id = nx_cam['id']
            is_online = nx_cam.get('isOnline', False)
            db_cam = db_cameras_map.get(cam_id, {})

            last_update = db_cam.get('last_update')
            worker_analyzing = False
            if is_online and db_cam.get('enabled', False) and last_update:
                try:
                    last_update_dt = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
                    worker_analyzing = (datetime.now() - last_update_dt) < timedelta(seconds=10)
                except Exception:
                    worker_analyzing = False

            merged[cam_id] = {
                'camera_id': cam_id,
                'camera_name': nx_cam.get('name', cam_id),
                'online': 1 if is_online else 0,
                'stream_connected': 1 if worker_analyzing else 0,
                'worker_analyzing': worker_analyzing,
                'enabled': db_cam.get('enabled', 0),
                'person_count': db_cam.get('person_count', 0),
                'fps': db_cam.get('fps', 0),
                'avg_confidence': db_cam.get('avg_confidence', 0),
                'last_update': db_cam.get('last_update'),
                'last_detection': db_cam.get('last_detection'),
            }

        async with camera_snapshot.lock:
            camera_snapshot.cameras = merged
            camera_snapshot.last_updated = time.monotonic()
            camera_snapshot.last_nx_latency_ms = nx_latency_ms
            camera_snapshot.last_error = None
    except Exception as e:
        async with camera_snapshot.lock:
            camera_snapshot.last_error = f"{type(e).__name__}: {e}"
        logger.error(f"camera snapshot refresh failed: {e}")


async def _refresh_camera_snapshot_loop() -> None:
    """Background task: refresh the camera snapshot at the configured interval."""
    interval = settings.CAMERA_REFRESH_INTERVAL_SECONDS
    while True:
        try:
            await _refresh_camera_snapshot_once()
            logger.debug(
                f"[snapshot] refreshed: {len(camera_snapshot.cameras)} cameras "
                f"in {camera_snapshot.last_nx_latency_ms or 0:.0f}ms"
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"snapshot refresh loop error: {e}")
        await asyncio.sleep(interval)


# F-010: drainer state, exposed via /api/health/details.
evlos_drainer_last_run: Optional[str] = None
evlos_drainer_last_result: Optional[dict] = None

# Worker supervisor state, exposed via /api/health/details.
supervisor_last_run: Optional[str] = None
supervisor_last_result: Optional[dict] = None


async def _evlos_drainer_loop():
    """Periodic drainer for the EVLOS failed-alerts spool.

    Runs once at startup with a larger batch to begin clearing any backlog,
    then every EVLOS_DRAINER_INTERVAL_SECONDS with the smaller batch size.
    """
    global evlos_drainer_last_run, evlos_drainer_last_result

    # Startup pass.
    try:
        result = await asyncio.to_thread(evlos_client.drain_failed_alerts, 50)
        evlos_drainer_last_run = datetime.utcnow().isoformat()
        evlos_drainer_last_result = result
        logger.info(f"EVLOS drainer startup: {result}")
    except Exception:
        logger.exception("EVLOS drainer startup pass crashed")

    interval = settings.EVLOS_DRAINER_INTERVAL_SECONDS
    batch = settings.EVLOS_DRAINER_BATCH_SIZE
    while True:
        try:
            await asyncio.sleep(interval)
            result = await asyncio.to_thread(evlos_client.drain_failed_alerts, batch)
            evlos_drainer_last_run = datetime.utcnow().isoformat()
            evlos_drainer_last_result = result
            if result.get("attempted", 0) > 0:
                logger.info(f"EVLOS drainer pass: {result}")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("EVLOS drainer pass crashed; continuing")


async def _worker_supervisor_loop():
    """Periodic liveness check on managed CameraWorker threads.

    Detects dead threads, attempts one revival per pass, exposes
    last_run + last_result via /api/health/details.
    """
    global supervisor_last_run, supervisor_last_result

    interval = settings.WORKER_SUPERVISOR_INTERVAL_SECONDS
    while True:
        try:
            await asyncio.sleep(interval)
            if worker_manager is None:
                continue
            result = await asyncio.to_thread(worker_manager.supervise)
            supervisor_last_run = datetime.utcnow().isoformat()
            supervisor_last_result = result
            if result.get("revived") or result.get("still_dead"):
                logger.warning(f"Worker supervisor: {result}")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Worker supervisor pass crashed; continuing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    global nx_client, worker_manager

    logger.info("=" * 60)
    logger.info("FastAPI Server Starting (SQLite Mode with Dynamic Workers)...")
    logger.info("=" * 60)

    # Initialize database
    logger.info("Initializing database...")
    # Database auto-initializes in db_manager.py
    logger.info("✓ Database ready")

    # Initialize NxWitness client
    logger.info("Initializing NxWitness client...")
    nx_client = NxWitnessClient()
    logger.info("✓ NxWitness client ready")

    # Initialize video worker manager
    logger.info("Initializing video worker manager...")
    worker_manager = VideoWorkerManager()
    worker_manager.initialize()
    logger.info("✓ Video worker manager ready")

    # Start background task for periodic cleanup
    cleanup_task = asyncio.create_task(periodic_cleanup())

    # F-001: start background camera-status snapshot refresher
    snapshot_task = asyncio.create_task(_refresh_camera_snapshot_loop())

    # F-010: start EVLOS spool drainer (with startup backlog pass)
    evlos_drainer_task = asyncio.create_task(_evlos_drainer_loop())

    # Worker supervisor: detect + revive dead worker threads.
    supervisor_task = asyncio.create_task(_worker_supervisor_loop())

    logger.info("=" * 60)
    logger.info(f"Server started on http://{settings.HOST}:{settings.PORT}")
    logger.info("Video workers managed dynamically via API")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down...")
    cleanup_task.cancel()
    snapshot_task.cancel()
    evlos_drainer_task.cancel()
    supervisor_task.cancel()
    if worker_manager:
        worker_manager.stop_all()

    # Graceful shutdown of EVLOS client ThreadPoolExecutor
    logger.info("Shutting down EVLOS client...")
    evlos_client.shutdown()

    # Close persistent DB read connection (F-012)
    db.close()

    logger.info("FastAPI server stopped")


app = FastAPI(
    title="Person Detection System",
    description="Real-time person detection with YOLO and NX Witness",
    version="2.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(evlos.router)
app.include_router(presets.router)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "mode": "sqlite"}


@app.get("/api/health/details")
async def health_details():
    """Diagnostic endpoint: per-worker liveness, EVLOS pool, snapshot age,
    DB journal mode, screenshot directory sizes, alert backlog. (Phase 2)
    """
    backend_dir = Path(__file__).parent
    status_summary = "ok"
    reasons = []

    # --- DB ---
    db_info = {"db_path": str(backend_dir / "database" / "surveillance.db")}
    try:
        conn = db.get_connection()
        try:
            db_info["journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
    except Exception as e:
        db_info["journal_mode_error"] = str(e)
    try:
        db_info["size_bytes"] = Path(db_info["db_path"]).stat().st_size
    except OSError as e:
        db_info["size_bytes_error"] = str(e)

    # --- Workers ---
    workers_info = {"expected": 0, "alive": 0, "dead": [], "names": []}
    if worker_manager is not None:
        workers = list(worker_manager.workers.values())
        workers_info["expected"] = len(workers)
        for w in workers:
            cam_id = getattr(w, "camera_id", "?")
            workers_info["names"].append(cam_id)
            thread = getattr(w, "thread", None)
            if thread is not None and thread.is_alive():
                workers_info["alive"] += 1
            else:
                workers_info["dead"].append(cam_id)

    # Supervisor state.
    workers_info["supervisor_last_run"] = supervisor_last_run
    workers_info["supervisor_last_result"] = supervisor_last_result
    sup_interval = settings.WORKER_SUPERVISOR_INTERVAL_SECONDS

    # Degraded if the supervisor itself stopped running.
    uptime_now = time.monotonic() - app_started_at
    if supervisor_last_run is None and uptime_now > 3 * sup_interval:
        status_summary = "degraded"
        reasons.append("worker supervisor never ran")
    elif supervisor_last_run is not None:
        try:
            sup_age = (datetime.utcnow() - datetime.fromisoformat(supervisor_last_run)).total_seconds()
            if sup_age > 3 * sup_interval:
                status_summary = "degraded"
                reasons.append(f"worker supervisor stale ({sup_age:.0f}s)")
        except Exception:
            pass

    # Degraded if dead workers persist across a supervisor pass.
    if workers_info["dead"] and workers_info["expected"] > 0 and supervisor_last_run is not None:
        status_summary = "degraded"
        reasons.append(f"{len(workers_info['dead'])} dead worker(s)")
    if supervisor_last_result and supervisor_last_result.get("still_dead"):
        status_summary = "degraded"
        reasons.append(
            f"supervisor cannot revive: {supervisor_last_result['still_dead']}"
        )

    # --- Camera snapshot ---
    async with camera_snapshot.lock:
        snap_age = (
            time.monotonic() - camera_snapshot.last_updated
            if camera_snapshot.last_updated else None
        )
        snap_info = {
            "age_seconds": round(snap_age, 2) if snap_age is not None else None,
            "camera_count": len(camera_snapshot.cameras),
            "last_nx_latency_ms": (
                round(camera_snapshot.last_nx_latency_ms, 1)
                if camera_snapshot.last_nx_latency_ms is not None else None
            ),
            "last_error": camera_snapshot.last_error,
        }
    if snap_age is not None and snap_age > 30 and snap_info["last_error"] is None:
        status_summary = "degraded"
        reasons.append(f"snapshot stale ({snap_age:.0f}s)")
    if snap_info["last_error"]:
        status_summary = "degraded"
        reasons.append(f"snapshot error: {snap_info['last_error']}")

    # --- EVLOS ---
    evlos_info = {"enabled": bool(getattr(evlos_client, "enabled", False))}
    try:
        ex = evlos_client.executor
        evlos_info["pool_max"] = getattr(ex, "_max_workers", None)
        threads = getattr(ex, "_threads", None)
        if threads is not None:
            evlos_info["pool_active"] = sum(1 for t in threads if t.is_alive())
        wq = getattr(ex, "_work_queue", None)
        if wq is not None and hasattr(wq, "qsize"):
            evlos_info["queue_size"] = wq.qsize()
    except Exception as e:
        evlos_info["executor_error"] = str(e)
    try:
        failed_dir = evlos_client.failed_dir
        if failed_dir.exists():
            evlos_info["failed_dir_count"] = sum(
                1 for p in failed_dir.iterdir() if p.is_file()
            )
        else:
            evlos_info["failed_dir_count"] = 0
    except Exception as e:
        evlos_info["failed_dir_error"] = str(e)
    if evlos_info.get("failed_dir_count", 0) > 100:
        status_summary = "degraded"
        reasons.append(f"{evlos_info['failed_dir_count']} failed EVLOS alerts")

    # F-010: drainer state.
    evlos_info["drainer_last_run"] = evlos_drainer_last_run
    evlos_info["drainer_last_result"] = evlos_drainer_last_result
    uptime = time.monotonic() - app_started_at
    drainer_interval = settings.EVLOS_DRAINER_INTERVAL_SECONDS
    if evlos_drainer_last_run is None and uptime > drainer_interval:
        status_summary = "degraded"
        reasons.append("EVLOS drainer never ran")
    elif evlos_drainer_last_run is not None:
        try:
            last = datetime.fromisoformat(evlos_drainer_last_run)
            age = (datetime.utcnow() - last).total_seconds()
            if age > 2 * drainer_interval:
                status_summary = "degraded"
                reasons.append(f"EVLOS drainer stale ({age:.0f}s)")
        except Exception:
            pass

    # --- Alerts backlog ---
    try:
        alerts_backlog = len(db.get_unnotified_alerts())
    except Exception as e:
        alerts_backlog = -1
        reasons.append(f"alerts_backlog error: {e}")
        status_summary = "degraded"

    # --- Screenshot directories ---
    def _dir_stats(p: Path) -> dict:
        try:
            if not p.exists():
                return {"file_count": 0, "size_mb": 0.0}
            files = [f for f in p.iterdir() if f.is_file()]
            total = sum(f.stat().st_size for f in files)
            return {
                "file_count": len(files),
                "size_mb": round(total / (1024 * 1024), 2),
            }
        except Exception as e:
            return {"error": str(e)}

    screenshot_dirs = {
        "data/static/alerts": _dir_stats(backend_dir / "data" / "static" / "alerts"),
        "data/alert_screenshots": _dir_stats(backend_dir / settings.ALERT_SCREENSHOT_DIR),
    }

    return {
        "status": status_summary,
        "reasons": reasons,
        "uptime_seconds": round(time.monotonic() - app_started_at, 1),
        "db": db_info,
        "workers": workers_info,
        "camera_snapshot": snap_info,
        "evlos": evlos_info,
        "alerts_backlog_unnotified": alerts_backlog,
        "screenshot_dirs": screenshot_dirs,
    }


@app.get("/api/cameras")
async def get_cameras():
    """Get all cameras with current status"""
    cameras = db.get_all_camera_status()
    return cameras


@app.get("/api/cameras/status")
async def get_camera_status():
    """
    Get camera status combining real-time NxWitness data with database stats
    - Online status from NxWitness (real-time) - SOURCE OF TRUTH
    - Detection stats from database (person_count, fps, etc.)
    - Worker analyzing status based on last update timestamp
    - Only shows cameras that exist in NxWitness
    """
    try:
        # Get real-time camera list from NxWitness (SOURCE OF TRUTH)
        nx_cameras = await asyncio.to_thread(nx_client.get_cameras)

        # Get detection stats from database
        db_cameras = db.get_all_camera_status()
        db_cameras_map = {cam['camera_id']: cam for cam in db_cameras}

        # Build status dict using NxWitness as source of truth
        status_dict = {}
        for nx_cam in nx_cameras:
            cam_id = nx_cam['id']
            is_online = nx_cam['isOnline']

            # Get database stats if available
            db_cam = db_cameras_map.get(cam_id, {})

            # Determine if worker is analyzing:
            # - Camera must be online
            # - Camera must be enabled
            # - Last update must be recent (within last 10 seconds)
            last_update = db_cam.get('last_update')
            worker_analyzing = False
            if is_online and db_cam.get('enabled', False):
                if last_update:
                    try:
                        last_update_dt = datetime.strptime(last_update, '%Y-%m-%d %H:%M:%S')
                        time_since_update = datetime.now() - last_update_dt
                        worker_analyzing = time_since_update < timedelta(seconds=10)
                    except:
                        worker_analyzing = False

            # Get detection configuration
            detection_config = db.get_camera_detection_config(cam_id)

            # Build status object
            status_dict[cam_id] = {
                'camera_id': cam_id,
                'camera_name': nx_cam['name'],  # Use NxWitness name
                'online': 1 if is_online else 0,  # Real-time from NxWitness
                'stream_connected': 1 if worker_analyzing else 0,
                'worker_analyzing': worker_analyzing,
                'enabled': db_cam.get('enabled', 0),
                'person_count': db_cam.get('person_count', 0),
                'fps': db_cam.get('fps', 0),
                'avg_confidence': db_cam.get('avg_confidence', 0),
                'last_update': db_cam.get('last_update'),
                'last_detection': db_cam.get('last_detection'),
                'detection_mode': detection_config.get('detection_mode', 'intrusion') if detection_config else 'intrusion',
                'detection_preset_id': detection_config.get('detection_preset_id') if detection_config else None,
                'preset_name': detection_config.get('name') if detection_config else None,
            }

        return status_dict

    except Exception as e:
        logger.error(f"Error getting camera status: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Fallback to database-only data
        cameras = db.get_all_camera_status()
        status_dict = {cam['camera_id']: {**cam, 'online': 0, 'worker_analyzing': False} for cam in cameras}
        return status_dict


@app.get("/api/cameras/{camera_id}")
async def get_camera(camera_id: str):
    """Get specific camera details"""
    camera = db.get_camera_status(camera_id)
    if not camera:
        return {"error": "Camera not found"}, 404
    return camera


@app.post("/api/cameras/{camera_id}/toggle")
async def toggle_camera(camera_id: str):
    """Toggle camera enabled/disabled state and start/stop worker"""
    # Get current state from database
    camera = db.get_camera_status(camera_id)

    camera_name = None

    if not camera:
        # Camera not in database - get name from NxWitness and create entry
        try:
            nx_cameras = await asyncio.to_thread(nx_client.get_cameras)
            nx_cam = next((c for c in nx_cameras if c['id'] == camera_id), None)

            if not nx_cam:
                return {"error": "Camera not found in NxWitness"}, 404

            camera_name = nx_cam['name']

            # Create new camera entry with enabled=0 initially
            db.upsert_camera_status(
                camera_id=camera_id,
                camera_name=camera_name,
                online=True,
                stream_connected=False,
                person_count=0,
                fps=0.0
            )

            # Start worker (this will set enabled=True in database)
            logger.info(f"Starting worker for {camera_name} ({camera_id})")
            await asyncio.to_thread(worker_manager.start_worker, camera_id, camera_name)

            return {
                "status": "success",
                "camera_id": camera_id,
                "enabled": True,
                "message": f"Worker started for {camera_name}"
            }
        except Exception as e:
            logger.error(f"Error creating camera entry: {e}")
            return {"error": f"Failed to create camera: {str(e)}"}, 500

    # Camera exists - toggle state
    camera_name = camera['camera_name']
    current_state = camera['enabled']
    new_state = not current_state

    # Start or stop worker (worker manager will update enabled state in database)
    if new_state:
        logger.info(f"Starting worker for {camera_name} ({camera_id})")
        await asyncio.to_thread(worker_manager.start_worker, camera_id, camera_name)
        message = f"Worker started for {camera_name}"
    else:
        logger.info(f"Stopping worker for {camera_name} ({camera_id})")
        await asyncio.to_thread(worker_manager.stop_worker, camera_id)
        message = f"Worker stopped for {camera_name}"

    return {
        "status": "success",
        "camera_id": camera_id,
        "enabled": bool(new_state),
        "message": message
    }


@app.get("/api/detections/recent")
async def get_recent_detections(limit: int = 100):
    """Get recent detections"""
    conn = db.get_connection()
    try:
        cursor = conn.execute("""
            SELECT d.id, d.camera_id, c.camera_name, d.person_count,
                   d.avg_confidence, d.timestamp
            FROM detections d
            JOIN camera_status c ON d.camera_id = c.camera_id
            WHERE d.person_count > 0
            ORDER BY d.timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/api/alerts/recent")
async def get_recent_alerts(limit: int = 100):
    """Get recent alerts"""
    conn = db.get_connection()
    try:
        cursor = conn.execute("""
            SELECT id, camera_id, camera_name, person_count,
                   avg_confidence, full_image_path, cropped_image_path, timestamp
            FROM alerts
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.get("/api/alerts/stats")
async def get_alert_stats():
    """Get alert statistics"""
    conn = db.get_connection()
    try:
        # Total alerts
        total_cursor = conn.execute("SELECT COUNT(*) as total FROM alerts")
        total_alerts = total_cursor.fetchone()['total']

        # Alerts today
        today_cursor = conn.execute("""
            SELECT COUNT(*) as today FROM alerts
            WHERE DATE(timestamp) = DATE('now')
        """)
        alerts_today = today_cursor.fetchone()['today']

        # Alerts per camera
        camera_cursor = conn.execute("""
            SELECT camera_name, COUNT(*) as count
            FROM alerts
            GROUP BY camera_name
            ORDER BY count DESC
        """)
        alerts_per_camera = {row['camera_name']: row['count'] for row in camera_cursor.fetchall()}

        # Cameras with alerts
        cameras_cursor = conn.execute("SELECT COUNT(DISTINCT camera_id) as count FROM alerts")
        cameras_with_alerts = cameras_cursor.fetchone()['count']

        return {
            "total_alerts": total_alerts,
            "alerts_today": alerts_today,
            "alerts_per_camera": alerts_per_camera,
            "cameras_with_alerts": cameras_with_alerts
        }
    finally:
        conn.close()


@app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    """Delete a specific alert"""
    conn = db.get_connection()
    try:
        # Check if alert exists
        cursor = conn.execute("SELECT id FROM alerts WHERE id = ?", (alert_id,))
        alert = cursor.fetchone()
        if not alert:
            return {"error": "Alert not found"}, 404

        # Delete the alert
        conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        return {"status": "success", "message": f"Alert {alert_id} deleted"}
    finally:
        conn.close()


@app.delete("/api/alerts")
async def delete_all_alerts():
    """Delete all alerts"""
    conn = db.get_connection()
    try:
        # Count alerts before deleting
        cursor = conn.execute("SELECT COUNT(*) as count FROM alerts")
        count = cursor.fetchone()['count']

        # Delete all alerts
        conn.execute("DELETE FROM alerts")
        conn.commit()
        return {"status": "success", "message": f"Deleted {count} alerts"}
    finally:
        conn.close()


@app.get("/api/metrics")
async def get_metrics():
    """Get system metrics"""
    import psutil
    import torch
    from datetime import datetime, timedelta

    conn = db.get_connection()
    try:
        # Get camera FPS data
        cameras = db.get_all_camera_status()
        camera_fps = {cam['camera_name']: cam['fps'] for cam in cameras if cam['fps'] > 0}

        # Calculate average FPS
        avg_fps = sum(camera_fps.values()) / len(camera_fps) if camera_fps else 0

        # Get total detections
        detections_cursor = conn.execute("SELECT COUNT(*) as total FROM detections WHERE person_count > 0")
        total_detections = detections_cursor.fetchone()['total']

        # Get alerts today
        today_cursor = conn.execute("""
            SELECT COUNT(*) as today FROM alerts
            WHERE DATE(timestamp) = DATE('now')
        """)
        alerts_today = today_cursor.fetchone()['today']

        # Active cameras (with stream connected)
        active_cameras = sum(1 for cam in cameras if cam['stream_connected'])

        # GPU Usage
        gpu_usage = 0
        gpu_memory = 0
        gpu_memory_total = 0
        try:
            if torch.cuda.is_available():
                gpu_usage = torch.cuda.utilization()
                gpu_memory = torch.cuda.memory_allocated() / (1024**3)  # GB
                gpu_memory_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
        except:
            pass

        # System Uptime (using first camera's last_update as proxy)
        uptime_hours = 0
        try:
            # Find the oldest last_update from cameras with stream_connected
            active_cams = [c for c in cameras if c['stream_connected'] and c['last_update']]
            if active_cams:
                # Get the oldest update time
                oldest_update = min(c['last_update'] for c in active_cams)
                # Parse timestamp and calculate uptime
                update_time = datetime.strptime(oldest_update, "%Y-%m-%d %H:%M:%S")
                uptime_hours = (datetime.now() - update_time).total_seconds() / 3600
        except:
            pass

        return {
            "avgFps": avg_fps,
            "cameraFps": camera_fps,
            "totalDetections": total_detections,
            "alertsToday": alerts_today,
            "activeCameras": active_cameras,
            "gpuUsage": round(gpu_usage, 1),
            "gpuMemory": round(gpu_memory, 2),
            "gpuMemoryTotal": round(gpu_memory_total, 2),
            "uptime": round(uptime_hours, 2),
            "history": []   # Not tracked in SQLite mode
        }
    finally:
        conn.close()


@app.get("/api/detection/config")
async def get_detection_config():
    """Get current detection configuration"""
    import json
    config_path = Path(__file__).parent / "config.json"

    if config_path.exists():
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        # Return defaults
        return {
            "model": "yolov8n.pt",
            "confidence": 0.5,
            "device": "cuda:0",
            "minPersons": 1,
            "cooldown": 5,
            "batchSize": 4,
            "streamWidth": 640,
            "streamHeight": 480,
            "frameSampling": 10
        }


@app.post("/api/detection/config")
async def update_detection_config(config: dict):
    """Update detection configuration"""
    import json
    config_path = Path(__file__).parent / "config.json"

    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Configuration updated: {config}")

        # Reload config in video worker manager
        if worker_manager:
            worker_manager.reload_config()

        return {"status": "success", "message": "Configuration saved and applied to running workers."}
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/system/reload-presets")
async def reload_preset_configs():
    """
    Reload detection preset configurations for all running workers.
    Use this after updating preset settings (like ppe_confidence) to apply changes
    without restarting workers.
    """
    if worker_manager:
        worker_manager.reload_config()
        return {"status": "success", "message": "Preset configurations reloaded for all workers."}
    else:
        return {"status": "error", "message": "Worker manager not initialized"}


@app.get("/api/system/memory")
async def get_memory_status():
    """
    Get detailed memory usage for monitoring potential memory leaks.
    Returns process memory, GPU memory, thread counts, and resource usage over time.
    """
    import psutil
    import os
    import gc

    try:
        # Get current process
        process = psutil.Process(os.getpid())

        # Process memory info
        mem_info = process.memory_info()
        working_set_mb = mem_info.rss / (1024 * 1024)
        private_bytes_mb = mem_info.vms / (1024 * 1024)

        # Thread and handle count
        num_threads = process.num_threads()
        try:
            num_handles = process.num_handles() if hasattr(process, 'num_handles') else None
        except:
            num_handles = None

        # Open files count
        try:
            open_files = len(process.open_files())
        except:
            open_files = None

        # System-wide memory
        system_mem = psutil.virtual_memory()

        # GPU memory (if available)
        gpu_info = {}
        try:
            import torch
            if torch.cuda.is_available():
                gpu_info = {
                    "allocated_mb": round(torch.cuda.memory_allocated() / (1024 * 1024), 2),
                    "reserved_mb": round(torch.cuda.memory_reserved() / (1024 * 1024), 2),
                    "max_allocated_mb": round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2),
                    "total_mb": round(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 2),
                }
        except:
            pass

        # EVLOS ThreadPoolExecutor status
        evlos_executor_info = {}
        try:
            executor = evlos_client.executor
            evlos_executor_info = {
                "max_workers": executor._max_workers,
                "threads_active": len([t for t in executor._threads if t.is_alive()]) if hasattr(executor, '_threads') else None,
                "queue_size": executor._work_queue.qsize() if hasattr(executor, '_work_queue') else None,
            }
        except:
            pass

        # Worker manager info
        worker_info = {}
        if worker_manager:
            worker_info = {
                "active_workers": len(worker_manager.workers),
                "worker_cameras": list(worker_manager.workers.keys()),
            }

        # Database connection check
        db_info = {}
        try:
            db_path = Path(__file__).parent / "database" / "surveillance.db"
            if db_path.exists():
                db_info["size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)
        except:
            pass

        # Alert images folder
        alerts_dir = Path(__file__).parent / "data" / "static" / "alerts"
        alerts_info = {}
        try:
            if alerts_dir.exists():
                alert_files = list(alerts_dir.glob("*.jpg"))
                alerts_info = {
                    "file_count": len(alert_files),
                    "total_size_mb": round(sum(f.stat().st_size for f in alert_files) / (1024 * 1024), 2) if alert_files else 0,
                }
        except:
            pass

        # Python garbage collector stats
        gc_stats = {
            "collections": gc.get_count(),
            "objects_tracked": len(gc.get_objects()),
        }

        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "process": {
                "pid": os.getpid(),
                "working_set_mb": round(working_set_mb, 2),
                "private_bytes_mb": round(private_bytes_mb, 2),
                "num_threads": num_threads,
                "num_handles": num_handles,
                "open_files": open_files,
            },
            "system": {
                "total_mb": round(system_mem.total / (1024 * 1024), 2),
                "available_mb": round(system_mem.available / (1024 * 1024), 2),
                "percent_used": system_mem.percent,
            },
            "gpu": gpu_info,
            "evlos_executor": evlos_executor_info,
            "workers": worker_info,
            "database": db_info,
            "alert_images": alerts_info,
            "garbage_collector": gc_stats,
        }

    except Exception as e:
        logger.error(f"Error getting memory status: {e}")
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# ============================================================================
# WebSocket Endpoint - Real-Time Surveillance
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time alerts (F-001 refactored).

    Alerts: polled from SQLite at WEBSOCKET_CHECK_INTERVAL (cheap indexed SELECT).
    Camera status / metrics: read from the shared CameraStatusSnapshot (filled
    by ONE background task), pushed at settings.CAMERA_REFRESH_INTERVAL_SECONDS.
    No per-client NxWitness calls.
    """
    await websocket.accept()
    logger.info(f"🔴 WebSocket connected - Real-time surveillance active")

    last_camera_push = 0.0
    last_metrics_push = 0.0
    metrics_interval = 10.0

    try:
        while True:
            # Fast: alert push from DB (shared read connection, F-012).
            alerts = db.get_unnotified_alerts()
            if alerts:
                alert_ids = []
                for alert in alerts:
                    await websocket.send_json({
                        "type": "alert",
                        "data": {
                            "id": alert['id'],
                            "camera_id": alert['camera_id'],
                            "camera_name": alert['camera_name'],
                            "person_count": alert['person_count'],
                            "avg_confidence": alert['avg_confidence'],
                            "full_image_path": alert.get('full_image_path'),
                            "cropped_image_path": alert.get('cropped_image_path'),
                            "timestamp": alert['timestamp']
                        }
                    })
                    alert_ids.append(alert['id'])
                    logger.info(f"📤 Alert sent: {alert['person_count']} person(s) in {alert['camera_name']}")
                db.mark_alerts_notified(alert_ids)

            now = time.monotonic()

            # Slow: camera status from shared snapshot.
            if now - last_camera_push >= settings.CAMERA_REFRESH_INTERVAL_SECONDS:
                async with camera_snapshot.lock:
                    cameras_dict = dict(camera_snapshot.cameras)
                await websocket.send_json({
                    "type": "camera_status_update",
                    "data": cameras_dict,
                })
                last_camera_push = now

                # Slow: metrics every metrics_interval seconds, derived from the snapshot.
                if now - last_metrics_push >= metrics_interval:
                    cameras_list = list(cameras_dict.values())
                    camera_fps = {c['camera_name']: c['fps'] for c in cameras_list if c.get('fps', 0)}
                    avg_fps = sum(camera_fps.values()) / len(camera_fps) if camera_fps else 0
                    active_cameras = sum(1 for c in cameras_list if c.get('stream_connected'))

                    temp_conn = db.get_connection()
                    try:
                        alerts_today = temp_conn.execute("""
                            SELECT COUNT(*) as today FROM alerts
                            WHERE DATE(timestamp) = DATE('now')
                        """).fetchone()['today']
                    finally:
                        temp_conn.close()

                    await websocket.send_json({
                        "type": "metrics_update",
                        "data": {
                            "avgFps": avg_fps,
                            "cameraFps": camera_fps,
                            "alertsToday": alerts_today,
                            "activeCameras": active_cameras,
                        }
                    })
                    last_metrics_push = now

            await asyncio.sleep(WEBSOCKET_CHECK_INTERVAL)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


# ============================================================================
# Background Tasks
# ============================================================================

async def periodic_cleanup():
    """Periodic database + screenshot file cleanup (F-009)"""
    while True:
        try:
            # Cleanup old data every hour
            await asyncio.sleep(3600)
            logger.info("Running database cleanup...")
            db.cleanup_old_detections(days=7)
            db.cleanup_old_alerts(days=7)

            # F-009: also clean the actual JPEG files (DB rows alone don't
            # release disk). Run the filesystem walk in a thread.
            backend_dir = Path(__file__).parent
            deleted_a = await asyncio.to_thread(
                cleanup_screenshot_dir, backend_dir / "data" / "static" / "alerts", 7
            )
            deleted_b = await asyncio.to_thread(
                cleanup_screenshot_dir, backend_dir / settings.ALERT_SCREENSHOT_DIR, 7
            )
            if deleted_a or deleted_b:
                logger.info(
                    f"periodic_cleanup: deleted {deleted_a + deleted_b} old screenshot files"
                )

            logger.info("✓ Database cleanup complete")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Cleanup error: {e}")


# ============================================================================
# Static Files & Frontend Serving
# ============================================================================

# Serve alert screenshots
screenshots_dir = Path(settings.ALERT_SCREENSHOT_DIR)
if screenshots_dir.exists():
    app.mount("/screenshots", StaticFiles(directory=str(screenshots_dir)), name="screenshots")
    logger.info(f"Serving screenshots from {screenshots_dir}")
else:
    logger.warning(f"Screenshots directory not found at {screenshots_dir}")
    # Create directory if it doesn't exist
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/screenshots", StaticFiles(directory=str(screenshots_dir)), name="screenshots")
    logger.info(f"Created and serving screenshots from {screenshots_dir}")

# Serve static files
static_dir = Path(__file__).parent / "data" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    logger.info(f"Serving static files from {static_dir}")

# Serve frontend if built
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    logger.info(f"Serving React frontend from {frontend_dist}")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Don't intercept API, WebSocket, or static file routes
        if full_path.startswith(('api/', 'ws/', 'health', 'screenshots/', 'static/', 'assets/')):
            # Let FastAPI handle these routes
            return None

        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")
else:
    logger.warning(f"Frontend build not found at {frontend_dist}")
    logger.warning("Run 'cd frontend && npm run build' to create production build")


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    import logging

    # Custom logging config to silence WebSocket debug messages
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["loggers"]["uvicorn"]["level"] = "INFO"
    log_config["loggers"]["uvicorn.access"]["level"] = "WARNING"
    log_config["loggers"]["uvicorn.error"]["level"] = "INFO"

    # Add websockets loggers to suppress DEBUG messages
    log_config["loggers"]["websockets"] = {"level": "WARNING"}
    log_config["loggers"]["websockets.protocol"] = {"level": "WARNING"}
    log_config["loggers"]["websockets.server"] = {"level": "WARNING"}

    logger.info("Starting FastAPI server in SQLite mode...")
    logger.info("Make sure to run video_worker.py in a separate terminal!")

    uvicorn.run(
        "main_sqlite:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # No reload to avoid conflicts
        log_level="info",
        log_config=log_config  # Use custom logging config
    )
