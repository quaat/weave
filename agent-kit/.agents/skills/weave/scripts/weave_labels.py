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
  named ``status``; a member whose name contains a verdict word appears only at
  the paths, in the outputs and with the values ``ALLOWED_VERDICT_NAMES`` lists;
  and no string value is a label, contains an upper-case status word or begins
  with a verdict word (see ``lint_json``).
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
  after ``tool status:`` (``TOOL_STATUS_WORDS``), and the text after its prefix
  does not begin with a verdict word, except a declared application outcome. Indented lines belong to the line above,
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
    "return_type", "return_tag", "net_transitions", "name",
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
# Words that begin a claim, in any case: the six labels' words and the usual verdict
# words. A text line, the text after any non-claim prefix, or a JSON string outside the
# exemptions that begins with one of them (after leading whitespace and quotes, and not
# followed by a letter or digit) states a result; only a claim line may, and it must
# begin with an exact label.
CLAIM_LEXICON = ("proved", "proven", "unproved", "checked", "scripted", "violated", "not established",
                 "established", "verified", "passed", "pass", "success", "succeeded", "ok", "fail", "failed",
                 "failure", "holds", "rechecked", "recheck", "executed", "bounded")
_CLAIM_WORD = re.compile(r"(?i)(?:not[\s_-]*)?(?:" + "|".join(sorted(
    (re.escape(w).replace(r"\ ", r"[\s_-]+") for w in CLAIM_LEXICON), key=len, reverse=True)) + r")(?![A-Za-z0-9])")
_LEADING_NOISE = " \t\"'`"


def _begins_with_verdict(text: str) -> bool:
    return _CLAIM_WORD.match(text.lstrip(_LEADING_NOISE)) is not None


# Member names that read as a verdict: a name whose parts (split on '_', '-' and camelCase,
# case-insensitive) include one of these words. In kit JSON the only verdict position is
# claim_label; runtime_status is a run's status and ok the tool status. Every other
# verdict-like name is an error unless ALLOWED_VERDICT_NAMES lists its exact path, the
# output it occurs in and its value domain.
VERDICT_NAME_WORDS = frozenset({
    "proved", "proven", "proof", "proofs", "verified", "verify", "established", "holds", "passed", "pass",
    "success", "successful", "succeeded", "result", "results", "verdict", "verdicts", "outcome", "outcomes",
    "claim", "claims", "label", "labels", "status", "statuses", "check", "checks", "checked", "conclusion",
    "conclusions", "finding", "findings", "assessment", "evaluation", "judgement", "judgment", "decision",
    "violated", "violation", "scripted", "fail", "failed", "failure", "rechecked", "executed",
})
APPLICATION_OUTCOMES = ("Ok", "Err", "Unknown")


def _command(*names):
    return lambda root: isinstance(root, dict) and root.get("command") in names


def _demo(name):
    return lambda root: isinstance(root, dict) and root.get("demo") == name


def _envelope(root):
    return isinstance(root, dict) and root.get("format") == ENVELOPE_FORMAT


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool)


# (path with '*' for any array index, which output it occurs in, allowed value), each the
# only place the name may appear. The JSON detail line of a failed `examples` expectation
# is linted as /results/<n> of an `examples` result.
ALLOWED_VERDICT_NAMES = (
    ("/runs/*/outcome", _command("simulate"), lambda v: v in APPLICATION_OUTCOMES),
    ("/results", _command("examples"), lambda v: isinstance(v, list) and all(isinstance(r, dict) and "ok" in r for r in v)),
    ("/results/*/outcome", _command("examples"), lambda v: v in APPLICATION_OUTCOMES),
    ("/checks", _command("examples"), _count),
    ("/passed", _command("examples"), _count),
    ("/result", _command("run-pure"), lambda v: not isinstance(v, (str, dict))),
    ("/check", _command("run-pure"), lambda v: isinstance(v, dict) and "claim_label" in v),
    ("/check", _demo("merge_sort"), lambda v: isinstance(v, dict) and "claim_label" in v),
    ("/requested_outcome", _demo("tiny_shop"), lambda v: v in APPLICATION_OUTCOMES + ("all",)),
    ("/scenarios/*/outcome", _demo("tiny_shop"), lambda v: v in APPLICATION_OUTCOMES),
    ("/claim", _envelope, lambda v: isinstance(v, dict) and "claim_label" not in v),
)
# Members whose keys are user-chosen place names (markings), not member names.
NAME_KEYED_MEMBERS = frozenset({"marking", "final_marking", "expected", "actual"})


