"""
Test script for EVLOS integration
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from integrations.evlos_client import evlos_client
from config import settings
from utils.logger import logger


def print_section(title):
    """Print section header"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_config():
    """Test EVLOS configuration"""
    print_section("EVLOS Configuration")

    print(f"Enabled:      {settings.EVLOS_ENABLED}")
    print(f"API URL:      {settings.EVLOS_API_URL}")
    print(f"Timeout:      {settings.EVLOS_TIMEOUT}s")
    print(f"Max Retries:  {settings.EVLOS_MAX_RETRIES}")
    print(f"Failed Dir:   {settings.EVLOS_FAILED_DIR}")

    if not settings.EVLOS_ENABLED:
        print("\n⚠️  EVLOS is DISABLED")
        print("To enable, set EVLOS_ENABLED=true in config or .env")
        return False

    return True


def test_connection():
    """Test EVLOS connection with dummy alert"""
    print_section("EVLOS Connection Test")

    if not settings.EVLOS_ENABLED:
        print("⏸️  Skipping (EVLOS disabled)")
        return

    print(f"Testing connection to {settings.EVLOS_API_URL}...")
    print("Sending dummy test alert...")

    result = evlos_client.test_connection()

    if result['success']:
        print(f"\n✅ SUCCESS!")
        print(f"Message: {result['message']}")
        print(f"Alert ID: {result['alert_id']}")
    else:
        print(f"\n❌ FAILED")
        print(f"Message: {result['message']}")


def test_alert_type_mapping():
    """Test alert type mappings"""
    print_section("Alert Type Mapping")

    test_cases = [
        ('person_detection', 1, 'intrusion'),
        ('person_detection', 3, 'crowd'),
        ('person_detection', 5, 'crowd'),
        ('helmet_missing', 1, 'no_ppe'),
        ('person_fall', 1, 'fall_detection'),
        ('unknown_type', 1, 'other'),
    ]

    print(f"{'Internal Type':<20} {'Persons':<10} {'→':<5} {'EVLOS Type':<15} {'Status':<10}")
    print("-" * 60)

    for internal_type, person_count, expected in test_cases:
        result = evlos_client.map_alert_type(internal_type, person_count)
        status = "✓" if result == expected else f"✗ (got {result})"
        print(f"{internal_type:<20} {person_count:<10} {'→':<5} {expected:<15} {status:<10}")


def test_severity_mapping():
    """Test severity mappings"""
    print_section("Severity Mapping")

    test_cases = [
        ('low', 'low'),
        ('medium', 'medium'),
        ('high', 'high'),
        ('critical', 'critical'),
    ]

    print(f"{'Internal Level':<20} {'→':<5} {'EVLOS Severity':<15} {'Status':<10}")
    print("-" * 60)

    for internal_level, expected in test_cases:
        result = evlos_client.map_severity(internal_level)
        status = "✓" if result == expected else f"✗ (got {result})"
        print(f"{internal_level:<20} {'→':<5} {expected:<15} {status:<10}")


def test_failed_alerts_dir():
    """Test failed alerts directory"""
    print_section("Failed Alerts Directory")

    failed_dir = Path(settings.EVLOS_FAILED_DIR)

    if failed_dir.exists():
        print(f"✓ Directory exists: {failed_dir}")

        # Count files
        json_files = list(failed_dir.glob("*.json"))
        jpg_files = list(failed_dir.glob("*.jpg"))

        print(f"  JSON files: {len(json_files)}")
        print(f"  Image files: {len(jpg_files)}")

        if json_files:
            print("\n  Recent failed alerts:")
            for json_file in sorted(json_files, reverse=True)[:5]:
                print(f"    - {json_file.name}")
    else:
        print(f"ℹ️  Directory does not exist yet: {failed_dir}")
        print("   It will be created automatically on first failed alert")


def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "EVLOS Integration Test" + " " * 21 + "║")
    print("╚" + "=" * 58 + "╝")

    # Test 1: Configuration
    enabled = test_config()

    # Test 2: Alert type mapping
    test_alert_type_mapping()

    # Test 3: Severity mapping
    test_severity_mapping()

    # Test 4: Failed alerts directory
    test_failed_alerts_dir()

    # Test 5: Connection (only if enabled)
    if enabled:
        test_connection()

    # Summary
    print_section("Summary")

    if enabled:
        print("EVLOS integration is ENABLED and ready to use.")
        print("\nNext steps:")
        print("  1. Start the backend: python main.py")
        print("  2. Trigger an alert (show person to camera)")
        print("  3. Check logs for: 'EVLOS alert queued'")
        print("  4. Check EVLOS platform for received alert")
    else:
        print("EVLOS integration is DISABLED.")
        print("\nTo enable:")
        print("  1. Set EVLOS_ENABLED=true in config.py or .env")
        print("  2. Restart the backend")
        print("  3. Run this test again to verify connection")

    print("\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
