#!/usr/bin/env python3
"""
Quick regression checks for Cypher timestamp handling utilities.
Ensures our helpers emit RFC3339 strings suitable for Graphiti ingestion.
"""

from flows.utils import current_timestamp_iso, iso_from_epoch_millis, is_isoformat_timestamp


def check_current_timestamp_iso() -> bool:
    print("🧪 Checking current_timestamp_iso output")
    value = current_timestamp_iso()
    print(f"   🕒 now: {value}")
    if not is_isoformat_timestamp(value):
        print("   ❌ current_timestamp_iso did not return an ISO8601 string")
        return False
    if not value.endswith('Z'):
        print("   ❌ Timestamp is missing Zulu suffix")
        return False
    print("   ✅ current_timestamp_iso emits RFC3339 timestamps")
    return True


def check_iso_from_epoch_millis() -> bool:
    print("\n🧪 Checking iso_from_epoch_millis conversion")
    epoch_ms = 1732473600000  # 2024-11-24T00:00:00Z
    value = iso_from_epoch_millis(epoch_ms)
    print(f"   🗓️  converted: {value}")
    if value != "2024-11-24T00:00:00.000Z":
        print("   ❌ iso_from_epoch_millis conversion mismatch")
        return False
    print("   ✅ iso_from_epoch_millis converts milliseconds to RFC3339")
    return True


def main() -> None:
    success = check_current_timestamp_iso() and check_iso_from_epoch_millis()
    if success:
        print("\n✅ Cypher timestamp helpers are behaving correctly!")
    else:
        print("\n❌ Timestamp helper regression detected!")


if __name__ == "__main__":
    main()