def _verdict_name(key: str) -> bool:
    """A member name with a verdict word among its parts (``check_result``, ``isProven``, ``holds``)."""
    return bool({part.lower() for part in re.split(r"_|-|(?<=[a-z])(?=[A-Z])", key)} & VERDICT_NAME_WORDS)


def _allowed_name(path: str, root, value) -> bool:
    shape = re.sub(r"/\d+(?=/|$)", "/*", path)
    return any(shape == pattern and context(root) and allowed(value)
               for pattern, context, allowed in ALLOWED_VERDICT_NAMES)


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


# Quotations in evidence envelopes (format weave-evidence-envelope-v1), the only JSON
# strings outside claim_label that may contain a status token: each entry of the top-level
# ``assumptions`` is a verbatim, cited quotation of the specification or a producer's
# docstring (evidence/weave_evidence/conditions.py; one quotes "PROVED labels apply only
# ..." from checker.py), and ``claim.statement`` is the wrapped file's own wording (for
# example the prototype's "VIOLATED <property> ..." in report.json). Both are re-derived
# and hash-checked by the evidence verifier; neither is the envelope's claim, which is
# ``claim_label``. They may contain a status token in their wording, but are never a bare
# label or status word.
ENVELOPE_FORMAT = "weave-evidence-envelope-v1"
ENVELOPE_QUOTATIONS = (re.compile(r"/assumptions/\d+"), re.compile(r"/claim/statement"))


def lint_json(document, pointer: str = "", root=None) -> list[str]:
    """Violations of the JSON claim rules in ``document``; an empty list when there are none.

    The only verdict position is ``claim_label``, exactly one of the six labels.

    1. Member names: no ``status``; ``runtime_status`` only with a runtime status; any other
       member whose name contains a verdict word (``VERDICT_NAME_WORDS``) is an error unless
       ``ALLOWED_VERDICT_NAMES`` lists its path, output and value domain.
    2. String values: none is a label or an upper-case status word, contains a status word
       as a whole upper-case token, or begins (after whitespace and quotes, in any case) with
       a verdict word (``CLAIM_LEXICON``).

    Exempt from rule 2: raw members (``RAW_MEMBERS``), user-chosen names
    (``IDENTIFIER_MEMBERS``; marking keys under ``NAME_KEYED_MEMBERS``), the teaching
    manifest's ``ACCEPT`` and, in an evidence envelope, its quotations
    (``ENVELOPE_QUOTATIONS``), which may contain a token but are never a bare label.
    ``root`` is the whole output, when ``document`` is part of one (``pointer`` is then
    its path); it decides which allowed paths apply. The runner's JSON has no tool status
    string: ``ok`` is a boolean.
    """
    root = document if root is None else root
    return _lint(document, pointer, root, _envelope(root))


def _lint(document, pointer: str, root, quotations: bool, name_keyed: bool = False) -> list[str]:
    errors = []
    if isinstance(document, dict):
        items = [(f"{pointer}/{key}", key, value) for key, value in document.items()]
    elif isinstance(document, list):
        items = [(f"{pointer}/{index}", None, value) for index, value in enumerate(document)]
    else:
        return errors
    for where, key, value in items:
        if key in RAW_MEMBERS:
            continue
        if key == "claim_label":
            if value not in RESULT_LABELS:
                errors.append(f"{where}: claim label {value!r} is not one of the six result labels")
            continue
        if key == "runtime_status":
            if value is not None and value not in RUNTIME_STATUSES:
                errors.append(f"{where}: runtime status {value!r} is not one of {', '.join(RUNTIME_STATUSES)}")
            continue
        if key == "status":
            errors.append(f"{where}: a member named 'status' ({value!r}) does not say whether it is a claim; "
                          "use claim_label for a claim, ok for tool status, runtime_status for a run")
            continue
        if key is not None and not name_keyed and _verdict_name(key):
            if not _allowed_name(where, root, value):
                errors.append(f"{where}: member name {key!r} reads as a verdict here; claims use claim_label only")
                continue
            if isinstance(value, str):
                continue  # an allow-listed application outcome; its value domain is already checked
        if key in IDENTIFIER_MEMBERS and _identifiers(value):
            continue
        if isinstance(value, str):
            quoted = quotations and any(q.fullmatch(where) for q in ENVELOPE_QUOTATIONS)
            errors += _value_errors(value, where, quoted)
        else:
            errors += _lint(value, where, root, quotations, name_keyed=key in NAME_KEYED_MEMBERS)
    return errors


