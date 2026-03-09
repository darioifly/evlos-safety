"""
Watch console output for alerts in real-time
Shows only alert-related activity
"""
import sys
import time

print("\n" + "="*80)
print("🔍 ALERT CONSOLE WATCHER")
print("="*80)
print("This will highlight alert-related messages from the backend console.")
print("Make sure to pipe the backend output to this script:")
print()
print("  python main.py 2>&1 | python watch_console.py")
print()
print("Or just watch the main.py console for these patterns:")
print("  - [ALERT MANAGER] process_detection()")
print("  - [ALERT MANAGER] Alert conditions met")
print("  - [ALERT SEND] Attempting to send alert")
print("  - [ALERT SEND] → POST to:")
print("  - [ALERT SEND] ← Response status:")
print("  - [ALERT SEND] SUCCESS!")
print("="*80)
print()

try:
    for line in sys.stdin:
        line = line.strip()

        # Filter for alert-related lines
        if any(keyword in line for keyword in [
            "[ALERT", "Alert sent", "alert", "Person detected",
            "send_alert", "process_detection"
        ]):
            # Highlight based on content
            if "✅" in line or "SUCCESS" in line:
                print(f"✅ {line}")
            elif "❌" in line or "FAILED" in line or "ERROR" in line:
                print(f"❌ {line}")
            elif "⚠️" in line or "WARNING" in line:
                print(f"⚠️  {line}")
            elif "[ALERT SEND] →" in line:
                print(f"📤 {line}")
            elif "[ALERT SEND] ←" in line:
                print(f"📥 {line}")
            elif "[ALERT MANAGER]" in line:
                print(f"🎯 {line}")
            else:
                print(f"   {line}")
            sys.stdout.flush()

except KeyboardInterrupt:
    print("\n\nWatcher stopped")
