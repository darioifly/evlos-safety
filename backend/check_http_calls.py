"""
Check if HTTP POST calls are being made to NxWitness
Monitor the log file in real-time for alert activity
"""
import time
import re
from pathlib import Path

log_file = Path(__file__).parent / "logs" / "detection_20251112.log"

print("Monitoring log file for HTTP activity...")
print(f"Log file: {log_file}")
print("-" * 60)

# Get current file size
with open(log_file, 'r', encoding='utf-8') as f:
    f.seek(0, 2)  # Go to end
    file_size = f.tell()

print(f"Starting monitoring from position: {file_size}")
print("Waiting for new log entries...\n")

try:
    with open(log_file, 'r', encoding='utf-8') as f:
        f.seek(file_size)  # Start from current end

        while True:
            line = f.readline()
            if line:
                # Check for alert-related logs
                if any(keyword in line for keyword in ['ALERT SEND', 'POST to:', 'Response status:', 'Alert sent', 'ALERT:']):
                    print(line.strip())
            else:
                time.sleep(0.5)  # Wait before checking again

except KeyboardInterrupt:
    print("\n\nMonitoring stopped.")
