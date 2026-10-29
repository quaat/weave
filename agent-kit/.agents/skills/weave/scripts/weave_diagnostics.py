# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Build the runner's weave-diagnostic-v1 documents (standard library only).

The code-to-rule map is ``assets/diagnostics.json``, a byte-identical copy of the
specification's ``diagnostics.json`` (``scripts/sync_skill_reference.py`` in the
kit refreshes it). Checker errors bring their own spans; pure-extension errors
carry a line, which becomes the span of that statement.
"""
from __future__ import annotations

import json
from pathlib import Path

FORMAT = "weave-diagnostic-v1"
MAP_PATH = Path(__file__).resolve().parents[1] / "assets" / "diagnostics.json"
CODES = json.loads(MAP_PATH.read_text(encoding="utf-8"))["codes"]


def rules(code: str) -> dict:
    """The map entry of a code; an unmapped code is a defect, never silently given a rule."""
    if code not in CODES:
        raise KeyError(f"Diagnostic code {code} is not in {MAP_PATH.name}")
    return CODES[code]


def region(file: str, line: int, column: int, end_line: int, end_column: int) -> dict:
    return {"file": file, "start": {"line": line, "column": column}, "end": {"line": end_line, "column": end_column}}


def statement_region(file: str, source: str, line: int) -> dict:
    """The statement on ``line`` without indentation or comment; the whole source when there is none."""
    lines = source.splitlines()
    if 1 <= line <= len(lines):
        text = lines[line - 1].split("#", 1)[0].rstrip()
        if text.strip():
            return region(file, line, len(text) - len(text.lstrip()) + 1, line, len(text) + 1)
    if not lines:
        return region(file, 1, 1, 1, 1)
    return region(file, 1, 1, len(lines), len(lines[-1]) + 1)


def from_check_error(error, file: str, source: str, stage: str) -> dict:
    """A prototype CheckError, located against ``source``, with its rules from the map."""
    entry = rules(error.code)
    return error.diagnostic(str(file), source, stage, entry["rule"], entry["secondary_rules"], entry["category"])


def from_pure_error(error, file: str, source: str) -> dict:
    entry = rules(error.code)
    return {"format": FORMAT, "code": error.code, "category": entry["category"], "rule": entry["rule"],
            "secondary_rules": list(entry["secondary_rules"]), "severity": "error", "stage": error.stage,
            "message": error.message, "span": statement_region(str(file), source, error.line),
            "related": [], "details": {}}


def tool_error(message: str, file, stage: str) -> dict:
    """A runner failure outside the checker: no rule and no source span."""
    entry = rules("TOOL_ERROR")
    return {"format": FORMAT, "code": "TOOL_ERROR", "category": entry["category"], "rule": None,
            "secondary_rules": [], "severity": "error", "stage": stage, "message": message or "error",
            "span": None, "related": [], "details": {"file": str(file)}}


def location(diagnostic: dict) -> str:
    """``file:line:column`` of a diagnostic's primary span, or the file alone when it has none."""
    span = diagnostic.get("span")
    if span is None:
        return diagnostic["details"].get("file", "")
    return f"{span['file']}:{span['start']['line']}:{span['start']['column']}"