def _value_errors(value: str, where: str, quoted: bool = False) -> list[str]:
    """A string outside claim_label: never a label or status word, no status token, no leading verdict word.

    A ``quoted`` string (an envelope quotation) may contain a status token or begin with
    one in its wording, but is still never a bare label or status word.
    """
    if value in RESULT_LABELS:
        return [f"{where}: result label {value!r} outside a claim_label member"]
    if value in NON_CLAIM_WORDS:
        return []
    if _STATUS_WORD.fullmatch(value.strip(_LEADING_NOISE)):
        return [f"{where}: status word {value!r} presents a claim without one of the six result labels"]
    if quoted:
        return []
    if _begins_with_verdict(value):
        return [f"{where}: {value!r} begins with a verdict word outside a claim_label member"]
    token = _STATUS_TOKEN.search(value)
    if token:
        return [f"{where}: {value!r} contains the status word {token.group()!r} outside a claim_label member"]
    return []


def text_claims(text: str) -> list[tuple[int, str]]:
    """``(line number, label)`` for each unindented line that presents a claim with one of the six labels."""
    claims = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _CLAIM_LINE.match(line)
        if match:
            claims.append((number, match.group(1)))
    return claims


def _declared(entry) -> tuple[str, tuple[str, ...]]:
    """A declared prefix: a heading, or (heading, the application outcomes allowed as its first word)."""
    prefix, words = (entry, ()) if isinstance(entry, str) else entry
    if not isinstance(prefix, str) or not _DECLARED_PREFIX.fullmatch(prefix):
        raise ValueError(f"declared prefix {prefix!r} must be a non-empty heading ending with ':', ': ' or ' - '")
    if _begins_with_verdict(prefix):
        raise ValueError(f"declared prefix {prefix!r} begins with a claim word")
    if not set(words) <= set(APPLICATION_OUTCOMES):
        raise ValueError(f"declared prefix {prefix!r} may allow only application outcomes, not {words!r}")
    return prefix, tuple(words)


def lint_text(text: str, extra_prefixes=()) -> list[str]:
    """Violations of the text rules: every unindented line is a claim with an exact label or a declared form.

    ``extra_prefixes`` are non-claim line prefixes a caller declares for its own output (a
    demo's headings): a heading, or ``(heading, outcomes)`` when the heading is followed by
    an application outcome name (``Ok``, ``Err``, ``Unknown``).
    """
    declared = [_declared(entry) for entry in extra_prefixes]
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line or line[0].isspace() or _CLAIM_LINE.match(line):
            continue
        if _begins_with_verdict(line):
            errors.append(f"line {number}: {line!r} presents a claim without an exact result label")
            continue
        if line.startswith("{"):
            # Only a JSON object: the detail of a failed `examples` expectation, linted as JSON.
            try:
                document = json.loads(line)
            except ValueError:
                document = None
            if not isinstance(document, dict):
                errors.append(f"line {number}: {line!r} starts with '{{' but is not a JSON object")
            else:
                errors += [f"line {number}: {e}" for e in
                           lint_json(document, "/results/0", {"command": "examples", "results": [document]})]
            continue
        runner = next((p for p in NON_CLAIM_PREFIXES if line.startswith(p)), None)
        own = next(((p, w) for p, w in declared if line.startswith(p)), None)
        if runner is None and own is None and not is_diagnostic_header(line):
            errors.append(f"line {number}: {line!r} is not a claim, a declared non-claim line or a diagnostic")
            continue
        body, outcomes = line, ()
        if runner == "tool status: ":
            rest = line[len(runner):]
            word = next((w for w in sorted(TOOL_STATUS_WORDS, key=len, reverse=True)
                         if rest == w or rest.startswith(w + " ")), None)
            body = rest[len(word):].lstrip() if word else rest
        elif runner is not None:
            body = line[len(runner):]
        elif own is not None:
            body, outcomes = line[len(own[0]):], own[1]
        first = body.lstrip(_LEADING_NOISE).split(" ", 1)[0]
        token = _STATUS_TOKEN.search(body)
        if token:
            errors.append(f"line {number}: {line!r} is not a claim but carries the status word {token.group()!r}")
        elif (runner is not None or own is not None) and first not in outcomes and _begins_with_verdict(body):
            errors.append(f"line {number}: {line!r} is not a claim but its text begins with a verdict word")
    return errors
