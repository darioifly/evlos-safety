"""
Main FastAPI Application
"""
import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from config import settings
from utils.logger import logger
from utils.metrics import metrics
from services.nx_witness import nx_client
from services.stream_manager import StreamManager
from services.alert_manager import alert_manager
from database.db_manager import DatabaseManager
from routers import cameras, detection, alerts, evlos, presets


# WebSocket connection manager
class ConnectionManager:
    """Manage WebSocket connections"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return

        disconnected = set()

        for connection in self.active_connections:
            try:
                # Use wait_for with timeout to avoid hanging on stuck connections
                await asyncio.wait_for(connection.send_json(message), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending to WebSocket client, marking for disconnection")
                disconnected.add(connection)
            except Exception as e:
                logger.warning(f"Error sending to WebSocket client: {e}")
                disconnected.add(connection)

        # Remove disconnected clients
        if disconnected:
            self.active_connections -= disconnected
            logger.info(f"Removed {len(disconnected)} stale WebSocket connections")


# Global instances
websocket_manager = ConnectionManager()
stream_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("=" * 60)
    logger.info("Person Detection System Starting...")
    logger.info("=" * 60)

    # Test NxWitness connection
    # IMPORTANT: Run in thread to avoid blocking the event loop
    logger.info("Testing NxWitness connection...")
    if await asyncio.to_thread(nx_client.test_connection):
        logger.info("✓ NxWitness connection successful")
    else:
        logger.warning("✗ NxWitness connection failed - will retry during runtime")

    # Get cameras
    logger.info("Fetching cameras from NxWitness...")
    all_cameras = await asyncio.to_thread(nx_client.get_cameras)
    logger.info(f"Found {len(all_cameras)} cameras")

    # Use all online cameras (or all cameras if IGNORE_CAMERA_STATUS is True)
    cameras = []
    for cam in all_cameras:
        # If IGNORE_CAMERA_STATUS is True, use all cameras regardless of status
        if settings.IGNORE_CAMERA_STATUS or cam.get('isOnline', False):
            cameras.append(cam)
            status = "online" if cam.get('isOnline', False) else "offline"
            logger.info(f"Adding camera: {cam.get('name', cam['id'])} ({status})")

    if not cameras:
        # If still no cameras, log error
        logger.error("No cameras available!")
        cameras = []
    else:
        logger.info(f"Total cameras to monitor: {len(cameras)}")

    # Set camera names in alert_manager for proper alert logging
    camera_names = {cam['id']: cam.get('name', cam['id']) for cam in cameras}
    alert_manager.set_camera_metadata(camera_names=camera_names)
    logger.info(f"Camera names configured in AlertManager: {len(camera_names)} cameras")

    # Initialize stream manager with event loop
    global stream_manager
    event_loop = asyncio.get_running_loop()
    stream_manager = StreamManager(websocket_manager, event_loop)

    # Background tasks for metrics and camera status
    # TEMPORARY: Both tasks disabled to debug HTTP request blocking
    # asyncio.create_task(broadcast_metrics())
    # asyncio.create_task(refresh_camera_status())

    # Initialize StreamManager with camera data (workers disabled by default)
    # Workers can be manually enabled per camera via /api/cameras/{id}/toggle endpoint
    logger.info("Initializing StreamManager with camera data (workers disabled)")
    async def init_stream_manager():
        """Initialize stream manager asynchronously"""
        if cameras:
            logger.info("Initializing camera data in StreamManager...")
            await asyncio.to_thread(stream_manager.start, cameras, False)  # auto_start_workers=False
            logger.info("✓ StreamManager initialized - workers disabled by default")

            # Restore previously enabled cameras from database
            try:
                db = DatabaseManager()
                enabled_cameras = db.get_enabled_cameras()
                if enabled_cameras:
                    logger.info(f"Restoring {len(enabled_cameras)} previously enabled camera(s)...")
                    for cam in enabled_cameras:
                        camera_id = cam.get('camera_id')
                        camera_name = cam.get('camera_name', camera_id)
                        logger.info(f"  Re-enabling camera: {camera_name} ({camera_id})")
                        try:
                            stream_manager.toggle_camera(camera_id)
                        except Exception as e:
                            logger.error(f"  Failed to re-enable camera {camera_name}: {e}")
                    logger.info(f"✓ Restored {len(enabled_cameras)} camera worker(s)")
                else:
                    logger.info("No previously enabled cameras to restore")
            except Exception as e:
                logger.error(f"Error restoring enabled cameras: {e}")
        else:
            logger.warning("No cameras found - stream manager not initialized")

    asyncio.create_task(init_stream_manager())

    logger.info("=" * 60)
    logger.info(f"Server started on http://{settings.HOST}:{settings.PORT}")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down...")
    if stream_manager:
        stream_manager.stop()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Person Detection System",
    description="YOLOv8-based person detection for NxWitness cameras",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(cameras.router)
app.include_router(detection.router)
app.include_router(alerts.router)
app.include_router(evlos.router)
app.include_router(presets.router)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "uptime_hours": metrics.get_uptime()
    }


# Test endpoint
@app.get("/test")
async def test_endpoint():
    """Test endpoint to verify server is responding"""
    logger.info("Test endpoint called")
    return {
        "message": "Server is working!",
        "websocket_endpoint": "/ws",
        "backend_port": settings.PORT
    }


# Worker restart endpoint
@app.post("/api/worker/restart")
async def restart_worker():
    """
    Restart all video workers

    Returns:
        Success message
    """
    try:
        global stream_manager

        if stream_manager is None:
            raise HTTPException(status_code=503, detail="Stream manager not initialized")

        logger.info("Restarting all video workers...")

        # Get current cameras before stopping
        import asyncio
        cameras = await asyncio.to_thread(nx_client.get_cameras)

        # Filter to online cameras (or all if IGNORE_CAMERA_STATUS is True)
        active_cameras = []
        for cam in cameras:
            if settings.IGNORE_CAMERA_STATUS or cam.get('isOnline', False):
                active_cameras.append(cam)

        # Stop current stream manager
        stream_manager.stop()

        # Create new stream manager
        event_loop = asyncio.get_running_loop()
        stream_manager = StreamManager(websocket_manager, event_loop)

        # Update camera names in alert_manager
        camera_names = {cam['id']: cam.get('name', cam['id']) for cam in active_cameras}
        alert_manager.set_camera_metadata(camera_names=camera_names)

        # Start with workers disabled (user can enable per camera)
        await asyncio.to_thread(stream_manager.start, active_cameras, False)

        logger.info(f"Workers restarted successfully with {len(active_cameras)} cameras")

        return {
            "message": "Video workers restarted successfully",
            "cameras": len(active_cameras)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restarting workers: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# Metrics endpoint
@app.get("/api/metrics")
async def get_metrics():
    """Get system metrics"""
    try:
        summary = metrics.get_summary()

        # Add GPU usage if available
        try:
            import torch
            if torch.cuda.is_available():
                gpu_memory = torch.cuda.memory_allocated(0) / 1024**3  # GB
                gpu_memory_total = torch.cuda.get_device_properties(0).total_memory / 1024**3
                summary['gpuUsage'] = round((gpu_memory / gpu_memory_total) * 100, 1)
                summary['gpuMemory'] = round(gpu_memory, 2)
                summary['gpuMemoryTotal'] = round(gpu_memory_total, 2)
            else:
                summary['gpuUsage'] = 0
        except Exception as e:
            logger.debug(f"Error getting GPU metrics: {e}")
            summary['gpuUsage'] = 0

        return summary

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    logger.info(f"WebSocket connection attempt from: {websocket.client}")

    try:
        await websocket_manager.connect(websocket)
        logger.info("WebSocket connection accepted and added to manager")

        # Send initial status
        if stream_manager:
            initial_data = stream_manager.get_status()
            logger.debug(f"Sending initial status with {len(initial_data)} cameras")
            await websocket.send_json({
                'type': 'initial_status',
                'data': initial_data
            })
            logger.info("Initial status sent successfully")

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data}")
            # Echo back (can be used for ping/pong)
            await websocket.send_json({'type': 'pong', 'data': data})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected normally")
        websocket_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"WebSocket traceback: {traceback.format_exc()}")
        websocket_manager.disconnect(websocket)


async def broadcast_metrics():
    """Background task to broadcast metrics periodically"""
    while True:
        try:
            await asyncio.sleep(5)  # Broadcast every 5 seconds

            # Get camera status
            status = {}
            if stream_manager:
                status = stream_manager.get_status()

            # If no worker status (workers disabled), get from NX Witness API
            if not status:
                cameras = await asyncio.to_thread(nx_client.get_cameras)
                for cam in cameras:
                    cam_id = cam.get('id')
                    status[cam_id] = {
                        'camera_id': cam_id,
                        'camera_name': cam.get('name', 'Unknown'),
                        'online': cam.get('isOnline', False),
                        'stream_connected': False,
                        'person_count': 0,
                        'fps': 0,
                        'avg_confidence': 0,
                        'last_detection': None,
                        'enabled': False
                    }

            # Broadcast camera status
            await websocket_manager.broadcast({
                'type': 'camera_status_update',
                'data': status
            })

            # Get metrics
            summary = metrics.get_summary()

            # Broadcast metrics
            await websocket_manager.broadcast({
                'type': 'metrics_update',
                'data': summary
            })

        except Exception as e:
            logger.error(f"Error in metrics broadcast: {e}")
            await asyncio.sleep(5)


async def refresh_camera_status():
    """Background task to refresh camera API status periodically"""
    while True:
        try:
            await asyncio.sleep(30)  # Refresh every 30 seconds

            if stream_manager:
                # Fetch latest camera status from NX Witness API
                # IMPORTANT: Run in thread to avoid blocking the event loop
                logger.debug("Refreshing camera API status from NX Witness...")
                cameras = await asyncio.to_thread(nx_client.get_cameras)

                if cameras:
                    # Update stream manager with latest API status
                    stream_manager.refresh_api_status(cameras)
                    logger.debug(f"Refreshed API status for {len(cameras)} cameras")
                else:
                    logger.warning("Failed to fetch cameras for status refresh")

        except Exception as e:
            logger.error(f"Error refreshing camera status: {e}")
            await asyncio.sleep(30)


# Serve screenshots directory
screenshots_dir = settings.ALERT_SCREENSHOT_DIR
if Path(screenshots_dir).exists():
    app.mount("/screenshots", StaticFiles(directory=str(screenshots_dir)), name="screenshots")
    logger.info(f"Serving screenshots from {screenshots_dir}")
else:
    logger.warning(f"Screenshots directory not found at {screenshots_dir}")

# Serve data directory for /static/alerts paths (backward compatibility)
data_dir = Path(screenshots_dir).parent
static_dir = data_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static_files")
    logger.info(f"Serving static files from {static_dir}")
else:
    logger.warning(f"Static directory not found at {static_dir}")

# Serve React frontend (must be last)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

if frontend_dist.exists():
    # Serve static files
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    # Serve index.html for all other routes (SPA)
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React frontend"""
        from fastapi.responses import FileResponse

        # If path doesn't start with /api or /ws or /screenshots or /static, serve index.html
        if not full_path.startswith(('api/', 'ws/', 'health', 'screenshots/', 'static/')):
            return FileResponse(frontend_dist / "index.html")

    logger.info(f"Serving React frontend from {frontend_dist}")
