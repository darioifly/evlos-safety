"""
Real-time alert monitoring script
Watches logs and shows alert activity
"""
import time
import os
import sys
from datetime import datetime

LOG_FILE = "logs/app.log"

def tail_log(filename, n=50):
    """Get last N lines of log file"""
    try:
        with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            return lines[-n:]
    except FileNotFoundError:
        return []

def print_header():
    """Print monitoring header"""
    print("\n" + "="*80)
    print("🔍 ALERT MONITORING - Real-time Log Watch")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Log file: {LOG_FILE}")
    print("-"*80)
    print("Watching for:")
    print("  - [ALERT MANAGER] Alert conditions met")
    print("  - [ALERT SEND] HTTP requests to NxWitness")
    print("  - [ALERT SEND] Response status codes")
    print("  - Errors and warnings")
    print("-"*80)
    print("\nPress Ctrl+C to stop\n")

def highlight_line(line):
    """Add color/highlighting to important lines"""
    line = line.strip()

    # Skip empty lines
    if not line:
        return None

    # Filter for alert-related lines
    if not any(keyword in line for keyword in [
        "[ALERT", "Alert", "alert", "Person detected",
        "send_alert", "process_detection", "Generic Event", "Bookmark"
    ]):
        return None

    # Highlight based on content
    if "✅" in line or "SUCCESS" in line:
        return f"✅ {line}"
    elif "❌" in line or "FAILED" in line or "ERROR" in line:
        return f"❌ {line}"
    elif "⚠️" in line or "WARNING" in line:
        return f"⚠️  {line}"
    elif "[ALERT SEND] →" in line:
        return f"📤 {line}"
    elif "[ALERT SEND] ←" in line:
        return f"📥 {line}"
    elif "[ALERT MANAGER]" in line:
        return f"🎯 {line}"
    else:
        return f"   {line}"

def main():
    """Main monitoring loop"""
    print_header()

    if not os.path.exists(LOG_FILE):
        print(f"❌ Log file not found: {LOG_FILE}")
        print("\nMake sure the backend is running:")
        print("  cd backend")
        print("  python main.py")
        return

    # Get initial position
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(0, 2)  # Go to end
            last_pos = f.tell()

        print("🟢 Monitoring active... (waiting for alerts)\n")

        while True:
            with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_pos)
                new_lines = f.readlines()
                last_pos = f.tell()

                for line in new_lines:
                    highlighted = highlight_line(line)
                    if highlighted:
                        print(highlighted)
                        sys.stdout.flush()

            time.sleep(0.5)  # Check every 500ms

    except KeyboardInterrupt:
        print("\n\n" + "="*80)
        print("Monitoring stopped")
        print("="*80)
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
