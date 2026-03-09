"""
Camera API Router
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict

from services.nx_witness import nx_client
from utils.logger import logger

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=List[Dict])
async def get_cameras():
    """
    Get list of all cameras from NxWitness

    Returns:
        List of camera objects with id, name, and online status
    """
    try:
        # Run in thread to avoid blocking the event loop
        import asyncio
        cameras = await asyncio.to_thread(nx_client.get_cameras)
        return cameras
    except Exception as e:
        logger.error(f"Error fetching cameras: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=Dict)
async def get_camera_status():
    """
    Get real-time status of all cameras

    Returns:
        Dictionary mapping camera_id to status info
    """
    try:
        from main import stream_manager
        from database.db_manager import DatabaseManager
        import asyncio

        # Get detection config from database for all cameras
        db = DatabaseManager()

        # If stream_manager exists, get worker status
        if stream_manager is not None:
            status = stream_manager.get_status()
            if status:
                # Enrich status with detection preset info from database
                for camera_id, cam_status in status.items():
                    detection_config = db.get_camera_detection_config(camera_id)
                    if detection_config:
                        cam_status['detection_mode'] = detection_config.get('detection_mode')
                        cam_status['detection_preset_id'] = detection_config.get('detection_preset_id')
                        cam_status['preset_name'] = detection_config.get('preset_name')
                return status

        # Fallback: Get camera list from NX Witness API (for when workers are disabled)
        cameras = await asyncio.to_thread(nx_client.get_cameras)

        # Format cameras as status dict for frontend compatibility
        status_dict = {}
        for cam in cameras:
            cam_id = cam.get('id')
            detection_config = db.get_camera_detection_config(cam_id)
            status_dict[cam_id] = {
                'camera_id': cam_id,
                'camera_name': cam.get('name', 'Unknown'),
                'online': cam.get('isOnline', False),
                'stream_connected': False,  # Workers disabled
                'person_count': 0,
                'fps': 0,
                'avg_confidence': 0,
                'last_detection': None,
                'enabled': False,  # Workers disabled
                'detection_mode': detection_config.get('detection_mode') if detection_config else None,
                'detection_preset_id': detection_config.get('detection_preset_id') if detection_config else None,
                'preset_name': detection_config.get('preset_name') if detection_config else None
            }

        return status_dict

    except Exception as e:
        logger.error(f"Error getting camera status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{camera_id}", response_model=Dict)
async def get_camera_detail(camera_id: str):
    """
    Get detailed status for a specific camera

    Args:
        camera_id: Camera identifier

    Returns:
        Camera status dictionary
    """
    try:
        from main import stream_manager

        if stream_manager is None:
            raise HTTPException(status_code=503, detail="Stream manager not initialized")

        status = stream_manager.get_status()

        if camera_id not in status:
            raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

        return status[camera_id]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting camera detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{camera_id}/toggle")
async def toggle_camera(camera_id: str):
    """
    Toggle worker for a specific camera (start/stop)

    Args:
        camera_id: Camera identifier

    Returns:
        Success message with new status
    """
    try:
        from main import stream_manager
        from database.db_manager import DatabaseManager

        if stream_manager is None:
            raise HTTPException(status_code=503, detail="Stream manager not initialized")

        # Toggle the camera worker
        new_status = stream_manager.toggle_camera(camera_id)
        logger.info(f"Toggled camera {camera_id} worker: {new_status}")

        # Persist enabled state to database
        db = DatabaseManager()
        db.set_camera_enabled(camera_id, new_status)

        return {
            "message": f"Camera {camera_id} worker {'started' if new_status else 'stopped'}",
            "enabled": new_status
        }
    except Exception as e:
        logger.error(f"Error toggling camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{camera_id}/restart")
async def restart_camera(camera_id: str):
    """
    Restart stream for a specific camera

    Args:
        camera_id: Camera identifier

    Returns:
        Success message
    """
    try:
        from main import stream_manager

        if stream_manager is None:
            raise HTTPException(status_code=503, detail="Stream manager not initialized")

        stream_manager.restart_camera(camera_id)
        logger.info(f"Restarted camera stream: {camera_id}")

        return {"message": f"Camera {camera_id} restarted successfully"}
    except Exception as e:
        logger.error(f"Error restarting camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))
