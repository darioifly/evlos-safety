"""
Test alert for specific camera
"""
import sys
sys.path.insert(0, '.')

from services.nx_witness import nx_client

# Get all cameras
cameras = nx_client.get_cameras()

# Find "pontinia 2" camera
pontinia_camera = None
for cam in cameras:
    if "pontinia" in cam['name'].lower() and "2" in cam['name']:
        pontinia_camera = cam
        break

if not pontinia_camera:
    print("❌ Camera 'pontinia 2' not found!")
    print("\nAvailable cameras:")
    for cam in cameras:
        print(f"  - {cam['name']} ({cam['id']})")
    sys.exit(1)

print("="*60)
print(f"Found camera: {pontinia_camera['name']}")
print(f"Camera ID: {pontinia_camera['id']}")
print(f"Online: {pontinia_camera['isOnline']}")
print("="*60)

# Test sending alert
print("\nSending test alert...")

boxes = [
    {"x1": 100, "y1": 200, "x2": 300, "y2": 500, "confidence": 0.793}
]

metadata = {
    "alertLevel": "low",
    "cameraMetadata": {
        "name": pontinia_camera['name'],
        "location": "Test Location",
        "zone": "Test Zone"
    },
    "timestamp": 1234567890
}

success = nx_client.send_alert(
    camera_id=pontinia_camera['id'],
    person_count=1,
    confidence=0.793,
    boxes=boxes,
    metadata=metadata
)

print("\n" + "="*60)
if success:
    print("✅ Alert sent successfully!")
    print("\nCheck NxWitness:")
    print("1. Notifications panel (bell icon)")
    print("2. Event Log menu")
    print("3. Should see: 'Person detected: 1 person(s) [LOW]'")
else:
    print("❌ Alert failed!")
    print("\nPossible issues:")
    print("1. Check backend logs: logs/app.log")
    print("2. Verify NxWitness API is accessible")
    print("3. Verify user permissions")
print("="*60)

# Test bookmark too
print("\n" + "="*60)
print("Testing bookmark creation...")
bookmark_success = nx_client.create_bookmark(
    camera_id=pontinia_camera['id'],
    name="Test - Person Detection",
    duration_seconds=60,
    tags={"persons": "1", "confidence": "0.793"}
)

if bookmark_success:
    print("✅ Bookmark created!")
    print("   → Check camera timeline")
else:
    print("❌ Bookmark failed!")
    print("   → Check 'Manage bookmarks' permission")
print("="*60)
