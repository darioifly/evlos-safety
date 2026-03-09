"""
Test configuration loading from .env
"""
import sys
sys.path.insert(0, '.')

from config import settings

print("\n" + "="*60)
print("CONFIGURATION TEST")
print("="*60)
print(f"NX_SERVER_URL: {settings.NX_SERVER_URL}")
print(f"NX_STREAM_SERVER_URL: {settings.NX_STREAM_SERVER_URL}")
print(f"NX_ADMIN_USERNAME: {settings.NX_ADMIN_USERNAME}")
print(f"IGNORE_CAMERA_STATUS: {settings.IGNORE_CAMERA_STATUS}")
print("="*60)

# Quick connection test
from services.nx_witness import nx_client

print("\nTesting connection with loaded config...")
cameras = nx_client.get_cameras()
print(f"✅ Found {len(cameras)} cameras")

if cameras:
    for cam in cameras[:5]:
        print(f"  - {cam['name']} ({cam['id'][:20]}...) - Online: {cam['isOnline']}")
