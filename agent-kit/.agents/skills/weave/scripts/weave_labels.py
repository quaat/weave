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
  named ``status``, no member other than ``claim_label`` holds a label, and no
  value is any other upper-case status word (``PASSED``, ``CHECKED``, ...);
  the only upper-case word values that are not claims are listed in
  ``NON_CLAIM_WORDS``, and user-chosen names under ``IDENTIFIER_MEMBERS`` are
  not checked.
* Text: a claim is an unindented line that begins with its exact label,
  followed by the statement (``LABEL statement``, the established console form;
  the six labels are distinct as prefixes). Every other unindented line has one
  of a closed set of forms: a blank line, a line that begins with one of
  ``NON_CLAIM_PREFIXES`` (``tool status:``, ``runtime status:``, ``result:``,
  ``raw output (``, ``error:``, ...), a diagnostic header
  (``file:line:column: CODE (RULE) [stage]`` with a mapped code and its principal
  rule, or ``file: TOOL_ERROR [stage]``), a JSON object (linted with
  ``lint_json``), or a non-empty prefix ending with a separator that a caller
  declares for its own output (the demos declare theirs). No such line carries a
  label or another upper-case status word, except the tool status word right
  after ``tool status:`` (``TOOL_STATUS_WORDS``). Indented lines belong to the line above,
  and raw output of another tool is printed indented under a ``raw output`` line.

``lint_json`` and ``lint_text`` check these rules and return one message per
violation; an empty list means the output names claims only with the six labels.
Diagnostics and raw tool output (the prototype's own console text, unittest
output) are not claims and are not linted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

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

# An upper-case status word: a whole string value such as "PASSED", "NOT PROVED" or
# "CHECKED LOWERING". Codes and identifiers with digits or lower case (E320, P421, N0,
# checkout) do not match.
_STATUS_WORD = re.compile(r"[A-Z][A-Z _/]*[A-Z]")
# Upper-case word values that are not claims: ACCEPT is the teaching manifest's expected
# outcome for an accepted case (``examples`` results), an expectation, not a label.
NON_CLAIM_WORDS = frozenset({"ACCEPT"})
# Members whose string values (or lists of strings) are user-chosen identifiers or paths,
# which the grammar lets be upper case (``\w+``): invariant, property, transition, flow,
# function, entry, enum type and case names, and file paths, as they occur in the runner's,
# the demos' and the envelopes' output. They are names, never claims, so the status-word
# check does not apply to them.
IDENTIFIER_MEMBERS = frozenset({
    "invariants", "properties", "property", "trace", "marking", "flows", "functions", "entry",
    "return_type", "return_tag", "outcome", "net_transitions", "name",
    "file", "net", "source", "certificate", "lowered_from", "prototype", "missing",
})


def _identifiers(value) -> bool:
    return isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value))

# The unindented non-claim lines the runner prints, a closed set: tool status
# (doctor, examples, test), runtime status, result and stats (run-pure), the
# prototype directory and missing files (doctor), a written certificate (analyze),
# the header of raw output (test) and an error line. (The JSON detail of a failed
# teaching expectation is an unindented JSON object, linted as JSON.)
NON_CLAIM_PREFIXES = ("tool status: ", "runtime status: ", "result: ", "stats: ", "prototype: ", "missing: ",
                      "certificate: ", "raw output (", "error: ")
# The one place a non-claim line may carry a status word: the word right after
# "tool status: " is the tool status itself (doctor, examples, test).
TOOL_STATUS_WORDS = ("PASS", "FAIL", "READY", "NOT READY")
# A whole upper-case status token: a word of the six labels or a known non-canonical
# status word (PASSED, PASS, FAIL, FAILED, RECHECKED, NOT PROVED, CHECKED, EXECUTED, ...).
# Outside a claim line no line carries one, except the tool status word above.
_STATUS_TOKEN = re.compile(r"(?<![A-Za-z0-9_])(?:PROVED|CHECKED|SCRIPTED|VIOLATED|ESTABLISHED|BOUNDS|PASSED|PASS|"
                           r"FAILED|FAIL|FAILURE|RECHECKED|EXECUTED|VERIFIED|BOUNDED|EXPECTED)(?![A-Za-z0-9_])")
# The diagnostic code-to-rule map the runner uses (assets/diagnostics.json in this skill).
_CODES = json.loads((Path(__file__).resolve().parents[1] / "assets" / "diagnostics.json")
                    .read_text(encoding="utf-8"))["codes"]
