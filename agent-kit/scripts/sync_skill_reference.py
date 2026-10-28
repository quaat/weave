#!/usr/bin/env python3
"""Copy the authoritative kit guide into the portable skill."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
shutil.copyfile(root / "docs/weave.md", root / ".agents/skills/weave/references/weave.md")
print("Synchronized the portable Weave language guide")
