#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from remote.controller import resolve_byte_range


class TestRemoteController(unittest.TestCase):
    def test_resolve_byte_range_accepts_common_browser_requests(self):
        self.assertIsNone(resolve_byte_range(None, 1000))
        self.assertEqual(resolve_byte_range("bytes=100-199", 1000), (100, 199))
        self.assertEqual(resolve_byte_range("bytes=100-", 1000), (100, 999))
        self.assertEqual(resolve_byte_range("bytes=-200", 1000), (800, 999))

    def test_resolve_byte_range_clamps_suffix_to_file_size(self):
        self.assertEqual(resolve_byte_range("bytes=-1500", 1000), (0, 999))

    def test_resolve_byte_range_rejects_invalid_ranges(self):
        invalid_ranges = [
            "items=0-1",
            "bytes=500-100",
            "bytes=1000-1001",
            "bytes=-0",
        ]

        for range_header in invalid_ranges:
            with self.subTest(range_header=range_header):
                with self.assertRaises(ValueError):
                    resolve_byte_range(range_header, 1000)


if __name__ == "__main__":
    unittest.main()