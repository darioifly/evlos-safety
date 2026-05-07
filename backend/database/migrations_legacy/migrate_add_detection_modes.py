"""
Migration: Add detection modes and presets support
"""
import sqlite3
import sys
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path(__file__).parent / "surveillance.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Adding detection mode columns to camera_status...")

    # Add detection_mode column
    try:
        cursor.execute("""
            ALTER TABLE camera_status
            ADD COLUMN detection_mode TEXT DEFAULT 'intrusion'
        """)
        print("✓ Added detection_mode column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("  - detection_mode column already exists")
        else:
            raise

    # Add detection_preset_id column
    try:
        cursor.execute("""
            ALTER TABLE camera_status
            ADD COLUMN detection_preset_id INTEGER NULL
        """)
        print("✓ Added detection_preset_id column")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("  - detection_preset_id column already exists")
        else:
            raise

    # Create detection_presets table
    print("\nCreating detection_presets table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detection_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            mode TEXT NOT NULL,
            intrusion_min_persons INTEGER DEFAULT 1,
            intrusion_confidence REAL DEFAULT 0.5,
            ppe_require_helmet BOOLEAN DEFAULT 1,
            ppe_require_vest BOOLEAN DEFAULT 1,
            ppe_confidence REAL DEFAULT 0.6,
            cooldown_seconds INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ Created detection_presets table")

    # Insert default presets
    print("\nInserting default presets...")

    # Intrusion presets
    cursor.execute("""
        INSERT OR IGNORE INTO detection_presets
        (id, name, description, mode, intrusion_min_persons, intrusion_confidence, cooldown_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (1, 'Intrusion - High Sensitivity', 'Detect 1+ person with 50% confidence', 'intrusion', 1, 0.5, 5))

    cursor.execute("""
        INSERT OR IGNORE INTO detection_presets
        (id, name, description, mode, intrusion_min_persons, intrusion_confidence, cooldown_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (2, 'Intrusion - Medium Sensitivity', 'Detect 1+ person with 70% confidence', 'intrusion', 1, 0.7, 10))

    cursor.execute("""
        INSERT OR IGNORE INTO detection_presets
        (id, name, description, mode, intrusion_min_persons, intrusion_confidence, cooldown_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (3, 'Intrusion - Low Sensitivity', 'Detect 2+ persons with 80% confidence', 'intrusion', 2, 0.8, 15))

    # PPE presets
    cursor.execute("""
        INSERT OR IGNORE INTO detection_presets
        (id, name, description, mode, ppe_require_helmet, ppe_require_vest, ppe_confidence, cooldown_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (4, 'PPE - Helmet Required', 'Alert when helmet missing', 'ppe', 1, 0, 0.6, 5))

    cursor.execute("""
        INSERT OR IGNORE INTO detection_presets
        (id, name, description, mode, ppe_require_helmet, ppe_require_vest, ppe_confidence, cooldown_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (5, 'PPE - Vest Required', 'Alert when vest missing', 'ppe', 0, 1, 0.6, 5))

    cursor.execute("""
        INSERT OR IGNORE INTO detection_presets
        (id, name, description, mode, ppe_require_helmet, ppe_require_vest, ppe_confidence, cooldown_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (6, 'PPE - Full (Helmet + Vest)', 'Alert when helmet or vest missing', 'ppe', 1, 1, 0.6, 5))

    print("✓ Default presets inserted")

    # Set default preset for existing cameras (Intrusion - High Sensitivity)
    print("\nSetting default preset for existing cameras...")
    cursor.execute("""
        UPDATE camera_status
        SET detection_preset_id = 1
        WHERE detection_preset_id IS NULL
    """)
    rows_updated = cursor.rowcount
    print(f"✓ Updated {rows_updated} cameras with default preset")

    conn.commit()
    conn.close()

    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    migrate()
