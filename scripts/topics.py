#!/usr/bin/env python3
"""Invoke the current task-local topic tools with one stdin JSON request."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from textpicos.content.topic_tools import main

if __name__ == "__main__":
    raise SystemExit(main())
