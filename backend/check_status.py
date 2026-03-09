from database.db_manager import DatabaseManager

db = DatabaseManager('database/surveillance.db')
cameras = db.get_all_camera_status()

online_streaming = [c for c in cameras if c['stream_connected']]

print(f"Camere con stream connesso: {len(online_streaming)}")
print(f"Totale camere: {len(cameras)}")
print()

if online_streaming:
    print("Dettagli camere attive:")
    for c in online_streaming:
        print(f"  - {c['camera_name']}: FPS={c['fps']:.1f}, last_update={c['last_update']}")
