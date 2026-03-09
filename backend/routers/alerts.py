"""
Alerts API Router
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Dict, Optional
from datetime import datetime
import csv
import io
import os

from services.alert_manager import alert_manager
from database.db_manager import db
from utils.logger import logger
from utils.screenshot import get_screenshot_stats
from config import settings

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=List[Dict])
@router.get("/recent", response_model=List[Dict])
async def get_alerts(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of alerts to return"),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID")
):
    """
    Get alert history from database

    Args:
        limit: Maximum number of alerts to return
        camera_id: Optional camera ID filter

    Returns:
        List of alert dictionaries
    """
    try:
        # Get alerts from database
        alerts = db.get_recent_alerts(limit=limit, camera_id=camera_id)

        # Convert database format to frontend format
        formatted_alerts = []
        for alert in alerts:
            # Calculate alert level based on person count and confidence
            alert_level = 'low'
            if alert['person_count'] >= 3:
                alert_level = 'high'
            elif alert['person_count'] >= 2:
                alert_level = 'medium'

            formatted_alerts.append({
                'id': alert['id'],
                'camera_id': alert['camera_id'],
                'camera_name': alert['camera_name'],
                'person_count': alert['person_count'],
                'avg_confidence': alert['avg_confidence'],
                'timestamp': alert['timestamp'],
                'alertLevel': alert_level,
                'full_image_path': alert['full_image_path'],
                'cropped_image_path': alert['cropped_image_path']
            })

        logger.info(f"Retrieved {len(formatted_alerts)} alerts from database")
        return formatted_alerts
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_alerts_csv(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID")
):
    """
    Export alerts to CSV file

    Args:
        camera_id: Optional camera ID filter

    Returns:
        CSV file as streaming response
    """
    try:
        alerts = alert_manager.get_history(limit=10000, camera_id=camera_id)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=['timestamp', 'cameraId', 'persons', 'confidence']
        )
        writer.writeheader()

        for alert in alerts:
            writer.writerow({
                'timestamp': alert['timestamp'],
                'cameraId': alert['cameraId'],
                'persons': alert['persons'],
                'confidence': f"{alert['confidence']:.2%}"
            })

        # Prepare response
        output.seek(0)
        filename = f"alerts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"Error exporting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buffer-status")
async def get_buffer_status():
    """
    Get alert buffer status

    Returns:
        Buffer status information
    """
    try:
        status = alert_manager.get_buffer_status()
        return status
    except Exception as e:
        logger.error(f"Error getting buffer status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_alert_stats():
    """
    Get alert statistics

    Returns:
        Alert statistics
    """
    try:
        alerts = alert_manager.get_history(limit=10000)

        # Calculate stats
        total_alerts = len(alerts)
        cameras_with_alerts = len(set(a['cameraId'] for a in alerts))

        # Count alerts per camera
        camera_counts = {}
        for alert in alerts:
            camera_id = alert['cameraId']
            camera_counts[camera_id] = camera_counts.get(camera_id, 0) + 1

        # Get today's alerts
        today = datetime.now().date()
        alerts_today = sum(
            1 for a in alerts
            if datetime.fromisoformat(a['timestamp']).date() == today
        )

        return {
            "total_alerts": total_alerts,
            "alerts_today": alerts_today,
            "cameras_with_alerts": cameras_with_alerts,
            "alerts_per_camera": camera_counts,
            "buffer_status": alert_manager.get_buffer_status()
        }

    except Exception as e:
        logger.error(f"Error getting alert stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshot/{filename}")
async def get_screenshot(filename: str):
    """
    Serve alert screenshot file

    Args:
        filename: Screenshot filename

    Returns:
        Screenshot image file
    """
    try:
        # Validate filename to prevent path traversal attacks
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        # Build file path
        screenshot_dir = settings.ALERT_SCREENSHOT_DIR
        filepath = os.path.join(screenshot_dir, filename)

        # Check if file exists
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Screenshot not found")

        # Check if it's actually a file (not a directory)
        if not os.path.isfile(filepath):
            raise HTTPException(status_code=400, detail="Invalid file")

        # Serve file
        return FileResponse(
            filepath,
            media_type="image/jpeg",
            filename=filename
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving screenshot {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screenshots/stats")
async def get_screenshots_stats():
    """
    Get statistics about stored screenshots

    Returns:
        Screenshot statistics (count, size, age)
    """
    try:
        stats = get_screenshot_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting screenshot stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
