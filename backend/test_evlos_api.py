"""
Quick test for EVLOS API endpoints
"""
import requests

BASE_URL = "http://localhost:7002/api/evlos"

print("Testing EVLOS API Endpoints")
print("=" * 60)

# Test 1: Get config
print("\n1. GET /api/evlos/config")
try:
    r = requests.get(f"{BASE_URL}/config")
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.json()}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test 2: Enable
print("\n2. POST /api/evlos/enable")
try:
    r = requests.post(f"{BASE_URL}/enable")
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.json()}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test 3: Get config again (should show enabled=true)
print("\n3. GET /api/evlos/config (after enable)")
try:
    r = requests.get(f"{BASE_URL}/config")
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.json()}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test 4: Disable
print("\n4. POST /api/evlos/disable")
try:
    r = requests.post(f"{BASE_URL}/disable")
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.json()}")
except Exception as e:
    print(f"   ERROR: {e}")

# Test 5: Get config final
print("\n5. GET /api/evlos/config (after disable)")
try:
    r = requests.get(f"{BASE_URL}/config")
    print(f"   Status: {r.status_code}")
    print(f"   Response: {r.json()}")
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 60)
print("Test complete!")
