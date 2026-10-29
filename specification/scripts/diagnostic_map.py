#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Derive the diagnostic codes a checker's source can emit, and find codes missing from the map.

A code is any string literal of the form E000 or P000 in the scanned Python
sources, and any string literal stored under a ``"code"`` key in a dict literal
(such as the agent kit's ``TOOL_ERROR``). Literals are read from the syntax
tree, never by running the sources. This over-approximates what can be emitted
(a literal compared against an error's code also counts), so a code the
checker can raise is never missed.

``python scripts/diagnostic_map.py`` checks the pinned prototype and, when it is
present in the repository, the agent kit; it exits 1 and names any unmapped
code.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "diagnostics.json"
CODE = re.compile(r"[EP]\d{3}")
PROTOTYPE = [ROOT / "reference/prototype" / name for name in
             ("checker.py", "coloured.py", "durable.py", "simulate.py", "verify_certificate.py")]
KIT_SCRIPTS = ROOT.parent / "agent-kit/.agents/skills/weave/scripts"


def emitted_codes(paths) -> set[str]:
    """Diagnostic codes written as literals in the given Python sources."""
    codes: set[str] = set()
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and CODE.fullmatch(node.value):
                codes.add(node.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (isinstance(key, ast.Constant) and key.value == "code"
                            and isinstance(value, ast.Constant) and isinstance(value.value, str)):
                        codes.add(value.value)
    return codes


def load_map(path: Path = MAP) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))["codes"]


def unmapped(paths, codes: dict) -> list[str]:
    """Codes the sources can emit that the map does not list."""
    return sorted(emitted_codes(paths) - set(codes))


def kit_sources() -> list[Path]:
    return sorted(KIT_SCRIPTS.rglob("*.py")) if KIT_SCRIPTS.is_dir() else []


def main() -> int:
    codes = load_map()
    missing = unmapped(PROTOTYPE + kit_sources(), codes)
    if missing:
        print("Unmapped diagnostic codes: " + ", ".join(missing), file=sys.stderr)
        return 1
    print(f"PASS: every emitted diagnostic code is in {MAP.name} ({len(codes)} codes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
