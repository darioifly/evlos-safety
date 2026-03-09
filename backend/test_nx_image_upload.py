"""
Test script to verify if NxWitness accepts image uploads with events
"""
import requests
from requests.auth import HTTPBasicAuth
import os

# NxWitness configuration
NX_SERVER = "http://192.168.1.31:7001"
NX_USER = "admin"
NX_PASS = "hik75814"

# Test image
test_image = r"c:\Users\iflys\Desktop\Safety\backend\data\static\alerts\Velletri_1_20251117_111249_191213_annotated.jpg"

if not os.path.exists(test_image):
    print(f"❌ Test image not found: {test_image}")
    exit(1)

print("=" * 70)
print("NxWitness Image Upload Test")
print("=" * 70)

# Test 1: Create event WITH image (multipart/form-data)
print("\n1. Testing /api/createEvent with image (multipart)...")
try:
    with open(test_image, 'rb') as img:
        files = {'file': (os.path.basename(test_image), img, 'image/jpeg')}
        params = {
            'source': '{446aab93-22f3-2593-5f68-31f4dcca48b5}',
            'caption': 'TEST: Image Upload',
            'description': 'Testing if image upload works',
            'eventType': 'personDetection'
        }

        response = requests.post(
            f"{NX_SERVER}/api/createEvent",
            params=params,
            files=files,
            auth=HTTPBasicAuth(NX_USER, NX_PASS),
            timeout=10,
            verify=False
        )

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:500]}")

        if response.status_code == 200:
            print("   ✅ SUCCESS - Image upload accepted!")
        else:
            print(f"   ⚠️ FAILED - Status {response.status_code}")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 2: Create event WITHOUT image (JSON)
print("\n2. Testing /api/createEvent without image (JSON)...")
try:
    payload = {
        'source': '{446aab93-22f3-2593-5f68-31f4dcca48b5}',
        'caption': 'TEST: No Image',
        'description': 'Testing without image',
        'eventType': 'personDetection'
    }

    response = requests.post(
        f"{NX_SERVER}/api/createEvent",
        json=payload,
        auth=HTTPBasicAuth(NX_USER, NX_PASS),
        timeout=10,
        verify=False
    )

    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:500]}")

    if response.status_code == 200:
        print("   ✅ SUCCESS - Event created!")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

# Test 3: Try alternative endpoint - /ec2/addEvent
print("\n3. Testing /ec2/addEvent with image...")
try:
    with open(test_image, 'rb') as img:
        files = {'file': (os.path.basename(test_image), img, 'image/jpeg')}
        params = {
            'source': '{446aab93-22f3-2593-5f68-31f4dcca48b5}',
            'caption': 'TEST: EC2 Upload',
            'description': 'Testing EC2 endpoint',
        }

        response = requests.post(
            f"{NX_SERVER}/ec2/addEvent",
            params=params,
            files=files,
            auth=HTTPBasicAuth(NX_USER, NX_PASS),
            timeout=10,
            verify=False
        )

        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:500]}")

        if response.status_code == 200:
            print("   ✅ SUCCESS!")
except Exception as e:
    print(f"   ❌ ERROR: {e}")

print("\n" + "=" * 70)
print("Test completed! Check NxWitness client to see if images appear.")
print("=" * 70)
