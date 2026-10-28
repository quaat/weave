#!/usr/bin/env python3
"""Repository shortcut for the portable Weave skill runner."""
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
runpy.run_path(str(Path(__file__).resolve().parents[1] / ".agents/skills/weave/scripts/weave.py"), run_name="__main__")
