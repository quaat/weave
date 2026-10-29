# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""The six result labels, the claim structure of runner output, and a lint for it (quaat/weave#8).

The labels are the first column of the "Result vocabulary" table in the
specification (``verification.rst``), verbatim. A claim carries exactly one of
them; anything else the runner reports is not a claim and is never written with
a label:

* JSON: a claim is an object with a ``claim_label`` member, the only place a
  verdict can appear. The JSON is a closed schema (``SCHEMA``): every path each
  runner command, demo and evidence envelope emits is declared with the kind of
  value it holds, and any undeclared path or value of another kind is an error.
  Tool status is the boolean ``ok`` (and the exit code); the status of a runtime
  run is ``runtime_status`` (``waiting``, ``timed out`` or ``completed``).
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
# An all-capitals token: a whole word of two or more capital letters, possibly joined by
# underscores (PASSED, SUCCESS, PROVEN, NOT, ESTABLISHED, TOOL_ERROR). Prose and the text
# after a non-claim prefix contain none, except those on PROSE_TOKENS; a label's words in
# prose are therefore findings too, since claims belong only in claim_label or a claim line.
_STATUS_TOKEN = re.compile(r"(?<![A-Za-z0-9_])[A-Z]{2,}(?:_[A-Z]+)*(?![A-Za-z0-9_])")
# All-capitals tokens that really occur in kit prose, each with where (enumerated from
# every output the tests produce; a new one fails the tests until it is listed here).
PROSE_TOKENS = {
    "OS": "run-pure /execution/scheduler and its runtime status line: 'cooperative, single OS thread'",
    "API": "examples /results/*/lesson, from the teaching manifest: 'An API changes state ...'",
}
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


ENVELOPE_FORMAT = "weave-evidence-envelope-v1"
TRACE_FORMAT = "weave-trace-v1"
APPLICATION_OUTCOMES = ("Ok", "Err", "Unknown")

# ------------------------------------------------------------------ closed JSON schema
#
# Every JSON path the kit emits, per output, with the kind of value it holds. A path not
# declared here, or a value of another kind, is an error: ``claim_label`` is the only
# place a verdict can appear, and every other member is named and typed below.
# ``*`` stands for any array index, or any key of a ``map`` (whose keys are user-chosen
# place names). The table is checked in both directions against real output by
# agent-kit/tests/test_result_labels.py: every real path must be declared, and every
# declared path must occur in some real output the tests produce.
#
# Kinds: ``label`` (exactly one of the six labels); ``("enum", values)``; ``identifier``
# (a user-chosen name, file path, version or hash; not inspected); ``prose`` (free text,
# checked by the verdict rules of ``_prose_errors``); ``quotation`` (an envelope's cited
# wording: may contain a status word, but is never a bare label or status word);
# ``integer``; ``boolean``; ``data`` (a computed value: numbers, Booleans and lists of
# them); ``expectation`` (a teaching expectation: ACCEPT, a mapped diagnostic code, or a
# marking of place counts); ``diagnostic`` (a weave-diagnostic-v1 document or a demo's
# error record; its message is tool text, not inspected); ``raw`` (another tool's output,
# not inspected, only at its exact path); and the containers ``object`` (named members,
# each declared), ``array`` and ``map``. A kind ending in ``?`` also allows null.

LABEL, IDENT, PROSE, QUOTE, INT, BOOL, DATA, RAW, DIAG = (
    "label", "identifier", "prose", "quotation", "integer", "boolean", "data", "raw", "diagnostic")
OBJ, ARR, MAP = "object", "array", "map"


def _enum(*values):
    return ("enum", values)


_RUNTIME = _enum(*RUNTIME_STATUSES)
_OUTCOME = _enum(*APPLICATION_OUTCOMES)
_DIAGNOSTIC_KEYS = frozenset({"format", "code", "category", "rule", "secondary_rules", "severity", "stage",
                              "message", "span", "related", "details", "line"})


def _with(prefix: str, entries: dict) -> dict:
    return {prefix + path: kind for path, kind in entries.items()}


