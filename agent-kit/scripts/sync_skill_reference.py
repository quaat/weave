#!/usr/bin/env python3
"""Copy the authoritative kit guide, and the specification's diagnostic map, into the portable skill."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
shutil.copyfile(root / "docs/weave.md", root / ".agents/skills/weave/references/weave.md")
print("Synchronized the portable Weave language guide")
# The code-to-rule map is maintained in the specification; the skill carries a byte-identical copy.
diagnostic_map = root.parent / "specification/diagnostics.json"
if diagnostic_map.is_file():
    shutil.copyfile(diagnostic_map, root / ".agents/skills/weave/assets/diagnostics.json")
    print("Synchronized the diagnostic code-to-rule map")
