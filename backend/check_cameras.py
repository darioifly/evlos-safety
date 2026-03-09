"""
Quick script to check camera IDs
"""
import sys
sys.path.insert(0, '.')

from services.nx_witness import nx_client

cameras = nx_client.get_cameras()

print("\n" + "="*80)
print("CAMERAS LIST")
print("="*80)

for i, cam in enumerate(cameras, 1):
    print(f"\n{i}. Name: {cam['name']}")
    print(f"   ID: {cam['id']}")
    print(f"   Online: {cam['isOnline']}")
    print(f"   Model: {cam.get('model', 'Unknown')}")

print("\n" + "="*80)
print(f"Total: {len(cameras)} cameras")
print("="*80)
