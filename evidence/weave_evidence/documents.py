# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Read and check documents in the four evidence formats.

A document is accepted only if its top-level ``format`` names a format this
reader implements, it validates against that format's schema, and it passes
the format's reader checks. A missing, non-string or unrecognised ``format``
is refused with a message naming what was found; it is never read as a nearby
version and never reported as success (stability policy, "Unrecognised
versions").
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import schema as schemas

CANONICAL_NET = "weave-canonical-net-v1"
TRACE = "weave-trace-v1"
ENVELOPE = "weave-evidence-envelope-v1"
DIAGNOSTIC = "weave-diagnostic-v1"

SCHEMA_FILES = {
    CANONICAL_NET: "canonical-net.v1.schema.json",
    TRACE: "trace.v1.schema.json",
    ENVELOPE: "evidence-envelope.v1.schema.json",
    DIAGNOSTIC: "diagnostic.v1.schema.json",
}

# The closed set of result labels of weave-evidence-envelope-v1: the six labels of
# specification/docs/chapters/verification.rst, "Result vocabulary", that predate
# CHECKED pure (quaat/weave#10). The envelope schema enumerates the same six strings.
RESULT_LABELS = (
    "PROVED",
    "CHECKED WITHIN BOUNDS",
    "CHECKED flow",
    "SCRIPTED / passed scenario",
    "VIOLATED",
    "NOT ESTABLISHED",
)
RUNTIME_STATUSES = ("waiting", "timed out", "completed")


class DocumentError(ValueError):
    """The input is not one well-formed JSON document."""


@dataclass
class Assessment:
    """Result of reading one document. ``accepted`` is True only when ``errors`` is empty."""

    format: object
    errors: list[str] = field(default_factory=list)
    refused: bool = False

    @property
    def accepted(self) -> bool:
        return not self.errors and not self.refused


def _reject_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise DocumentError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _reject_constant(name):
    raise DocumentError(f"non-standard JSON constant {name}")


def parse(text: str):
    """Parse strict JSON: duplicate keys, NaN and Infinity are errors."""
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except json.JSONDecodeError as error:
        raise DocumentError(str(error)) from error


def canonical_bytes(document) -> bytes:
    """The byte form written by this tooling: sorted keys, two-space indent, final newline."""
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def implemented_formats() -> tuple[str, ...]:
    return tuple(SCHEMA_FILES)


def assess(document) -> Assessment:
    """Check one parsed document. Unknown or missing formats are refused, never accepted."""
    if not isinstance(document, dict):
        return Assessment(None, [f"refused: expected a JSON object with a top-level 'format' field, "
                                 f"got {type(document).__name__}"], refused=True)
    if "format" not in document:
        return Assessment(None, ["refused: no top-level 'format' field; an evidence document must name "
                                 f"its format (implemented: {', '.join(implemented_formats())})"], refused=True)
    fmt = document["format"]
    if not isinstance(fmt, str) or fmt not in SCHEMA_FILES:
        return Assessment(fmt, [f"refused: unrecognised format identifier {fmt!r}; this reader implements "
                                f"{', '.join(implemented_formats())} and does not read other identifiers "
                                "or versions"], refused=True)
    errors = schemas.validate(document, schemas.load(SCHEMA_FILES[fmt]))
    if not errors:
        errors = READER_CHECKS[fmt](document)
    return Assessment(fmt, errors)


def assess_text(text: str) -> Assessment:
    try:
        document = parse(text)
    except DocumentError as error:
        return Assessment(None, [f"refused: not one strict JSON document: {error}"], refused=True)
    return assess(document)


def read_document(path: Path) -> tuple[object, Assessment, bytes | None]:
    """Read and check one file. An unreadable, non-UTF-8 or non-JSON file is refused, naming the file."""
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        return None, Assessment(None, [f"refused: cannot read {path}: {error.strerror or error}"], refused=True), None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        return None, Assessment(None, [f"refused: {path} is not UTF-8: {error.reason} at byte {error.start}"],
                                refused=True), data
    try:
        document = parse(text)
    except DocumentError as error:
        return None, Assessment(None, [f"refused: {path} is not one strict JSON document: {error}"], refused=True), data
    return document, assess(document), data


def assess_file(path: Path) -> Assessment:
    return read_document(path)[1]


# ------------------------------------------------------------------ reader checks


def _duplicates(values) -> list:
    seen, dup = set(), []
    for v in values:
        if v in seen and v not in dup:
            dup.append(v)
        seen.add(v)
    return dup


def check_canonical_net(net: dict) -> list[str]:
    errors = []
    places = {p["name"]: p for p in net["places"]}
    names = [p["name"] for p in net["places"]]
    tnames = [t["name"] for t in net["transitions"]]
    for label, values in (("place", names), ("transition", tnames)):
        for dup in _duplicates(values):
            errors.append(f"duplicate {label} {dup!r}")
        if values != sorted(values):
            errors.append(f"{label}s are not sorted by name")
    params = [p["name"] for p in net["parameters"]]
    for dup in _duplicates(params):
        errors.append(f"duplicate parameter {dup!r}")
    sorts = len(net["colour_sorts"])
    for p in net["places"]:
        if p["indices"] and len(p["indices"]) != sorts:
            errors.append(f"place {p['name']!r}: {len(p['indices'])} indices, net has {sorts} colour sorts")
    marked = [m["place"] for m in net["initial_marking"]]
    if marked != names:
        errors.append("initial_marking must list every place exactly once, in place order")
    for m in net["initial_marking"]:
        for parameter in m["parameters"]:
            if parameter not in params:
                errors.append(f"initial marking of {m['place']!r} uses undeclared parameter {parameter!r}")
    order = {"take": 0, "read": 1, "put": 2}
    for t in net["transitions"]:
        if t["binder"] and len(t["binder"]) != sorts:
            errors.append(f"transition {t['name']!r}: binder has {len(t['binder'])} variables, net has {sorts} colour sorts")
        if t["guards"] != sorted(set(t["guards"])):
            errors.append(f"transition {t['name']!r}: guards are not sorted and unique")
        keys = [(order[a["kind"]], a["place"]) for a in t["arcs"]]
        if keys != sorted(keys):
            errors.append(f"transition {t['name']!r}: arcs are not in canonical order")
        for dup in _duplicates(keys):
            errors.append(f"transition {t['name']!r}: duplicate {a_kind(dup)} arc on {dup[1]!r}")
        for a in t["arcs"]:
            place = places.get(a["place"])
            if place is None:
                errors.append(f"transition {t['name']!r}: arc on undeclared place {a['place']!r}")
            elif len(a["inscription"]) != len(place["indices"]):
                errors.append(f"transition {t['name']!r}: {a['kind']} {a['place']!r} inscription arity "
                              f"{len(a['inscription'])}, place has {len(place['indices'])} indices")
    return errors


def a_kind(key: tuple[int, str]) -> str:
    return ("take", "read", "put")[key[0]]


def _marking_errors(marking: list[dict], where: str) -> list[str]:
    keys = [(m["place"], tuple(m["colour"])) for m in marking]
    errors = [f"{where}: duplicate token count for {p}{list(c) if c else ''}" for p, c in _duplicates(keys)]
    if keys != sorted(keys):
        errors.append(f"{where}: entries are not sorted by place and colour")
    return errors


def check_trace(trace: dict) -> list[str]:
    errors = []
    sequence = [s["sequence"] for s in trace["steps"]]
    if any(b <= a for a, b in zip(sequence, sequence[1:])):
        errors.append("step sequence numbers must increase strictly")
    for step in trace["steps"]:
        if "marking" in step:
            errors += _marking_errors(step["marking"], f"step {step['sequence']}")
    if trace["final_marking"] is not None:
        errors += _marking_errors(trace["final_marking"], "final_marking")
    if trace["outcome"] in RESULT_LABELS:
        errors.append(f"outcome {trace['outcome']!r} is a result label; a trace outcome is an application outcome")
    return errors


def check_envelope(envelope: dict) -> list[str]:
    errors = []
    for key in ("sources", "dependencies"):
        for dup in _duplicates([f["path"] for f in envelope[key]]):
            errors.append(f"{key}: duplicate path {dup!r}")
    for dup in _duplicates([t["name"] for t in envelope["tools"]]):
        errors.append(f"tools: duplicate tool {dup!r}")
    for dup in _duplicates([p["name"] for p in envelope["profiles"]]):
        errors.append(f"profiles: duplicate profile {dup!r}")
    return errors


def _span_errors(span: dict | None, where: str) -> list[str]:
    if span is None:
        return []
    start, end = span["start"], span["end"]
    if (end["line"], end["column"]) < (start["line"], start["column"]):
        return [f"{where}: span ends before it starts"]
    return []


def check_diagnostic(diagnostic: dict) -> list[str]:
    errors = _span_errors(diagnostic["span"], "span")
    for i, item in enumerate(diagnostic["related"]):
        errors += _span_errors(item["span"], f"related[{i}]")
    if diagnostic["rule"] is not None and diagnostic["rule"] in diagnostic["secondary_rules"]:
        errors.append(f"principal rule {diagnostic['rule']!r} is repeated in secondary_rules")
    return errors


READER_CHECKS = {CANONICAL_NET: check_canonical_net, TRACE: check_trace, ENVELOPE: check_envelope,
                 DIAGNOSTIC: check_diagnostic}


def verify_hashes(envelope: dict, root: Path) -> list[str]:
    """Recompute the SHA-256 of the wrapped file, sources and dependencies under ``root``."""
    errors = []
    entries = [("wrapped", envelope["wrapped"])] + [(k, f) for k in ("sources", "dependencies") for f in envelope[k]]
    for key, entry in entries:
        path = Path(root) / entry["path"]
        if not path.is_file():
            errors.append(f"{key}: {entry['path']} is missing")
            continue
        try:
            digest = sha256_file(path)
        except OSError as error:
            errors.append(f"{key}: cannot read {entry['path']}: {error.strerror or error}")
            continue
        if digest != entry["sha256"]:
            errors.append(f"{key}: {entry['path']} does not hash to the recorded sha256")
    return errors
