"""
Test Script for NxWitness Integration
Tests Generic Events and Bookmarks APIs
"""
import sys
import time
import uuid
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, '.')

from services.nx_witness import nx_client
from config import settings
from utils.logger import logger

def test_connection():
    """Test 1: Connection to NxWitness"""
    print("\n" + "="*60)
    print("TEST 1: Connection to NxWitness Server")
    print("="*60)

    try:
        result = nx_client.test_connection()
        if result:
            print("✅ Connection successful!")
            return True
        else:
            print("❌ Connection failed!")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def test_get_cameras():
    """Test 2: Fetch camera list"""
    print("\n" + "="*60)
    print("TEST 2: Fetch Camera List")
    print("="*60)

    try:
        cameras = nx_client.get_cameras()
        if cameras:
            print(f"✅ Found {len(cameras)} cameras:")
            for i, cam in enumerate(cameras[:5], 1):  # Show first 5
                print(f"   {i}. {cam['name']} ({cam['id']}) - Online: {cam['isOnline']}")
            if len(cameras) > 5:
                print(f"   ... and {len(cameras) - 5} more")
            return cameras
        else:
            print("❌ No cameras found!")
            return []
    except Exception as e:
        print(f"❌ Error fetching cameras: {e}")
        return []


def test_generic_event(camera_id):
    """Test 3: Send Generic Event"""
    print("\n" + "="*60)
    print("TEST 3: Send Generic Event")
    print("="*60)

    try:
        # Prepare test metadata
        boxes = [
            {"x1": 100, "y1": 200, "x2": 300, "y2": 500, "confidence": 0.95},
            {"x1": 400, "y1": 150, "x2": 600, "y2": 480, "confidence": 0.87}
        ]

        metadata = {
            "alertLevel": "high",
            "cameraMetadata": {
                "name": "Test Camera",
                "location": "Test Location",
                "zone": "Test Zone"
            },
            "screenshotPath": "test/screenshot.jpg",
            "timestamp": time.time()
        }

        print(f"Sending event to camera: {camera_id}")
        print(f"  - Persons: 2")
        print(f"  - Confidence: 91%")
        print(f"  - Alert Level: HIGH")

        success = nx_client.send_alert(
            camera_id=camera_id,
            person_count=2,
            confidence=0.91,
            boxes=boxes,
            metadata=metadata
        )

        if success:
            print("✅ Generic Event sent successfully!")
            print("   → Check NxWitness notifications panel")
            return True
        else:
            print("❌ Failed to send Generic Event!")
            print("   → Check NxWitness logs and API permissions")
            return False

    except Exception as e:
        print(f"❌ Error sending event: {e}")
        return False


def test_bookmark(camera_id):
    """Test 4: Create Bookmark"""
    print("\n" + "="*60)
    print("TEST 4: Create Video Bookmark")
    print("="*60)

    try:
        print(f"Creating bookmark on camera: {camera_id}")
        print(f"  - Name: Test Bookmark - Person Detection")
        print(f"  - Duration: 60 seconds")
        print(f"  - Tags: test:true, persons:2")

        success = nx_client.create_bookmark(
            camera_id=camera_id,
            name="Test Bookmark - Person Detection",
            duration_seconds=60,
            tags={
                "test": "true",
                "persons": "2",
                "confidence": "0.91",
                "alertLevel": "high"
            }
        )

        if success:
            print("✅ Bookmark created successfully!")
            print("   → Check camera timeline in NxWitness")
            return True
        else:
            print("❌ Failed to create Bookmark!")
            print("   → Check user permissions: 'Manage bookmarks'")
            return False

    except Exception as e:
        print(f"❌ Error creating bookmark: {e}")
        return False


def print_summary(results):
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("-"*60)
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Integration is working correctly.")
        print("\nNext steps:")
        print("1. Check NxWitness notifications panel for the test event")
        print("2. Check camera timeline for the test bookmark")
        print("3. Create Event Rules in NxWitness to handle alerts")
        print("4. Configure camera metadata (locations, zones)")
    else:
        print("\n⚠️  Some tests failed. Please check:")
        print("1. NxWitness server is running and accessible")
        print("2. Credentials in .env are correct")
        print("3. User has Administrator role")
        print("4. User has 'Manage bookmarks' permission")
        print("5. HTTP API is enabled in NxWitness settings")
        print("6. Generic Events are enabled")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("NxWitness Integration Test Suite")
    print("="*60)
    print(f"Server URL: {settings.NX_SERVER_URL}")
    print(f"Stream URL: {settings.NX_STREAM_SERVER_URL}")
    print(f"Username: {settings.NX_ADMIN_USERNAME}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Test 1: Connection
    results["Connection"] = test_connection()
    if not results["Connection"]:
        print("\n❌ Cannot proceed: Connection failed!")
        print_summary(results)
        return

    # Test 2: Get Cameras
    cameras = test_get_cameras()
    results["Get Cameras"] = len(cameras) > 0
    if not cameras:
        print("\n❌ Cannot proceed: No cameras found!")
        print_summary(results)
        return

    # Use first online camera for tests
    test_camera = None
    for cam in cameras:
        if cam.get('isOnline'):
            test_camera = cam
            break

    if not test_camera:
        print("\n⚠️  No online cameras found, using first camera anyway...")
        test_camera = cameras[0]

    camera_id = test_camera['id']
    print(f"\n📹 Using camera for tests: {test_camera['name']} ({camera_id})")

    # Test 3: Generic Event
    results["Generic Event"] = test_generic_event(camera_id)

    # Wait a bit between tests
    time.sleep(1)

    # Test 4: Bookmark
    results["Bookmark"] = test_bookmark(camera_id)

    # Print summary
    print_summary(results)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
