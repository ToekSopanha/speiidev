#!/usr/bin/env python3
"""Run the full automated unit test suite for SpeiiDev."""
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    print("🧪 Running SpeiiDev Automated Test Suite...")
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT_DIR / "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
