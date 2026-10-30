#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Check rule coverage and generate docs/chapters/rule-coverage.rst.

Every rule ID in ``rules.json`` needs a conformance case in
``examples/manifest.json``, ``examples/pure/manifest.json`` (P0) or
``examples/modules/manifest.json`` (modules-1), a test listed in
``tests/rule-coverage.json``, or a pending-implementation entry there. Listed tests must exist, and a listed
diagnostic code must appear as a string literal in the test method.
``--check`` fails on a gap, a broken reference or a stale generated page.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = "docs/chapters/rule-coverage.rst"
FORMAT = "weave-rule-coverage-v1"
ISSUE = re.compile(r"quaat/weave#[1-9]\d*")
CODE = re.compile(r"E\d{3}")
P0_FORMAT = "weave-p0-conformance-v1"
MODULES_FORMAT = "weave-modules-conformance-v1"
POSITIVE_RESULTS = {"ACCEPT", "VALUE"}


class CoverageError(ValueError):
    """The coverage map is incomplete or refers to something that does not exist."""


def load(root: Path = ROOT) -> tuple[dict, dict, dict]:
    """rules.json, the conformance cases of the three manifests (as one ``cases`` list), the map."""
    read = lambda rel: json.loads((root / rel).read_text(encoding="utf-8"))
    manifest, pure = read("examples/manifest.json"), read("examples/pure/manifest.json")
    modules = read("examples/modules/manifest.json")
    if pure.get("format") != P0_FORMAT:
        raise CoverageError(f"Unsupported P0 manifest format: {pure.get('format')!r}; expected {P0_FORMAT}")
    if modules.get("format") != MODULES_FORMAT:
        raise CoverageError(f"Unsupported modules manifest format: {modules.get('format')!r}; expected {MODULES_FORMAT}")
    manifest = dict(manifest, cases=manifest["cases"] + pure["cases"] + modules["cases"])
    return read("rules.json"), manifest, read("tests/rule-coverage.json")


def _method(root: Path, ref: str, cache: dict) -> ast.FunctionDef:
    parts = ref.split("::")
    if len(parts) != 3 or not all(parts):
        raise CoverageError(f"Test reference must be path::Class::method: {ref}")
    path, cls, method = parts
    file = root / path
    if not file.is_file():
        raise CoverageError(f"Test file does not exist: {path}")
    if path not in cache:
        text = file.read_text(encoding="utf-8")
        cache[path] = ast.parse(text)
    for node in cache[path].body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method and method.startswith("test"):
                    return item
    raise CoverageError(f"Test not found: {ref}")


