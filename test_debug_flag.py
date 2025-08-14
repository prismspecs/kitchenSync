#!/usr/bin/env python3
"""
Test script to verify --debug flag works correctly in collaborator.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_debug_override():
    """Test that --debug command line flag properly enables debug mode"""
    print("🧪 Testing --debug flag override...")

    # Test without debug flag
    print("\n1. Testing normal mode (no --debug flag):")
    from collaborator import CollaboratorPi

    try:
        collaborator_normal = CollaboratorPi(
            "collaborator_config.ini", debug_override=False
        )
        debug_normal = collaborator_normal.config.debug_mode
        print(f"   Debug mode: {debug_normal}")
    except Exception as e:
        print(f"   Error: {e}")

    # Test with debug flag
    print("\n2. Testing with debug_override=True:")
    try:
        collaborator_debug = CollaboratorPi(
            "collaborator_config.ini", debug_override=True
        )
        debug_override = collaborator_debug.config.debug_mode
        print(f"   Debug mode: {debug_override}")

        if debug_override:
            print("   ✅ Debug override working correctly!")
        else:
            print("   ❌ Debug override not working")

    except Exception as e:
        print(f"   Error: {e}")

    print("\n3. Command line usage:")
    print("   python3 collaborator.py --debug")
    print("   Should now properly enable debug mode from startup")


if __name__ == "__main__":
    test_debug_override()
