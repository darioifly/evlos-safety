"""
Database Manager for Person Detection System
Handles SQLite database operations for shared data between processes
"""
import sqlite3
import json
import threading
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path
from utils.logger import logger

DB_PATH = Path(__file__).parent / "surveillance.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_local_timestamp():
    """Get current timestamp in local timezone (Rome/Europe)"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DatabaseManager:
    """Manages SQLite database operations"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_database()
        # Persistent read connection for hot-path WS reads (F-012).
        # Serialized via _read_lock because sqlite3 connections are not
        # thread-safe even with check_same_thread=False.
        self._read_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._read_conn.row_factory = sqlite3.Row
        self._read_conn.execute("PRAGMA busy_timeout=5000")
        self._read_conn.execute("PRAGMA foreign_keys=ON")
        self._read_lock = threading.Lock()

    def _init_database(self):
        """Initialize database with schema"""
        try:
            conn = self.get_connection()

            # WAL allows concurrent readers/writers without "database is locked".
            # synchronous=NORMAL is safe with WAL and faster than FULL.
            # busy_timeout gives writes 5s to wait for a reader instead of failing immediately.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")

            # Read and execute schema
            if SCHEMA_PATH.exists():
                with open(SCHEMA_PATH, 'r') as f:
                    schema_sql = f.read()
                conn.executescript(schema_sql)
                conn.commit()
                logger.info(f"Database initialized at {self.db_path}")
            else:
                logger.warning(f"Schema file not found: {SCHEMA_PATH}")

            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Access columns by name
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _read(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Execute a read query against the shared persistent connection (F-012).

        Used by hot-path reads called from the WebSocket loop to avoid
        opening/closing a connection per call.
        """
        with self._read_lock:
            cursor = self._read_conn.execute(sql, params)
            return cursor.fetchall()

    def close(self):
        """Close the persistent read connection. Called from FastAPI lifespan shutdown."""
        try:
            with self._read_lock:
                self._read_conn.close()
        except Exception as e:
            logger.debug(f"Error closing read connection: {e}")

    # Camera Status Operations

    def upsert_camera_status(self, camera_id: str, camera_name: str,
                            online: bool = False, stream_connected: bool = False,
                            person_count: int = 0, fps: float = 0.0):
        """Insert or update camera status"""
        conn = self.get_connection()
        timestamp = get_local_timestamp()
        try:
            conn.execute("""
                INSERT INTO camera_status
                (camera_id, camera_name, online, stream_connected, person_count, fps, last_update)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(camera_id) DO UPDATE SET
                    camera_name = excluded.camera_name,
                    online = excluded.online,
                    stream_connected = excluded.stream_connected,
                    person_count = excluded.person_count,
                    fps = excluded.fps,
                    last_update = ?
            """, (camera_id, camera_name, online, stream_connected, person_count, fps, timestamp, timestamp))
            conn.commit()
        finally:
            conn.close()

    def update_camera_detection(self, camera_id: str, person_count: int):
        """Update camera with new detection"""
        conn = self.get_connection()
        timestamp = get_local_timestamp()
        try:
            conn.execute("""
                UPDATE camera_status
                SET person_count = ?,
                    last_update = ?,
                    last_detection = ?
                WHERE camera_id = ?
            """, (person_count, timestamp, timestamp, camera_id))
            conn.commit()
        finally:
            conn.close()

    def get_all_camera_status(self) -> List[Dict]:
        """Get status of all cameras (F-012: hot-path read on shared connection)"""
        rows = self._read("""
            SELECT camera_id, camera_name, online, stream_connected,
                   person_count, fps, enabled, last_update, last_detection
            FROM camera_status
            ORDER BY camera_name
        """)
        return [dict(row) for row in rows]

    def get_camera_status(self, camera_id: str) -> Optional[Dict]:
        """Get status of specific camera"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM camera_status WHERE camera_id = ?
            """, (camera_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # Detection Operations

    def insert_detection(self, camera_id: str, person_count: int,
                        avg_confidence: float, boxes: List[Dict] = None):
        """Insert new detection event"""
        conn = self.get_connection()
        timestamp = get_local_timestamp()
        try:
            boxes_json = json.dumps(boxes) if boxes else None
            cursor = conn.execute("""
                INSERT INTO detections
                (camera_id, person_count, avg_confidence, boxes, timestamp, notified)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (camera_id, person_count, avg_confidence, boxes_json, timestamp))
            detection_id = cursor.lastrowid
            conn.commit()
            return detection_id
        finally:
            conn.close()

    def get_unnotified_detections(self) -> List[Dict]:
        """Get all unnotified detections"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT d.id, d.camera_id, c.camera_name, d.person_count,
                       d.avg_confidence, d.boxes, d.timestamp
                FROM detections d
                JOIN camera_status c ON d.camera_id = c.camera_id
                WHERE d.notified = 0 AND d.person_count > 0
                ORDER BY d.timestamp DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def mark_detections_notified(self, detection_ids: List[int]):
        """Mark detections as notified"""
        if not detection_ids:
            return

        conn = self.get_connection()
        try:
            placeholders = ','.join('?' * len(detection_ids))
            conn.execute(f"""
                UPDATE detections
                SET notified = 1
                WHERE id IN ({placeholders})
            """, detection_ids)
            conn.commit()
        finally:
            conn.close()

    # Alert Operations

    def insert_alert(self, camera_id: str, camera_name: str,
                    person_count: int, avg_confidence: float,
                    full_image_path: str = None, cropped_image_path: str = None):
        """Insert new alert with optional image paths"""
        conn = self.get_connection()
        timestamp = get_local_timestamp()
        try:
            cursor = conn.execute("""
                INSERT INTO alerts
                (camera_id, camera_name, person_count, avg_confidence,
                 full_image_path, cropped_image_path, timestamp, notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """, (camera_id, camera_name, person_count, avg_confidence,
                  full_image_path, cropped_image_path, timestamp))
            alert_id = cursor.lastrowid
            conn.commit()
            return alert_id
        finally:
            conn.close()

    def get_unnotified_alerts(self) -> List[Dict]:
        """Get all unnotified alerts (F-012: hot-path read on shared connection)"""
        rows = self._read("""
            SELECT id, camera_id, camera_name, person_count,
                   avg_confidence, full_image_path, cropped_image_path, timestamp
            FROM alerts
            WHERE notified = 0
            ORDER BY timestamp DESC
        """)
        return [dict(row) for row in rows]

    def mark_alerts_notified(self, alert_ids: List[int]):
        """Mark alerts as notified"""
        if not alert_ids:
            return

        conn = self.get_connection()
        try:
            placeholders = ','.join('?' * len(alert_ids))
            conn.execute(f"""
                UPDATE alerts
                SET notified = 1
                WHERE id IN ({placeholders})
            """, alert_ids)
            conn.commit()
        finally:
            conn.close()

    def get_recent_alerts(self, limit: int = 100, camera_id: str = None) -> List[Dict]:
        """Get recent alerts from database"""
        conn = self.get_connection()
        try:
            if camera_id:
                cursor = conn.execute("""
                    SELECT id, camera_id, camera_name, person_count,
                           avg_confidence, full_image_path, cropped_image_path, timestamp
                    FROM alerts
                    WHERE camera_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (camera_id, limit))
            else:
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

    # Metrics Operations

    def record_metric(self, name: str, value: float):
        """Record a metric value"""
        conn = self.get_connection()
        timestamp = get_local_timestamp()
        try:
            conn.execute("""
                INSERT INTO metrics (metric_name, metric_value, timestamp)
                VALUES (?, ?, ?)
            """, (name, value, timestamp))
            conn.commit()
        finally:
            conn.close()

    def get_recent_metrics(self, name: str, limit: int = 100) -> List[Dict]:
        """Get recent metrics for a given name"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT metric_value, timestamp
                FROM metrics
                WHERE metric_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (name, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # Maintenance Operations

    def cleanup_old_detections(self, days: int = 7):
        """Delete detections older than specified days"""
        conn = self.get_connection()
        try:
            conn.execute("""
                DELETE FROM detections
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (days,))
            conn.commit()
            logger.info(f"Cleaned up detections older than {days} days")
        finally:
            conn.close()

    def cleanup_old_alerts(self, days: int = 7):
        """Delete alerts older than specified days"""
        conn = self.get_connection()
        try:
            conn.execute("""
                DELETE FROM alerts
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            """, (days,))
            conn.commit()
            logger.info(f"Cleaned up alerts older than {days} days")
        finally:
            conn.close()

    # Worker State Operations

    def set_camera_enabled(self, camera_id: str, enabled: bool):
        """Set camera worker enabled state (for persistence)"""
        conn = self.get_connection()
        try:
            conn.execute("""
                UPDATE camera_status
                SET enabled = ?
                WHERE camera_id = ?
            """, (enabled, camera_id))
            conn.commit()
            logger.info(f"Camera {camera_id} enabled state set to {enabled}")
        finally:
            conn.close()

    def get_enabled_cameras(self) -> List[Dict]:
        """Get all cameras that should have workers running"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT camera_id, camera_name, enabled
                FROM camera_status
                WHERE enabled = 1
                ORDER BY camera_name
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def is_camera_enabled(self, camera_id: str) -> bool:
        """Check if camera worker should be running"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT enabled FROM camera_status WHERE camera_id = ?
            """, (camera_id,))
            row = cursor.fetchone()
            return bool(row['enabled']) if row else False
        finally:
            conn.close()

    # Detection Presets Operations

    def get_all_presets(self) -> List[Dict]:
        """Get all detection presets"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM detection_presets
                ORDER BY mode, name
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_preset(self, preset_id: int) -> Optional[Dict]:
        """Get specific preset by ID"""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM detection_presets WHERE id = ?
            """, (preset_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def create_preset(self, name: str, description: str, mode: str, **settings) -> int:
        """Create new detection preset"""
        conn = self.get_connection()
        timestamp = get_local_timestamp()
        try:
            cursor = conn.execute("""
                INSERT INTO detection_presets
                (name, description, mode, intrusion_min_persons, intrusion_confidence,
                 ppe_require_helmet, ppe_require_vest, ppe_confidence, cooldown_seconds,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, description, mode,
                settings.get('intrusion_min_persons', 1),
                settings.get('intrusion_confidence', 0.5),
                settings.get('ppe_require_helmet', True),
                settings.get('ppe_require_vest', True),
                settings.get('ppe_confidence', 0.6),
                settings.get('cooldown_seconds', 5),
                timestamp, timestamp
            ))
            preset_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Created preset: {name} (ID: {preset_id})")
            return preset_id
        finally:
            conn.close()

    def update_preset(self, preset_id: int, **settings) -> bool:
        """Update detection preset"""
        conn = self.get_connection()
        timestamp = get_local_timestamp()
        try:
            # Build dynamic UPDATE query based on provided settings
            update_fields = []
            values = []

            for key, value in settings.items():
                if key in ['name', 'description', 'mode', 'intrusion_min_persons',
                          'intrusion_confidence', 'ppe_require_helmet', 'ppe_require_vest',
                          'ppe_confidence', 'cooldown_seconds']:
                    update_fields.append(f"{key} = ?")
                    values.append(value)

            if not update_fields:
                return False

            update_fields.append("updated_at = ?")
            values.append(timestamp)
            values.append(preset_id)

            query = f"""
                UPDATE detection_presets
                SET {', '.join(update_fields)}
                WHERE id = ?
            """

            conn.execute(query, values)
            conn.commit()
            logger.info(f"Updated preset ID: {preset_id}")
            return True
        finally:
            conn.close()

    def delete_preset(self, preset_id: int) -> bool:
        """Delete detection preset (only if not in use)"""
        conn = self.get_connection()
        try:
            # Check if preset is in use
            cursor = conn.execute("""
                SELECT COUNT(*) as count FROM camera_status
                WHERE detection_preset_id = ?
            """, (preset_id,))
            count = cursor.fetchone()['count']

            if count > 0:
                logger.warning(f"Cannot delete preset {preset_id}: in use by {count} cameras")
                return False

            conn.execute("DELETE FROM detection_presets WHERE id = ?", (preset_id,))
            conn.commit()
            logger.info(f"Deleted preset ID: {preset_id}")
            return True
        finally:
            conn.close()

    # Camera Detection Mode Operations

    def set_camera_detection_mode(self, camera_id: str, mode: str, preset_id: Optional[int] = None):
        """Set camera detection mode and preset"""
        conn = self.get_connection()
        try:
            conn.execute("""
                UPDATE camera_status
                SET detection_mode = ?, detection_preset_id = ?
                WHERE camera_id = ?
            """, (mode, preset_id, camera_id))
            conn.commit()
            logger.info(f"Camera {camera_id} detection mode set to {mode} with preset {preset_id}")
        finally:
            conn.close()

    def get_camera_detection_config(self, camera_id: str) -> Optional[Dict]:
        """Get camera detection configuration with preset details (F-012: hot-path read on shared connection)"""
        rows = self._read("""
            SELECT
                c.detection_mode,
                c.detection_preset_id,
                p.name as preset_name,
                p.*
            FROM camera_status c
            LEFT JOIN detection_presets p ON c.detection_preset_id = p.id
            WHERE c.camera_id = ?
        """, (camera_id,))
        return dict(rows[0]) if rows else None


# Global database instance
db = DatabaseManager()
