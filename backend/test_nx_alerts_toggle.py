"""
Test script to enable NxWitness alerts and monitor HTTP activity
"""
import requests
import json
import time
from pathlib import Path

API_URL = "http://localhost:7002"

print("=" * 70)
print("NxWitness Alerts Toggle Test")
print("=" * 70)

# 1. Read current config
print("\n1. Reading current configuration...")
response = requests.get(f"{API_URL}/api/detection/config")
config = response.json()
print(f"Current nxWitnessAlerts.enabled: {config.get('nxWitnessAlerts', {}).get('enabled', False)}")

# 2. Enable NxWitness alerts
print("\n2. Enabling NxWitness alerts...")
config['nxWitnessAlerts'] = {
    'enabled': True,
    'sendEvents': True,
    'createBookmarks': True,
    'bookmarkDuration': 300
}

response = requests.post(f"{API_URL}/api/detection/config", json=config)
print(f"Response: {response.json()}")

# 3. Verify config was updated
print("\n3. Verifying configuration update...")
time.sleep(1)
response = requests.get(f"{API_URL}/api/detection/config")
new_config = response.json()
print(f"New nxWitnessAlerts.enabled: {new_config.get('nxWitnessAlerts', {}).get('enabled', False)}")

# 4. Monitor logs for NxWitness activity
print("\n4. Monitoring logs for NxWitness HTTP alerts...")
print("Waiting for alerts (monitoring next 30 seconds)...")
print("-" * 70)

log_file = Path(__file__).parent / "logs" / "detection_20251112.log"
start_time = time.time()
last_position = log_file.stat().st_size if log_file.exists() else 0

try:
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        f.seek(last_position)

        while time.time() - start_time < 30:
            line = f.readline()
            if line:
                # Filter for NxWitness related logs
                if any(keyword in line for keyword in [
                    'NxWitness alerts enabled',
                    'Alert event sent to NxWitness',
                    'Bookmark created on NxWitness',
                    '[ALERT SEND]',
                    'POST to:',
                    'Response status:'
                ]):
                    print(line.strip())
            else:
                time.sleep(0.5)

except KeyboardInterrupt:
    print("\n\nMonitoring stopped.")

print("\n" + "=" * 70)
print("Test completed!")
print("=" * 70)
print("\nCheck the logs above for:")
print("  ✓ 'NxWitness alerts enabled' - System detected config change")
print("  ✓ 'Alert event sent to NxWitness' - HTTP POST successful")
print("  ✓ 'Bookmark created on NxWitness' - Bookmark creation successful")
print("  ✓ '[ALERT SEND]' messages - Detailed HTTP activity")
