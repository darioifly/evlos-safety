-- SQLite Database Schema for Person Detection System
-- Shared database between FastAPI and Video Worker processes

-- Camera status table - Updated by Video Worker, Read by FastAPI
CREATE TABLE IF NOT EXISTS camera_status (
    camera_id TEXT PRIMARY KEY,
    camera_name TEXT NOT NULL,
    online BOOLEAN DEFAULT 0,
    stream_connected BOOLEAN DEFAULT 0,
    person_count INTEGER DEFAULT 0,
    fps REAL DEFAULT 0.0,
    enabled BOOLEAN DEFAULT 1,  -- Whether worker should process this camera
    detection_mode TEXT DEFAULT 'intrusion',  -- 'intrusion' or 'ppe' (DPI)
    detection_preset_id INTEGER NULL,  -- Reference to detection_presets table
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_detection TIMESTAMP NULL,
    FOREIGN KEY (detection_preset_id) REFERENCES detection_presets(id)
);

-- Detection events table - Written by Video Worker, Read by FastAPI
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    person_count INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    boxes TEXT,  -- JSON string with bounding box coordinates
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT 0,  -- Marked as 1 after sent via WebSocket
    FOREIGN KEY (camera_id) REFERENCES camera_status(camera_id)
);

-- Alert events table - Written by Video Worker when person detected
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id TEXT NOT NULL,
    camera_name TEXT NOT NULL,
    person_count INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    full_image_path TEXT,  -- Path to full frame image
    cropped_image_path TEXT,  -- Path to cropped person image
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT 0,  -- Marked as 1 after sent via WebSocket
    FOREIGN KEY (camera_id) REFERENCES camera_status(camera_id)
);

-- Metrics table - Performance tracking
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Detection presets table - Configurable detection settings
CREATE TABLE IF NOT EXISTS detection_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    mode TEXT NOT NULL,  -- 'intrusion' or 'ppe'
    -- Intrusion mode settings
    intrusion_min_persons INTEGER DEFAULT 1,
    intrusion_confidence REAL DEFAULT 0.5,
    -- PPE mode settings
    ppe_require_helmet BOOLEAN DEFAULT 1,
    ppe_require_vest BOOLEAN DEFAULT 1,
    ppe_confidence REAL DEFAULT 0.6,
    -- Common settings
    cooldown_seconds INTEGER DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default presets
INSERT OR IGNORE INTO detection_presets (id, name, description, mode, intrusion_min_persons, intrusion_confidence, cooldown_seconds)
VALUES
    (1, 'Intrusion - High Sensitivity', 'Detect 1+ person with 50% confidence', 'intrusion', 1, 0.5, 5),
    (2, 'Intrusion - Medium Sensitivity', 'Detect 1+ person with 70% confidence', 'intrusion', 1, 0.7, 10),
    (3, 'Intrusion - Low Sensitivity', 'Detect 2+ persons with 80% confidence', 'intrusion', 2, 0.8, 15);

INSERT OR IGNORE INTO detection_presets (id, name, description, mode, ppe_require_helmet, ppe_require_vest, ppe_confidence, cooldown_seconds)
VALUES
    (4, 'PPE - Helmet Required', 'Alert when helmet missing', 'ppe', 1, 0, 0.6, 5),
    (5, 'PPE - Vest Required', 'Alert when vest missing', 'ppe', 0, 1, 0.6, 5),
    (6, 'PPE - Full (Helmet + Vest)', 'Alert when helmet or vest missing', 'ppe', 1, 1, 0.6, 5);

-- Create indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_detections_camera ON detections(camera_id);
CREATE INDEX IF NOT EXISTS idx_detections_timestamp ON detections(timestamp);
CREATE INDEX IF NOT EXISTS idx_detections_notified ON detections(notified);
CREATE INDEX IF NOT EXISTS idx_alerts_notified ON alerts(notified);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