_COMMON = {"": OBJ, "/ok": BOOL, "/diagnostic": DIAG, "/upstream_output": RAW}
_ACCOUNTING = {"/accounting": OBJ, "/accounting/claim_label": LABEL, "/accounting/invariants": ARR,
               "/accounting/invariants/*": IDENT}
_ORDERING = {"/ordering": OBJ, "/ordering/claim_label": LABEL, "/ordering/states": INT, "/ordering/edges": INT,
             "/ordering/orders": INT, "/ordering/stock": INT, "/ordering/admission_limit": INT,
             "/ordering/place_bound": INT, "/ordering/max_states": INT, "/ordering/properties": ARR,
             "/ordering/properties/*": IDENT, "/ordering/assumptions": ARR, "/ordering/assumptions/*": PROSE}
# E320 (VIOLATED) and E321 (NOT ESTABLISHED) ordering claims, on a failed net check
_ORDERING_FAILED = {"/ordering/diagnostic_code": _enum("E320", "E321"), "/ordering/property": IDENT,
                    "/ordering/trace": "array?", "/ordering/trace/*": IDENT, "/ordering/marking": IDENT,
                    "/ordering/reason": PROSE}
_NET = {**_ACCOUNTING, **_ORDERING, **_ORDERING_FAILED}
_FLOW_FILES = {"/files": ARR, "/files/*": OBJ, "/files/*/file": IDENT, "/files/*/ok": BOOL,
               "/files/*/claim_label": LABEL, "/files/*/flows": ARR, "/files/*/flows/*": IDENT}
_PURE_CLAIM = {"": OBJ, "/file": IDENT, "/ok": BOOL, "/claim_label": LABEL, "/functions": ARR,
               "/functions/*": IDENT, "/reason": PROSE}
_EXECUTION = {"/execution": OBJ, "/execution/mode": _enum("concurrent", "sequential"),
              "/execution/scheduler": PROSE, "/execution/schedule": _enum("fifo", "lifo", "random"),
              "/execution/seed": INT, "/execution/limits": OBJ,
              **{f"/execution/limits/{k}": INT for k in ("workers", "quantum", "fuel", "max_tasks", "max_depth")},
              "/stats": OBJ, **{f"/stats/{k}": INT for k in ("tasks_created", "max_live_tasks", "forks", "joins",
                                                           "slices", "max_frames", "steps", "pending_tasks",
                                                           "pending_joins", "root_task")}}
# Scheduler events of a pure run, written by weave_pure/runtime.py (Machine.emit): typed,
# not raw. Only events of a run that returned appear in output (a failed run reports its
# diagnostic instead), so the failure and cancellation events are not declared.
_EVENTS = {"/events": ARR, "/events/*": OBJ, "/events/*/seq": INT,
           "/events/*/event": _enum("activation_created", "run", "fork", "wait", "child_complete", "join",
                                    "root_complete", "fork_inline", "join_inline"),
           "/events/*/task": INT, "/events/*/parent": "integer?", "/events/*/fork": "integer?",
           "/events/*/branch": "identifier?", "/events/*/fn": IDENT, "/events/*/steps": INT,
           "/events/*/line": INT, "/events/*/left": INT, "/events/*/right": INT,
           "/events/*/left_fn": IDENT, "/events/*/right_fn": IDENT}
_RUN = {"/runs": ARR, "/runs/*": OBJ, "/runs/*/claim_label": LABEL, "/runs/*/runtime_status": _RUNTIME,
        "/runs/*/outcome": _OUTCOME, "/runs/*/entry": IDENT, "/runs/*/return_type": "identifier?",
        "/runs/*/return_tag": "identifier?", "/runs/*/marking": MAP, "/runs/*/marking/*": INT,
        "/runs/*/events": RAW}


def _command(name: str, *parts: dict) -> dict:
    """A runner command's schema; a part may remove a common path by declaring it None."""
    schema = {**_COMMON, "/command": _enum(name)}
    for part in parts:
        schema.update(part)
    return {path: kind for path, kind in schema.items() if kind is not None}


