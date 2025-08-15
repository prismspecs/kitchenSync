#!/usr/bin/env python3
"""
Test the long event function with keepalives
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.schedule import Schedule


def test_long_event():
    """Test creating a long relay event with keepalives"""

    schedule = Schedule("long_event_test.json")
    schedule.clear_schedule()

    print("🔧 Testing long relay event with keepalives...")

    # Test a 15-second event (should get keepalives at 4s, 8s, 12s)
    schedule.add_relay_long_event(
        start_time=10.0,
        end_time=25.0,  # 15 second duration
        relay_output=1,
        velocity=127,
    )

    # Test a short event (no keepalives needed)
    schedule.add_relay_long_event(
        start_time=30.0,
        end_time=32.0,  # 2 second duration
        relay_output=2,
        velocity=100,
    )

    schedule.save_schedule()
    print(f"✅ Created test schedule: {schedule.schedule_file}")
    print("📋 Schedule contents:")
    schedule.print_schedule()


if __name__ == "__main__":
    test_long_event()
