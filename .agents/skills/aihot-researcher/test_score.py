#!/usr/bin/env python3
"""Ensure retired scoring refuses without reading inputs or writing rankings."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).parent


def test_retired_scoring_refuses_without_output() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        output = root / "ranked.json"
        command = [sys.executable, "-S", str(HERE / "score.py"),
                   "--raw", str(root / "nonexistent-raw.json"),
                   "--scored", str(root / "nonexistent-scores.json"),
                   "--config", str(root / "nonexistent-config.json"),
                   "--out", str(output)]
        result = subprocess.run(command, text=True, capture_output=True)
        assert result.returncode == 2, result.stderr
        assert not result.stdout
        assert json.loads(result.stderr)["error"] == "AIHOT_SCORING_RETIRED"
        assert not output.exists(), "Retired scoring must not create rankings"
        output.write_text("existing result must remain unchanged", encoding="utf-8")
        result = subprocess.run(command, text=True, capture_output=True)
        assert result.returncode == 2
        assert json.loads(result.stderr)["error"] == "AIHOT_SCORING_RETIRED"
        assert output.read_text(encoding="utf-8") == "existing result must remain unchanged"


if __name__ == "__main__":
    test_retired_scoring_refuses_without_output()
    print("[test_score] PASS: retired scoring refused; no output created or overwritten")