else:
    logger.warning(f"Frontend build not found at {frontend_dist}")
    logger.warning("Run 'cd frontend && npm run build' to create production build")


if __name__ == "__main__":
    import uvicorn
    import os
    import logging

    # Suppress ALL debug logging from websockets and uvicorn BEFORE starting
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("websockets.protocol").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.WARNING)
    logging.getLogger("websockets.client").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Custom logging config to silence WebSocket debug messages
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["loggers"]["uvicorn"]["level"] = "INFO"
    log_config["loggers"]["uvicorn.access"]["level"] = "WARNING"
    log_config["loggers"]["uvicorn.error"]["level"] = "INFO"

    # Add websockets loggers to suppress DEBUG messages
    log_config["loggers"]["websockets"] = {"level": "WARNING", "handlers": [], "propagate": False}
    log_config["loggers"]["websockets.protocol"] = {"level": "WARNING", "handlers": [], "propagate": False}
    log_config["loggers"]["websockets.server"] = {"level": "WARNING", "handlers": [], "propagate": False}
    log_config["loggers"]["websockets.client"] = {"level": "WARNING", "handlers": [], "propagate": False}

    # Signal handler for graceful shutdown
    def signal_handler(sig, frame):
        """Handle Ctrl+C to gracefully shutdown threads"""
        logger.info("\n🛑 Received shutdown signal (Ctrl+C)")
        logger.info("Stopping stream manager...")
        if stream_manager:
            stream_manager.stop()
        logger.info("Shutdown complete. Exiting...")
        sys.exit(0)

    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # IMPORTANT: Reload is DISABLED because it conflicts with threading
    # When uvicorn reloads, it doesn't properly stop background threads,
    # causing multiple instances and deadlocks. Restart manually instead.

    logger.info("Press Ctrl+C to stop the server")

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # DISABLED to prevent thread conflicts
        log_level="info",  # Force INFO level (not DEBUG)
        log_config=log_config  # Use custom logging config
    )
