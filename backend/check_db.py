import sys
sys.path.insert(0, 'C:\\Users\\iflys\\Desktop\\Safety\\backend')

from database.db_manager import DatabaseManager
import json

db = DatabaseManager('database/surveillance.db')
cameras = db.get_all_camera_status()
print(json.dumps(cameras, indent=2, default=str))