SCHEMA = {
    "doctor": _command("doctor", {"/diagnostic": None, "/python": IDENT, "/minimum_python": IDENT, "/reference_python": IDENT,
                                  "/third_party_dependencies": ARR, "/third_party_dependencies/*": IDENT,
                                  "/prototype": IDENT, "/missing": ARR, "/missing/*": IDENT}),
    "check": _command("check", _NET, {"/net": IDENT}, _FLOW_FILES, {"/files/*/diagnostic": DIAG}),
    "analyze": _command("analyze", _NET, {"/net": IDENT, "/certificate": IDENT}),
    "lower": _command("lower", _NET, {"/net": IDENT}, _FLOW_FILES, {"/output": IDENT, "/flows": ARR, "/flows/*": IDENT,
                                                   "/files/*/lowered_from": IDENT}),
    "simulate": _command("simulate", _NET, {"/net": IDENT}, _RUN),
    "verify": _command("verify", _ACCOUNTING, {"/certificate": IDENT, "/accounting/method": _enum("certificate recheck"),
                                               "/accounting/scope": PROSE}),
    "examples": _command("examples", _NET, {"/checks": INT, "/passed": INT, "/results": ARR, "/results/*": OBJ,
                                            "/results/*/file": IDENT, "/results/*/ok": BOOL,
                                            "/results/*/lesson": PROSE, "/results/*/outcome": _OUTCOME,
                                            "/results/*/expected": "expectation", "/results/*/actual": "expectation",
                                            "/results/*/diagnostic": DIAG}),
    "test": _command("test", {"/output": RAW}),
    "check-pure": _command("check-pure", {"/scope": PROSE, "/files": ARR, "/files/*/diagnostic": DIAG},
                           _with("/files/*", _PURE_CLAIM)),
    "run-pure": _command("run-pure", {"/scope": PROSE, "/runtime_status": _RUNTIME, "/file": IDENT, "/entry": IDENT,
                                      "/result": DATA}, _with("/check", _PURE_CLAIM), _EXECUTION, _EVENTS),
    "demo:tiny_shop": {"": OBJ, "/demo": _enum("tiny_shop"), "/ok": BOOL, "/source": IDENT, "/entry": IDENT,
                       "/requested_outcome": _enum(*APPLICATION_OUTCOMES, "all"), "/runner_exit": INT,
                       "/diagnostic": DIAG, **_ACCOUNTING, **_ORDERING,
                       "/scenarios": ARR, "/scenarios/*": OBJ, "/scenarios/*/claim_label": LABEL,
                       "/scenarios/*/runtime_status": _RUNTIME, "/scenarios/*/outcome": _OUTCOME,
                       "/scenarios/*/settlement": PROSE, "/scenarios/*/explanation": PROSE,
                       "/scenarios/*/return_type": "identifier?", "/scenarios/*/return_tag": "identifier?",
                       "/scenarios/*/net_transitions": ARR, "/scenarios/*/net_transitions/*": IDENT,
                       "/scenarios/*/final_marking": MAP, "/scenarios/*/final_marking/*": INT,
                       "/scenarios/*/events": RAW},
    "demo:merge_sort": {"": OBJ, "/demo": _enum("merge_sort"), "/ok": BOOL, "/source": IDENT, "/entry": IDENT,
                        "/input": ARR, "/input/*": INT, "/runner_exit": INT, "/output": DATA,
                        "/runtime_status": _RUNTIME, "/scope": PROSE, "/diagnostic": DIAG,
                        **_with("/check", _PURE_CLAIM), **_EXECUTION, **_EVENTS},
    "envelope": {"": OBJ, "/format": _enum(ENVELOPE_FORMAT), "/claim_label": LABEL,
                 "/runtime_status": ("enum", RUNTIME_STATUSES + (None,)),
                 "/claim": OBJ, "/claim/name": IDENT, "/claim/pointer": IDENT, "/claim/statement": "quotation?",
                 "/claim/detail": RAW, "/assumptions": ARR, "/assumptions/*": QUOTE, "/scope": "prose?",
                 "/profiles": ARR, "/profiles/*": OBJ, "/profiles/*/name": IDENT, "/profiles/*/revision": IDENT,
                 "/bounds": "object?", **{f"/bounds/{k}": INT for k in ("admission_limit", "max_states", "orders",
                                                                       "place_bound", "stock", "token_bound_per_colour")},
                 "/bounds/admission": IDENT, "/bounds/dispatch": IDENT, "/bounds/colours": ARR,
                 "/bounds/colours/*": ARR, "/bounds/colours/*/*": IDENT,
                 "/completeness": "object?", "/completeness/complete": BOOL, "/completeness/states": INT,
                 "/completeness/edges": INT, "/completeness/unreached_transitions": ARR,
                 "/completeness/unreached_transitions/*": IDENT,
                 "/wrapped": OBJ, "/wrapped/path": IDENT, "/wrapped/sha256": IDENT, "/wrapped/format": "identifier?",
                 **{f"/{group}": ARR for group in ("sources", "dependencies")},
                 **{f"/{group}/*": OBJ for group in ("sources", "dependencies")},
                 **{f"/{group}/*/{k}": IDENT for group in ("sources", "dependencies") for k in ("path", "sha256")},
                 "/tools": ARR, "/tools/*": OBJ, "/tools/*/name": IDENT, "/tools/*/version": "identifier?",
                 "/tools/*/supported_profiles": ARR, "/tools/*/supported_profiles/*": IDENT,
                 "/trace": "object?", "/trace/format": _enum(TRACE_FORMAT), "/trace/sha256": IDENT},
}
DECLARED_PATHS = sum(len(paths) for paths in SCHEMA.values())


