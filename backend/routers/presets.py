"""
Detection Presets API Router
Manages detection mode presets (Intrusion and PPE)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from database import db
from utils.logger import logger

router = APIRouter(prefix="/api/presets", tags=["presets"])


# Pydantic models for request/response
class PresetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    mode: str  # 'intrusion' or 'ppe'
    intrusion_min_persons: Optional[int] = 1
    intrusion_confidence: Optional[float] = 0.5
    ppe_require_helmet: Optional[bool] = True
    ppe_require_vest: Optional[bool] = True
    ppe_confidence: Optional[float] = 0.6
    cooldown_seconds: Optional[int] = 5


class PresetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    mode: Optional[str] = None
    intrusion_min_persons: Optional[int] = None
    intrusion_confidence: Optional[float] = None
    ppe_require_helmet: Optional[bool] = None
    ppe_require_vest: Optional[bool] = None
    ppe_confidence: Optional[float] = None
    cooldown_seconds: Optional[int] = None


@router.get("")
async def get_all_presets():
    """
    Get all detection presets

    Returns:
        List of all available detection presets
    """
    try:
        presets = db.get_all_presets()
        return {"presets": presets}
    except Exception as e:
        logger.error(f"Error fetching presets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{preset_id}")
async def get_preset(preset_id: int):
    """
    Get specific preset by ID

    Args:
        preset_id: Preset identifier

    Returns:
        Preset details
    """
    try:
        preset = db.get_preset(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
        return preset
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching preset {preset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_preset(preset: PresetCreate):
    """
    Create new detection preset

    Args:
        preset: Preset configuration

    Returns:
        Created preset with ID
    """
    try:
        # Validate mode
        if preset.mode not in ['intrusion', 'ppe']:
            raise HTTPException(status_code=400, detail="Mode must be 'intrusion' or 'ppe'")

        # Create preset
        preset_id = db.create_preset(
            name=preset.name,
            description=preset.description or "",
            mode=preset.mode,
            intrusion_min_persons=preset.intrusion_min_persons,
            intrusion_confidence=preset.intrusion_confidence,
            ppe_require_helmet=preset.ppe_require_helmet,
            ppe_require_vest=preset.ppe_require_vest,
            ppe_confidence=preset.ppe_confidence,
            cooldown_seconds=preset.cooldown_seconds
        )

        # Fetch and return created preset
        created_preset = db.get_preset(preset_id)
        return {
            "message": "Preset created successfully",
            "preset": created_preset
        }
    except Exception as e:
        logger.error(f"Error creating preset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{preset_id}")
async def update_preset(preset_id: int, preset: PresetUpdate):
    """
    Update existing preset

    Args:
        preset_id: Preset identifier
        preset: Updated preset configuration

    Returns:
        Updated preset
    """
    try:
        # Check if preset exists
        existing = db.get_preset(preset_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")

        # Validate mode if provided
        if preset.mode and preset.mode not in ['intrusion', 'ppe']:
            raise HTTPException(status_code=400, detail="Mode must be 'intrusion' or 'ppe'")

        # Build update dict with only provided fields
        update_data = {}
        for field, value in preset.dict(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value

        # Update preset
        success = db.update_preset(preset_id, **update_data)

        if not success:
            raise HTTPException(status_code=400, detail="No fields to update")

        # Fetch and return updated preset
        updated_preset = db.get_preset(preset_id)
        return {
            "message": "Preset updated successfully",
            "preset": updated_preset
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating preset {preset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{preset_id}")
async def delete_preset(preset_id: int):
    """
    Delete preset (only if not in use by any camera)

    Args:
        preset_id: Preset identifier

    Returns:
        Success message
    """
    try:
        # Check if preset exists
        preset = db.get_preset(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")

        # Try to delete
        success = db.delete_preset(preset_id)

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete preset: currently in use by one or more cameras"
            )

        return {
            "message": f"Preset '{preset['name']}' deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting preset {preset_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/camera/{camera_id}/set-preset")
async def set_camera_preset(camera_id: str, preset_id: int):
    """
    Set detection preset for a specific camera

    Args:
        camera_id: Camera identifier
        preset_id: Preset to apply

    Returns:
        Success message with preset details
    """
    try:
        import main_sqlite

        # Check if preset exists
        preset = db.get_preset(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")

        # Set camera detection mode and preset
        db.set_camera_detection_mode(camera_id, preset['mode'], preset_id)

        # Restart worker if it's running to apply new configuration
        worker_manager = main_sqlite.worker_manager
        if worker_manager and camera_id in worker_manager.workers:
            camera_info = db.get_camera_status(camera_id)
            if camera_info:
                logger.info(f"Restarting worker for camera {camera_id} to apply new preset")
                worker_manager.stop_worker(camera_id)
                worker_manager.start_worker(camera_id, camera_info.get('camera_name', camera_id))

        return {
            "message": f"Camera {camera_id} set to preset '{preset['name']}'",
            "mode": preset['mode'],
            "preset": preset
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting preset for camera {camera_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/camera/{camera_id}/config")
async def get_camera_detection_config(camera_id: str):
    """
    Get current detection configuration for a camera

    Args:
        camera_id: Camera identifier

    Returns:
        Detection configuration with preset details
    """
    try:
        config = db.get_camera_detection_config(camera_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")

        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching config for camera {camera_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