def _literals(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def validate(rules: dict, manifest: dict, coverage: dict, root: Path = ROOT) -> list[dict]:
    """Return one row per rule, or raise CoverageError."""
    if coverage.get("format") != FORMAT:
        raise CoverageError(f"Unsupported coverage format: {coverage.get('format')!r}; expected {FORMAT}")
    entries = coverage.get("rules")
    if not isinstance(entries, dict):
        raise CoverageError("Coverage map needs a 'rules' object")
    unknown = sorted(set(entries) - set(rules))
    if unknown:
        raise CoverageError("Coverage entries for unknown rule IDs: " + ", ".join(unknown))
    cases: dict[str, list[dict]] = {rule: [] for rule in rules}
    for case in manifest["cases"]:
        for rule in case["rules"]:
            if rule not in cases:
                raise CoverageError(f"Conformance case {case['id']} names unknown rule {rule}")
            cases[rule].append(case)
    cache: dict = {}
    rows = []
    for rule in sorted(rules):
        entry = entries.get(rule)
        if entry is None:
            raise CoverageError(f"No coverage entry for {rule}: list a test or a pending entry")
        extra = set(entry) - {"tests", "pending", "note"}
        if extra:
            raise CoverageError(f"{rule}: unknown fields {sorted(extra)}")
        tests = entry.get("tests", [])
        for test in tests:
            if set(test) - {"test", "polarity", "code"} or "test" not in test:
                raise CoverageError(f"{rule}: test entries have 'test', 'polarity' and optional 'code'")
            if test.get("polarity") not in {"positive", "negative"}:
                raise CoverageError(f"{rule}: polarity must be positive or negative: {test['test']}")
            method = _method(root, test["test"], cache)
            code = test.get("code")
            if code is not None:
                if test["polarity"] != "negative" or not CODE.fullmatch(code):
                    raise CoverageError(f"{rule}: a code belongs to a negative test and has the form E000")
                if code not in _literals(method):
                    raise CoverageError(f"{rule}: {test['test']} does not assert {code}")
        pending = entry.get("pending")
        if pending is not None:
            issue, reason = pending.get("issue"), pending.get("reason")
            if set(pending) != {"issue", "reason"} or not isinstance(reason, str) or not reason.strip():
                raise CoverageError(f"{rule}: a pending entry needs 'issue' and a nonempty 'reason'")
            if issue is not None and not (isinstance(issue, str) and ISSUE.fullmatch(issue)):
                raise CoverageError(f"{rule}: pending issue must be quaat/weave#N or null, not {issue!r}")
        if not tests and not cases[rule] and pending is None:
            raise CoverageError(f"{rule} has no conformance case, no test and no pending entry")
        rows.append({"rule": rule, "cases": cases[rule], "tests": tests, "pending": pending,
                     "note": entry.get("note")})
    return rows


def _short(ref: str) -> str:
    path, cls, method = ref.split("::")
    return f"``{Path(path).stem}.{cls}.{method}``"


def render(rows: list[dict]) -> str:
    covered = [r for r in rows if r["pending"] is None]
    pending = [r for r in rows if r["pending"] is not None]
    untracked = [r for r in pending if r["pending"]["issue"] is None]
    one_sided = [r["rule"] for r in covered
                 if not ({t["polarity"] for t in r["tests"]}
                         | {"positive" if c["expect"] in POSITIVE_RESULTS else "negative" for c in r["cases"]})
                 >= {"positive", "negative"}]
    out = [
        ".. SPDX-FileCopyrightText: 2026 Thomas F. Hagelien",
        ".. SPDX-License-Identifier: MIT",
        "",
        ".. This page is generated by scripts/rule_coverage.py; do not edit it by hand.",
        "",
        "Rule coverage",
        "===================",
        "",
        "This generated page records, for each rule ID in ``rules.json``, the",
        "conformance cases (from ``examples/manifest.json``, for P0",
        "``examples/pure/manifest.json`` and, for modules-1,",
        "``examples/modules/manifest.json``) and tests that exercise it,",
        "or a pending-implementation entry. The map is ``tests/rule-coverage.json``.",
        "``python scripts/rule_coverage.py`` regenerates this page and ``--check`` fails",
        "if a rule has no case, test or pending entry, if a listed test does not exist,",
        "if a listed code is not asserted by its test, or if this page is stale.",
        "``tests/test_rule_coverage.py`` runs that check in ``make validate-offline``.",
        "",
        "A *positive* test or case expects acceptance or the conforming behaviour; a",
        "*negative* one expects rejection, with the diagnostic code shown where the test",
        "asserts one. A listed test exercises the rule through the reference prototype in",
        "``reference/prototype/``, or, for the ``P0-*`` rules, through the P0 reference",
        "evaluator ``scripts/p0_reference.py`` (``test_p0``; the Rust crates have their own",
        "tests, and ``scripts/p0_differential.py`` compares the two), or, for the ``MOD-*``",
        "rules, through ``scripts/modules_conformance.py`` (``test_modules``; the modules-1",
        "cases of P0 programs run through the Rust ``weave`` command): it is regression",
        "evidence for that implementation, not a proof that the rule holds for every input.",
        "Tests from ``test_rule_cases``, ``test_documentation``, ``test_p0`` and ``test_modules`` are in",
        "``tests/``; the others are the prototype's tests in ``reference/prototype/tests/``.",
        "",
        f"**Summary.** {len(rows)} rule IDs; {len(covered)} with a test or conformance case and",
        f"no pending entry; {len(pending)} pending implementation"
        + (f", of which {len(untracked)} have no tracking issue yet (\"issue to be opened\")."
           if untracked else ", each with a tracking issue."),
    ]
    if one_sided:
        out += ["", "Rules with tests or cases in one direction only: " + ", ".join(one_sided) + "."]
    out += ["", "Summary table", "-------------------", "",
            ".. list-table::", "   :header-rows: 1", "   :widths: 26 26 12 12 24", "",
            "   * - Rule", "     - Conformance cases", "     - Positive tests", "     - Negative tests",
            "     - Status"]
    for r in rows:
        ids = ", ".join(c["id"] for c in r["cases"]) or "none"
        npos = sum(t["polarity"] == "positive" for t in r["tests"])
        nneg = sum(t["polarity"] == "negative" for t in r["tests"])
        if r["pending"] is None:
            status = "tested"
        else:
            status = "pending: " + (r["pending"]["issue"] or "issue to be opened")
        out += [f"   * - :ref:`{r['rule']} <{r['rule']}>`", f"     - {ids}", f"     - {npos}",
                f"     - {nneg}", f"     - {status}"]
    out += ["", "Pending implementation", "----------------------------", ""]
    for r in pending:
        issue = r["pending"]["issue"] or "issue to be opened"
        out += [f"* :ref:`{r['rule']} <{r['rule']}>` ({issue}): {r['pending']['reason']}"]
    out += ["", "Tests by rule", "-------------------", ""]
    for r in rows:
        out += [f"* :ref:`{r['rule']} <{r['rule']}>`", ""]
        if r["cases"]:
            out += ["  * Conformance cases: " + ", ".join(f"{c['id']} ({c['expect']})" for c in r["cases"])]
        for t in r["tests"]:
            code = f", {t['code']}" if t.get("code") else ""
            out += [f"  * {t['polarity']}{code}: {_short(t['test'])}"]
        if r["pending"] is not None:
            out += [f"  * Pending: {r['pending']['issue'] or 'issue to be opened'}"]
        if r["note"]:
            out += [f"  * Note: {r['note']}"]
        out += [""]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail on gaps or a stale page")
    args = parser.parse_args(argv)
    try:
        rows = validate(*load())
    except CoverageError as error:
        raise SystemExit(f"Rule coverage FAILED: {error}")
    text = render(rows)
    page = ROOT / PAGE
    if args.check:
        if not page.exists() or page.read_text(encoding="utf-8") != text:
            raise SystemExit(f"Rule coverage FAILED: {PAGE} is stale; run scripts/rule_coverage.py")
    else:
        page.write_text(text, encoding="utf-8")
    pending = sum(r["pending"] is not None for r in rows)
    print(f"PASS: rule coverage {'current' if args.check else 'generated'}: "
          f"{len(rows)} rules, {len(rows) - pending} tested, {pending} pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
