"""
Detection Configuration API Router
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from config import settings
from services.detector import detector
from services.alert_manager import alert_manager
from utils.logger import logger

router = APIRouter(prefix="/api/detection", tags=["detection"])


class DetectionConfig(BaseModel):
    """Detection configuration model"""
    model: Optional[str] = Field(None, description="YOLO model path")
    confidence: Optional[float] = Field(None, ge=0.1, le=0.95, description="Confidence threshold")
    device: Optional[str] = Field(None, description="Device to use (cuda:0 or cpu)")
    minPersons: Optional[int] = Field(None, ge=1, le=10, description="Minimum persons for alert")
    cooldown: Optional[int] = Field(None, ge=1, le=60, description="Alert cooldown in seconds")
    batchSize: Optional[int] = Field(None, ge=1, le=16, description="Batch size for processing")
    streamWidth: Optional[int] = Field(None, ge=320, le=1920, description="Stream width")
    streamHeight: Optional[int] = Field(None, ge=240, le=1080, description="Stream height")
    frameSampling: Optional[int] = Field(None, ge=1, le=30, description="Frame sampling rate")

    class Config:
        extra = "ignore"  # Ignore extra fields not in model


@router.get("/config")
async def get_config():
    """
    Get current detection configuration

    Returns:
        Current configuration settings
    """
    try:
        return {
            "model": settings.YOLO_MODEL,
            "confidence": settings.CONFIDENCE_THRESHOLD,
            "device": settings.DEVICE,
            "minPersons": settings.MIN_PERSONS_FOR_ALERT,
            "cooldown": settings.ALERT_COOLDOWN_SECONDS,
            "batchSize": settings.BATCH_SIZE,
            "streamWidth": settings.STREAM_WIDTH,
            "streamHeight": settings.STREAM_HEIGHT,
            "frameSampling": settings.FRAME_SAMPLING
        }
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(config: DetectionConfig):
    """
    Update detection configuration

    Args:
        config: New configuration settings

    Returns:
        Updated configuration
    """
    try:
        updated_fields = []

        # Update YOLO model
        if config.model and config.model != settings.YOLO_MODEL:
            settings.YOLO_MODEL = config.model
            detector.reload_model(model_path=config.model)
            updated_fields.append("model")
            logger.info(f"Updated YOLO model to {config.model}")

        # Update confidence threshold
        if config.confidence is not None and config.confidence != settings.CONFIDENCE_THRESHOLD:
            settings.CONFIDENCE_THRESHOLD = config.confidence
            detector.update_confidence(config.confidence)
            updated_fields.append("confidence")
            logger.info(f"Updated confidence threshold to {config.confidence}")

        # Update device
        if config.device and config.device != settings.DEVICE:
            if config.device not in ['cuda:0', 'cpu', 'cuda']:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid device. Choose 'cuda:0' or 'cpu'"
                )
            settings.DEVICE = config.device
            detector.reload_model(device=config.device)
            updated_fields.append("device")
            logger.info(f"Updated device to {config.device}")

        # Update minimum persons
        if config.minPersons is not None and config.minPersons != settings.MIN_PERSONS_FOR_ALERT:
            settings.MIN_PERSONS_FOR_ALERT = config.minPersons
            alert_manager.update_config(min_persons=config.minPersons)
            updated_fields.append("minPersons")
            logger.info(f"Updated minimum persons to {config.minPersons}")

        # Update cooldown
        if config.cooldown is not None and config.cooldown != settings.ALERT_COOLDOWN_SECONDS:
            settings.ALERT_COOLDOWN_SECONDS = config.cooldown
            alert_manager.update_config(cooldown=config.cooldown)
            updated_fields.append("cooldown")
            logger.info(f"Updated alert cooldown to {config.cooldown}s")

        # Update batch size
        if config.batchSize is not None and config.batchSize != settings.BATCH_SIZE:
            settings.BATCH_SIZE = config.batchSize
            updated_fields.append("batchSize")
            logger.info(f"Updated batch size to {config.batchSize}")

        # Update stream width
        if config.streamWidth is not None and config.streamWidth != settings.STREAM_WIDTH:
            settings.STREAM_WIDTH = config.streamWidth
            updated_fields.append("streamWidth")
            logger.info(f"Updated stream width to {config.streamWidth}")

        # Update stream height
        if config.streamHeight is not None and config.streamHeight != settings.STREAM_HEIGHT:
            settings.STREAM_HEIGHT = config.streamHeight
            updated_fields.append("streamHeight")
            logger.info(f"Updated stream height to {config.streamHeight}")

        # Update frame sampling
        if config.frameSampling is not None and config.frameSampling != settings.FRAME_SAMPLING:
            settings.FRAME_SAMPLING = config.frameSampling
            updated_fields.append("frameSampling")
            logger.info(f"Updated frame sampling to {config.frameSampling}")

        return {
            "message": f"Configuration updated successfully",
            "updated_fields": updated_fields,
            "current_config": {
                "model": settings.YOLO_MODEL,
                "confidence": settings.CONFIDENCE_THRESHOLD,
                "device": settings.DEVICE,
                "minPersons": settings.MIN_PERSONS_FOR_ALERT,
                "cooldown": settings.ALERT_COOLDOWN_SECONDS,
                "batchSize": settings.BATCH_SIZE
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_detection_status():
    """
    Get detection system status

    Returns:
        System status information
    """
    try:
        import torch

        return {
            "running": True,
            "model_loaded": detector.model is not None,
            "device": settings.DEVICE,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "current_model": settings.YOLO_MODEL
        }
    except Exception as e:
        logger.error(f"Error getting detection status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
