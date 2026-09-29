#!/usr/bin/env python3
"""Run the Python test suite (no browser needed).

    python run_tests.py            all tests
    python run_tests.py protocol   only tests/test_protocol.py
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    pattern = f"test_{sys.argv[1]}.py" if len(sys.argv) > 1 else "test_*.py"
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=pattern, top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
