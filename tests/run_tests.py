"""Test runner — discovers and runs all hub tests.

Usage:
    python3 tests/run_tests.py
    python3 tests/run_tests.py -v          # verbose
"""
import sys
import unittest
from pathlib import Path

# Ensure repo root is on the path so test modules can import hub, db, etc.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

loader = unittest.TestLoader()
suite = loader.discover(start_dir=str(Path(__file__).parent), pattern="test_*.py")

runner = unittest.TextTestRunner(verbosity=2 if "-v" in sys.argv else 1)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
