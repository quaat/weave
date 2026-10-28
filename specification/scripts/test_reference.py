#!/usr/bin/env python3
"""Run the unchanged upstream tests from their required working directory."""
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "reference" / "prototype"
    result = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-q"],
        cwd=root,
        check=False,
    )
    raise SystemExit(result.returncode)