def output_kind(root) -> str | None:
    """Which declared output ``root`` is: a runner command, a demo, or an evidence envelope."""
    if not isinstance(root, dict):
        return None
    if root.get("format") == ENVELOPE_FORMAT:
        return "envelope"
    if isinstance(root.get("demo"), str):
        return f"demo:{root['demo']}"
    if isinstance(root.get("command"), str):
        return root["command"]
    return None


def lint_json(document, pointer: str = "", root=None, used: set | None = None) -> list[str]:
    """Violations of the closed JSON schema in ``document``; an empty list when there are none.

    ``root`` is the whole output when ``document`` is part of one at ``pointer`` (the JSON
    line of a failed ``examples`` expectation); it decides which output's schema applies.
    ``used`` collects ``(output, declared path)`` pairs, for the tests' coverage check.
    """
    root = document if root is None else root
    kind = output_kind(root)
    if kind not in SCHEMA:
        return [f"{pointer or '/'}: not a declared kit output (command, demo or evidence envelope): {kind!r}"]
    pattern = re.sub(r"/\d+(?=/|$)", "/*", pointer)
    return _walk(document, pointer, pattern, SCHEMA[kind], kind, used)


def _walk(value, where: str, pattern: str, schema: dict, output: str, used) -> list[str]:
    kind = schema.get(pattern)
    if kind is None:
        return [f"{where or '/'}: path {pattern or '/'} is not declared for {output} output"]
    if used is not None:
        used.add((output, pattern))
    if isinstance(kind, str) and kind.endswith("?"):
        if value is None:
            return []
        kind = kind[:-1]
    if isinstance(kind, tuple):
        values = kind[1]
        return [] if value in values else [f"{where}: {value!r} is not one of {list(values)!r}"]
    if kind == RAW:
        return []
    if kind == OBJ:
        if not isinstance(value, dict):
            return [f"{where or '/'}: expected an object"]
        return [e for key, item in value.items()
                for e in _walk(item, f"{where}/{key}", f"{pattern}/{key}", schema, output, used)]
    if kind in (ARR, MAP):
        if not isinstance(value, list if kind == ARR else dict):
            return [f"{where}: expected {'an array' if kind == ARR else 'a map'}"]
        items = enumerate(value) if kind == ARR else value.items()
        return [e for key, item in items for e in _walk(item, f"{where}/{key}", f"{pattern}/*", schema, output, used)]
    return _leaf_errors(kind, value, where)


