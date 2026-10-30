#!/usr/bin/env python3
"""Validate this documentation's source snapshot, examples, and bounded evidence."""
from __future__ import annotations
import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "reference" / "prototype"))
from checker import CheckError, check_flow, explore_order, lower_flow_source, parse_net, prove
from coloured import Unfolding, explore_colours, parse_coloured, prove_colours
from simulate import simulate
sys.path.insert(0, str(ROOT / "scripts"))
import p0_reference

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def main() -> int:
    provenance = json.loads(read(ROOT / "PROVENANCE.json"))
    for relative, expected in provenance["reference_files"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Reference snapshot changed: {relative}")

    examples = ROOT / "examples"
    manifest = json.loads(read(examples / "manifest.json"))
    net_source = read(examples / manifest["net"])
    net = parse_net(net_source)
    accounting = prove(net)
    ordering = explore_order(net)
    coloured = parse_coloured(read(examples / "nets" / "Inventory.coloured.weave"))
    families = prove_colours(coloured)
    coloured_ordering = explore_colours(coloured)
    outcomes = []
    accepted = []

    for case in manifest["cases"]:
        path = examples / case["file"]
        source = read(path)
        actual = "ACCEPT"
        try:
            if case["kind"] == "flow":
                check_flow(net, source)
            elif case["kind"] == "net":
                candidate = parse_net(source)
                prove(candidate)
                explore_order(candidate)
            elif case["kind"] == "net_append":
                candidate = parse_net(net_source.rstrip() + "\n\n" + source)
                prove(candidate)
                explore_order(candidate)
            else:
                raise ValueError(f"Unsupported manifest kind: {case['kind']}")
        except CheckError as exc:
            actual = exc.code
        if actual != case["expect"]:
            raise AssertionError(f"{case['file']}: expected {case['expect']}, got {actual}")
        outcomes.append({"file": case["file"], "expected": case["expect"], "actual": actual})
        if actual == "ACCEPT" and case["kind"] == "flow":
            lowered = lower_flow_source(source)
            check_flow(net, lowered)
            check_flow(coloured.base, source)
            check_flow(coloured.base, lowered)
            accepted.append(case["file"])

    runs = []
    for scenario in manifest["scenarios"]:
        result = simulate(net, read(examples / scenario["file"]),
                          scenario["entry"], scenario["outcome"])
        for place, expected in scenario["marking"].items():
            if result["marking"][place] != expected:
                raise AssertionError(f"{scenario['outcome']}: wrong {place} marking")
        runs.append({"outcome": scenario["outcome"], "marking": result["marking"]})

    if (ordering["states"], ordering["edges"]) != (20, 43):
        raise AssertionError("Pinned legacy exploration changed")
    if (coloured_ordering["states"], coloured_ordering["edges"]) != (841, 3712):
        raise AssertionError("Pinned coloured exploration changed")
    if coloured_ordering["unreached_transitions"]:
        raise AssertionError("Pinned coloured protocol has unreachable transitions")
    unfolding = Unfolding(coloured)
    if (len(unfolding.rows), len(unfolding.modes)) != (32, 48):
        raise AssertionError("Pinned finite unfolding changed")

    # The P0 corpus is checked here but not recorded in report.json, whose format
    # (weave-specification-validation-v1) has no P0 field; validation/p0-differential.json
    # records the P0 results.
    pure = p0_corpus(examples)

    output = ROOT / "validation"
    output.mkdir(exist_ok=True)
    (output / "lowered-checkout.weave").write_text(
        lower_flow_source(read(examples / "valid" / "checkout_propagating.weave")),
        encoding="utf-8")
    lease = parse_net(read(examples / "nets/Lease.weave"))
    prove(lease)
    check_flow(lease, read(examples / "valid/lease_roundtrip.weave"))
    try:
        explore_order(lease)
    except CheckError as exc:
        if exc.code != "E300": raise
    else:
        raise AssertionError("Lease must not claim an absent ordering model")
    bad = parse_net(read(examples / "nets/unsafe_paid_release.weave"))
    prove(bad)
    try:
        explore_order(bad)
    except CheckError as exc:
        if exc.code != "E320": raise
        (output / "counterexample-E320.txt").write_text(exc.render("examples/nets/unsafe_paid_release.weave")+"\n")
    else:
        raise AssertionError("Expected E320")
    bad_colour = parse_coloured(read(examples / "nets/cross_order_read.weave"))
    prove_colours(bad_colour)
    try:
        explore_colours(bad_colour)
    except CheckError as exc:
        if exc.code != "E420": raise
        (output / "counterexample-E420.txt").write_text(exc.render("examples/nets/cross_order_read.weave")+"\n")
    else:
        raise AssertionError("Expected E420")
    report = {
        "format": "weave-specification-validation-v1",
        "document": "0.2-draft",
        "python": platform.python_version(),
        "reference_integrity": "PASS",
        "lease": "accounting/F0 pass; ordering E300",
        "counterexamples": ["E320", "E420"],
        "cases": outcomes,
        "accepted_flows_checked_original_and_lowered_against_n0_and_n1": accepted,
        "scenarios": runs,
        "n0": {"invariants": len(accounting["invariants"]),
               "states": ordering["states"], "edges": ordering["edges"],
               "complete": ordering["complete"]},
        "n1": {"aggregate_invariants": len(families["aggregate"]),
               "family_invariants": len(families["families"]),
               "states": coloured_ordering["states"], "edges": coloured_ordering["edges"],
               "complete": coloured_ordering["complete"],
               "unreached_transitions": coloured_ordering["unreached_transitions"],
               "cells": len(unfolding.rows), "modes": len(unfolding.modes)},
        "scope": "Example and snapshot regression evidence, not grammar equivalence or language soundness."
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(outcomes)} source expectations; {len(runs)} scripted scenarios")
    print(f"PASS: {len(accepted)} valid flows and their lowerings checked with N0 and N1 APIs")
    print("PASS: N0 20 states / 43 edges; N1 841 states / 3712 edges")
    print("PASS: unchanged reference snapshot; 32 coloured cells / 48 firing modes")
    print(f"PASS: {pure['check_cases']} P0 check cases and {pure['run_cases']} P0 run cases "
          "meet examples/pure/manifest.json with the P0 reference evaluator")
    return 0


def p0_corpus(examples: Path) -> dict:
    """The P0 corpus (weave-p0-conformance-v1) with the P0 reference evaluator."""
    manifest = json.loads(read(examples / "pure" / "manifest.json"))
    if manifest.get("format") != "weave-p0-conformance-v1":
        raise ValueError(f"Unsupported P0 manifest format: {manifest.get('format')!r}")
    checks = runs = 0
    for case in manifest["cases"]:
        source = read(examples / case["file"])
        try:
            program = p0_reference.check(source)
            actual = "ACCEPT"
        except p0_reference.Diagnostic as exc:
            program, actual = None, exc.code
        if case["kind"] == "check":
            checks += 1
        else:
            runs += 1
            if program is None:
                raise AssertionError(f"{case['id']}: {case['file']} is rejected ({actual})")
            try:
                report = p0_reference.run(program, case["entry"], case["args"], case.get("budgets"))
                actual = report["diagnostics"][0].code if report["diagnostics"] else "VALUE"
            except p0_reference.Diagnostic as exc:
                report, actual = None, exc.code
            if actual == "VALUE" and report["value"] != case["value"]:
                raise AssertionError(f"{case['id']}: value {report['value']!r}, expected {case['value']!r}")
            if report is not None and "usage" in case:
                b = report["budgets"]
                usage = {"fuel": b["fuel"]["used"], "depth": b["depth"]["max"], "int_bits": b["int_bits"]["max"]}
                if usage != case["usage"]:
                    raise AssertionError(f"{case['id']}: usage {usage}, expected {case['usage']}")
        if actual != case["expect"]:
            raise AssertionError(f"{case['id']} {case['file']}: expected {case['expect']}, got {actual}")
    return {"manifest": "examples/pure/manifest.json", "check_cases": checks, "run_cases": runs,
            "implementation": "scripts/p0_reference.py"}

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckError, OSError, ValueError, RuntimeError, AssertionError) as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

