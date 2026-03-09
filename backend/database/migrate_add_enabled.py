"""
Migration script to add 'enabled' column to camera_status table
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "surveillance.db"

def migrate():
    """Add enabled column to camera_status table"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(camera_status)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'enabled' not in columns:
            print("Adding 'enabled' column to camera_status table...")
            cursor.execute("""
                ALTER TABLE camera_status
                ADD COLUMN enabled BOOLEAN DEFAULT 1
            """)
            conn.commit()
            print("Column 'enabled' added successfully")
        else:
            print("Column 'enabled' already exists, skipping migration")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