# A diagnostic header as weave.py print_diagnostic writes it: ``file:line:column: CODE
# (RULE) [stage]`` for a checker or pure-extension code, whose span always has a line and
# column; ``file: TOOL_ERROR [stage]`` (or ``: TOOL_ERROR [stage]``) for a tool error,
# which has no span and no rule. The file is a path without whitespace; the code must be
# in the map and the rule must be the code's principal rule from the map.
_DIAGNOSTIC = re.compile(r"(?P<location>[^\s:]*(?::\d+:\d+)?): (?P<code>[A-Z][A-Z0-9_]*)"
                         r"(?: \((?P<rule>[^()\s]+)\))? \[[a-z-]+\]")


def is_diagnostic_header(line: str) -> bool:
    found = _DIAGNOSTIC.fullmatch(line)
    if found is None or found["code"] not in _CODES:
        return False
    spanned = found["location"].count(":") == 2
    if found["code"] == "TOOL_ERROR":
        return not spanned and found["rule"] is None and _CODES["TOOL_ERROR"]["rule"] is None
    return spanned and found["rule"] is not None and found["rule"] == _CODES[found["code"]]["rule"]
# A declared prefix: a non-empty heading that ends with a separator.
_DECLARED_PREFIX = re.compile(r"\S.*?(?::|: | - )")
# Words that begin a claim, in any case or spelling: the label words and the
# prototype's and earlier kit's non-canonical ones. A line starting with one of
# them must start with an exact label.
_CLAIM_WORD = re.compile(r"(?i)^(?:not[\s_-]*)?(?:proved|checked|scripted|violated|established|passed|pass|"
                         r"failed|recheck(?:ed)?|executed|verified|bounded)\b")
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
            elif key in IDENTIFIER_MEMBERS and _identifiers(value):
                continue
            elif isinstance(value, str):
                errors += _value_errors(value, where)
            else:
                errors += lint_json(value, where)
    elif isinstance(document, list):
        for index, value in enumerate(document):
            where = f"{pointer}/{index}"
            if isinstance(value, str):
                errors += _value_errors(value, where)
            else:
                errors += lint_json(value, where)
    return errors


def _value_errors(value: str, where: str) -> list[str]:
    """A string outside claim_label: never a label, and never another upper-case status word."""
    if value in RESULT_LABELS:
        return [f"{where}: result label {value!r} outside a claim_label member"]
    if _STATUS_WORD.fullmatch(value) and value not in NON_CLAIM_WORDS:
        return [f"{where}: status word {value!r} presents a claim without one of the six result labels"]
    return []


def text_claims(text: str) -> list[tuple[int, str]]:
    """``(line number, label)`` for each unindented line that presents a claim with one of the six labels."""
    claims = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _CLAIM_LINE.match(line)
        if match:
            claims.append((number, match.group(1)))
    return claims


def lint_text(text: str, extra_prefixes: tuple[str, ...] = ()) -> list[str]:
    """Violations of the text rules: every unindented line is a claim with an exact label or a declared form.

    ``extra_prefixes`` are non-claim line prefixes a caller declares for its own output
    (a demo's headings); they may not begin with a claim word.
    """
    for prefix in extra_prefixes:
        if not isinstance(prefix, str) or not _DECLARED_PREFIX.fullmatch(prefix):
            raise ValueError(f"declared prefix {prefix!r} must be a non-empty heading ending with ':', ': ' or ' - '")
        if _CLAIM_WORD.match(prefix):
            raise ValueError(f"declared prefix {prefix!r} begins with a claim word")
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line or line[0].isspace() or _CLAIM_LINE.match(line):
            continue
        if _CLAIM_WORD.match(line):
            errors.append(f"line {number}: {line!r} presents a claim without an exact result label")
        elif line.startswith("{"):
            # Only a JSON object (a failed example's detail), linted as JSON.
            try:
                document = json.loads(line)
            except ValueError:
                document = None
            if not isinstance(document, dict):
                errors.append(f"line {number}: {line!r} starts with '{{' but is not a JSON object")
            else:
                errors += [f"line {number}: {e}" for e in lint_json(document)]
        elif line.startswith(NON_CLAIM_PREFIXES + tuple(extra_prefixes)) or is_diagnostic_header(line):
            body = line
            if line.startswith("tool status: "):
                rest = line[len("tool status: "):]
                word = next((w for w in sorted(TOOL_STATUS_WORDS, key=len, reverse=True)
                             if rest == w or rest.startswith(w + " ")), None)
                body = rest[len(word):] if word else rest
            token = _STATUS_TOKEN.search(body)
            if token:
                errors.append(f"line {number}: {line!r} is not a claim but carries the status word {token.group()!r}")
        else:
            errors.append(f"line {number}: {line!r} is not a claim, a declared non-claim line or a diagnostic")
    return errors
