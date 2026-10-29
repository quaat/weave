# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""The six result labels, the claim structure of runner output, and a lint for it (quaat/weave#8).

The labels are the first column of the "Result vocabulary" table in the
specification (``verification.rst``), verbatim. A claim carries exactly one of
them; anything else the runner reports is not a claim and is never written with
a label:

* JSON: a claim is an object with a ``claim_label`` member. Tool status is the
  boolean ``ok`` (and the exit code); the status of a runtime run is
  ``runtime_status`` (``waiting``, ``timed out`` or ``completed``). No member is
  named ``status``, and no member other than ``claim_label`` holds a label.
* Text: a claim is an unindented line that begins with its label, followed by
  the statement (``LABEL statement``, the established console form; the six
  labels are distinct as prefixes). Non-claim lines begin with a lower-case name
  (``tool status:``, ``runtime status:``, ``result:``, ...) or a diagnostic
  location; indented lines belong to the line above, and raw output of another
  tool is printed indented under a ``raw output`` line.

``lint_json`` and ``lint_text`` check these rules and return one message per
violation; an empty list means the output names claims only with the six labels.
Diagnostics and raw tool output (the prototype's own console text, unittest
output) are not claims and are not linted.
"""
from __future__ import annotations

import re

RESULT_LABELS = (
    "PROVED",
    "CHECKED WITHIN BOUNDS",
    "CHECKED flow",
    "SCRIPTED / passed scenario",
    "VIOLATED",
    "NOT ESTABLISHED",
)
PROVED, BOUNDED, FLOW, SCRIPTED, VIOLATED, NOT_ESTABLISHED = RESULT_LABELS
RUNTIME_STATUSES = ("waiting", "timed out", "completed")

# Members whose values are raw output of another tool, diagnostics, or data the
# producer copied unchanged; they hold no claim and are not linted.
RAW_MEMBERS = frozenset({"diagnostic", "output", "upstream_output", "events", "detail", "context"})

# An unindented text line whose first word is upper case (two or more capitals)
# presents a claim, as the prototype's console lines (PROVED, CHECKED, PASSED,
# RECHECKED, NOT PROVED) do. A path such as ``Inventory.weave:3:1`` or a code
# such as ``E204`` does not match.
_PRESENTED = re.compile(r"^[A-Z][A-Z_]+(?=[\s:]|$)")
_CLAIM_LINE = re.compile("^(" + "|".join(re.escape(label) for label in RESULT_LABELS) + r")(?=[ :]|$)")


def labelled(label: str, **fields) -> dict:
    """A claim object; refuses any label outside the six."""
    if label not in RESULT_LABELS:
        raise ValueError(f"{label!r} is not one of the six result labels")
    return {"claim_label": label, **fields}


def claim_line(label: str, statement: str) -> str:
    if label not in RESULT_LABELS:
        raise ValueError(f"{label!r} is not one of the six result labels")
    return f"{label} {statement}"


def json_claims(document, pointer: str = "") -> list[tuple[str, object]]:
    """``(JSON Pointer, label)`` for every ``claim_label`` member, in document order, outside raw members."""
    found = []
    if isinstance(document, dict):
        for key, value in document.items():
            if key in RAW_MEMBERS:
                continue
            where = f"{pointer}/{key}"
            if key == "claim_label":
                found.append((where, value))
            else:
                found += json_claims(value, where)
    elif isinstance(document, list):
        for index, value in enumerate(document):
            found += json_claims(value, f"{pointer}/{index}")
    return found


def lint_json(document, pointer: str = "") -> list[str]:
    """Violations of the JSON claim rules in ``document``; an empty list when there are none."""
    errors = []
    if isinstance(document, dict):
        for key, value in document.items():
            if key in RAW_MEMBERS:
                continue
            where = f"{pointer}/{key}"
            if key == "claim_label":
                if value not in RESULT_LABELS:
                    errors.append(f"{where}: claim label {value!r} is not one of the six result labels")
            elif key == "status":
                errors.append(f"{where}: a member named 'status' ({value!r}) does not say whether it is a claim; "
                              "use claim_label for a claim, ok for tool status, runtime_status for a run")
            elif key == "runtime_status":
                if value is not None and value not in RUNTIME_STATUSES:
                    errors.append(f"{where}: runtime status {value!r} is not one of {', '.join(RUNTIME_STATUSES)}")
            elif isinstance(value, str) and value in RESULT_LABELS:
                errors.append(f"{where}: result label {value!r} outside a claim_label member")
            else:
                errors += lint_json(value, where)
    elif isinstance(document, list):
        for index, value in enumerate(document):
            where = f"{pointer}/{index}"
            if isinstance(value, str) and value in RESULT_LABELS:
                errors.append(f"{where}: result label {value!r} outside a claim_label member")
            else:
                errors += lint_json(value, where)
    return errors


def text_claims(text: str) -> list[tuple[int, str]]:
    """``(line number, label)`` for each unindented line that presents a claim with one of the six labels."""
    claims = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _CLAIM_LINE.match(line)
        if match:
            claims.append((number, match.group(1)))
    return claims


def lint_text(text: str) -> list[str]:
    """Violations of the text claim rules: an unindented upper-case first word that does not begin a label."""
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        if _PRESENTED.match(line) and not _CLAIM_LINE.match(line):
            errors.append(f"line {number}: {line!r} presents a claim without one of the six result labels")
    return errors
