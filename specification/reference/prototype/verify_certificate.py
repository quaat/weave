#!/usr/bin/env python3
"""Recheck certificates using separate arithmetic, sharing only the parser.

This is not an independent formal proof assistant. The parser, Python integer
semantics, and the standard place-invariant induction rule are trusted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from checker import CheckError, linear_expression, parse_net


def verify(source: str, certificate: dict) -> int:
    net = parse_net(source)
    if certificate.get("format") != "weave-place-invariant-v1":
        raise ValueError("Unsupported certificate format")
    if certificate.get("source_sha256") != hashlib.sha256(source.encode()).hexdigest():
        raise ValueError("Certificate does not belong to this exact source")
    places, transitions = list(net.places), list(net.transitions)
    if certificate.get("places") != places or certificate.get("transitions") != transitions:
        raise ValueError("Source and certificate declaration order disagree")
    matrix = certificate.get("incidence")
    expected_matrix = []
    for place in places:
        row = []
        for name in transitions:
            rule = net.transitions[name]
            row.append(rule.put.get(place, 0) - rule.take.get(place, 0))
        expected_matrix.append(row)
    if matrix != expected_matrix:
        raise ValueError("Certificate incidence matrix disagrees with source")
    initial = []
    for place in places:
        value = net.places[place].initial
        initial.append([1, 0] if value == net.parameter else [0, int(value)])
    if certificate.get("initial_affine") != initial:
        raise ValueError("Certificate initial marking disagrees with source")
    records = certificate.get("invariants", [])
    if len(records) != len(net.invariants) or {r["name"] for r in records} != set(net.invariants):
        raise ValueError("Certificate must cover each declared invariant exactly once")
    for record in records:
        expression = net.invariants[record["name"]][0]
        left, right = expression.split("==")
        terms, left_constant = linear_expression(left)
        rhs, right_constant = linear_expression(right)
        if set(terms) - set(places) or set(rhs) - {net.parameter}:
            raise ValueError("Invariant refers to undeclared quantities")
        weights = [terms.get(place, 0) for place in places]
        if not any(weights) or record["weights"] != weights:
            raise ValueError("Certificate weights disagree with declared invariant")
        target = [rhs.get(net.parameter, 0), right_constant - left_constant]
        for column in range(len(transitions)):
            delta = 0
            for row in range(len(places)):
                delta += weights[row] * matrix[row][column]
            if delta != 0:
                raise ValueError(f"Preservation failed at {transitions[column]}")
        initial_sum = [0, 0]
        for row, weight in enumerate(weights):
            initial_sum[0] += weight * initial[row][0]
            initial_sum[1] += weight * initial[row][1]
        if initial_sum != target:
            raise ValueError("Initial marking fails the equality")
        if record["initial_actual"] != initial_sum or record["initial_target"] != target:
            raise ValueError("Incorrect recorded initial proof step")
        if record["transition_residuals"] != [0] * len(transitions):
            raise ValueError("Incorrect recorded transition residuals")
        if record["expression"] != expression or record["status"] != "PROVED":
            raise ValueError("Incorrect recorded claim")
    return len(records)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("net", type=Path)
    parser.add_argument("certificate", type=Path)
    args = parser.parse_args()
    try:
        count = verify(args.net.read_text(), json.loads(args.certificate.read_text()))
        print(f"RECHECKED {count} source-bound invariant certificates")
        return 0
    except (CheckError, ValueError, KeyError, TypeError) as error:
        print(f"CERTIFICATE REJECTED: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
