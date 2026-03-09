"""
EVLOS Integration Router
Provides endpoints for testing and managing EVLOS integration
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional

from integrations.evlos_client import evlos_client
from config import settings
from utils.logger import logger

router = APIRouter(prefix="/api/evlos", tags=["EVLOS"])


class EVLOSConfigResponse(BaseModel):
    """EVLOS configuration status"""
    enabled: bool
    api_url: str
    timeout: int
    max_retries: int
    failed_dir: str


class EVLOSTestResponse(BaseModel):
    """EVLOS connection test result"""
    success: bool
    message: str
    alert_id: Optional[str] = None


@router.get("/config", response_model=EVLOSConfigResponse)
async def get_evlos_config():
    """
    Get current EVLOS configuration

    Returns configuration status and settings for EVLOS integration.
    """
    return EVLOSConfigResponse(
        enabled=evlos_client.enabled,
        api_url=settings.EVLOS_API_URL,
        timeout=settings.EVLOS_TIMEOUT,
        max_retries=settings.EVLOS_MAX_RETRIES,
        failed_dir=settings.EVLOS_FAILED_DIR
    )


@router.post("/test", response_model=EVLOSTestResponse)
async def test_evlos_connection():
    """
    Test connection to EVLOS API

    Sends a dummy test alert to verify connectivity and authentication.
    Returns success status and any error messages.
    """
    logger.info("EVLOS connection test requested via API")

    try:
        result = evlos_client.test_connection()

        return EVLOSTestResponse(
            success=result['success'],
            message=result['message'],
            alert_id=result.get('alert_id')
        )

    except Exception as e:
        logger.error(f"EVLOS test failed with exception: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Test failed: {str(e)}"
        )


@router.get("/failed-alerts")
async def get_failed_alerts() -> Dict:
    """
    Get list of failed alerts stored locally

    Returns count and list of failed alert files that can be retried manually.
    """
    import os
    from pathlib import Path

    failed_dir = Path(settings.EVLOS_FAILED_DIR)

    if not failed_dir.exists():
        return {
            "count": 0,
            "alerts": [],
            "message": "No failed alerts directory found"
        }

    # List JSON metadata files (each represents a failed alert)
    json_files = list(failed_dir.glob("*.json"))

    alerts = []
    for json_file in json_files:
        try:
            import json
            with open(json_file, 'r') as f:
                metadata = json.load(f)

            # Add filename info
            metadata['json_file'] = json_file.name
            metadata['image_file'] = json_file.stem + '.jpg'

            alerts.append(metadata)
        except Exception as e:
            logger.warning(f"Error reading failed alert {json_file}: {e}")

    # Sort by timestamp (newest first)
    alerts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    return {
        "count": len(alerts),
        "alerts": alerts,
        "directory": str(failed_dir)
    }


@router.post("/enable", status_code=200)
async def enable_evlos() -> Dict:
    """
    Enable EVLOS integration at runtime

    Note: This only affects the current process. To persist, set EVLOS_ENABLED=true in config.
    """
    try:
        evlos_client.enabled = True
        logger.info("EVLOS integration enabled via API")

        return {
            "success": True,
            "message": "EVLOS integration enabled (runtime only - update config for persistence)"
        }
    except Exception as e:
        logger.error(f"Error enabling EVLOS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disable", status_code=200)
async def disable_evlos() -> Dict:
    """
    Disable EVLOS integration at runtime

    Note: This only affects the current process. To persist, set EVLOS_ENABLED=false in config.
    """
    try:
        evlos_client.enabled = False
        logger.info("EVLOS integration disabled via API")

        return {
            "success": True,
            "message": "EVLOS integration disabled (runtime only - update config for persistence)"
        }
    except Exception as e:
        logger.error(f"Error disabling EVLOS: {e}")
        raise HTTPException(status_code=500, detail=str(e))
