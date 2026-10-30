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
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckError, OSError, ValueError, RuntimeError, AssertionError) as exc:
        print(f"VALIDATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)

