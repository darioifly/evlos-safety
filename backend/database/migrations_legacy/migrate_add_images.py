"""
Migration script to add image path columns to alerts table
"""
import sqlite3
import os

# Get database path
db_path = os.path.join(os.path.dirname(__file__), 'surveillance.db')

print(f"Migrating database: {db_path}")

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(alerts)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'full_image_path' not in columns:
        print("Adding full_image_path column...")
        cursor.execute("ALTER TABLE alerts ADD COLUMN full_image_path TEXT")
        print("Added full_image_path")
    else:
        print("full_image_path already exists")

    if 'cropped_image_path' not in columns:
        print("Adding cropped_image_path column...")
        cursor.execute("ALTER TABLE alerts ADD COLUMN cropped_image_path TEXT")
        print("Added cropped_image_path")
    else:
        print("cropped_image_path already exists")

    conn.commit()
    print("\nMigration completed successfully!")

except Exception as e:
    print(f"Migration failed: {e}")
    conn.rollback()
finally:
    conn.close()