def _leaf_errors(kind: str, value, where: str) -> list[str]:
    if kind == LABEL:
        return [] if value in RESULT_LABELS else [f"{where}: claim label {value!r} is not one of the six result labels"]
    if kind == INT:
        return [] if isinstance(value, int) and not isinstance(value, bool) else [f"{where}: expected an integer"]
    if kind == BOOL:
        return [] if isinstance(value, bool) else [f"{where}: expected a Boolean"]
    if kind == DATA:
        return [] if _data(value) else [f"{where}: expected numbers, Booleans or lists of them"]
    if kind == DIAG:
        if not isinstance(value, dict) or not isinstance(value.get("code"), str) or set(value) - _DIAGNOSTIC_KEYS:
            return [f"{where}: expected a diagnostic with the weave-diagnostic-v1 members"]
        return []
    if kind == "expectation":
        if isinstance(value, str) and (value == "ACCEPT" or value in _CODES):
            return []
        if isinstance(value, dict) and all(isinstance(v, int) and not isinstance(v, bool) for v in value.values()):
            return []
        return [f"{where}: expected ACCEPT, a diagnostic code or a marking"]
    if not isinstance(value, str):
        return [f"{where}: expected a string ({kind})"]
    if kind == IDENT:
        return []
    if kind == QUOTE:
        if value in RESULT_LABELS or _STATUS_WORD.fullmatch(value.strip(_LEADING_NOISE)):
            return [f"{where}: a quotation is never a bare label or status word: {value!r}"]
        return []
    return _prose_errors(value, where)


def _data(value) -> bool:
    if isinstance(value, list):
        return all(_data(item) for item in value)
    return isinstance(value, (int, float, bool))


def _prose_errors(value: str, where: str) -> list[str]:
    """Free text: never a label or upper-case status word, no status token, no leading verdict word."""
    if value in RESULT_LABELS:
        return [f"{where}: result label {value!r} outside a claim_label member"]
    if _begins_with_verdict(value):
        return [f"{where}: {value!r} begins with a verdict word outside a claim_label member"]
    token = _capitals(value)
    if token:
        return [f"{where}: {value!r} contains the status word {token!r} outside a claim_label member"]
    return []


def _capitals(text: str) -> str | None:
    """The first all-capitals token in ``text`` that is not on PROSE_TOKENS, if any."""
    return next((m.group() for m in _STATUS_TOKEN.finditer(text) if m.group() not in PROSE_TOKENS), None)


# Codes the demos' own error records use, besides the mapped diagnostic codes.
DEMO_CODES = ("INPUT", "RUNNER_OUTPUT", "RUNNER_FAILED")
_ERROR_CODE = re.compile(r"(?P<code>[A-Z][A-Z0-9_]*) \[[a-z-]+\]")


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
                errors += [f"line {number}: {e}" for e in lint_json(document, "/results/0", {"command": "examples"})]
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
            # An error line names its code and stage first; a code is allowed only there.
            code = _ERROR_CODE.match(body) if runner == "error: " else None
            if code and (code["code"] in _CODES or code["code"] in DEMO_CODES):
                body = body[code.end():]
        elif own is not None:
            body, outcomes = line[len(own[0]):], own[1]
        else:
            # a diagnostic header: code and rule are checked against the map; the location is free text
            body = _DIAGNOSTIC.fullmatch(line)["location"]
        first = body.lstrip(_LEADING_NOISE).split(" ", 1)[0]
        token = _capitals(body)
        if token:
            errors.append(f"line {number}: {line!r} is not a claim but carries the status word {token!r}")
        elif (runner is not None or own is not None) and first not in outcomes and _begins_with_verdict(body):
            errors.append(f"line {number}: {line!r} is not a claim but its text begins with a verdict word")
    return errors
