#!/usr/bin/env python3
"""Entry point.

    python run_bridge.py doctor     check the setup
    python run_bridge.py probe      see what the adapter reads from the chat
    python run_bridge.py run        start Edge and watch the chat
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from copilot_bridge.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
