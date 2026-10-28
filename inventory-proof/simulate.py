#!/usr/bin/env python3
"""Synchronous single-order reference execution with one scripted foreign reply.

This executes the checked, lowered source against the parsed net. It is not a
durable runtime, provider adapter, or proof of compiler/runtime refinement.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from checker import (Binding, CheckError, Signature, Type, apply_call, check_flow,
                     explore_order, lower_questions, parameters, parse_net, prove,
                     split_commas, type_of)


@dataclass
class Value:
    type: Type
    symbol: str = ""
    tag: str | None = None
    payload: Value | None = None


def simulate(net, source: str, entry: str, outcome: str) -> dict:
    """Run a scalar-entry flow with exactly one scripted Ok/Err/Unknown reply."""
    prove(net)
    explore_order(net)
    check_flow(net, source)
    if outcome not in {"Ok", "Err", "Unknown"}:
        raise ValueError("Outcome must be Ok, Err, or Unknown")
    declarations, helpers = {}, {}
    for root in lower_questions(source):
        m = re.fullmatch(r"flow (\w+)\((.*)\)(?: -> (.+))?:", root.text)
        helpers[m[1]] = Signature(parameters(m[2]), type_of(m[3] or "Unit"), "", root.line)
        declarations[m[1]] = root
    if entry not in helpers:
        raise ValueError("Unknown entry flow")
    if any(typ.keys or typ.name in net.resources or typ.name in net.enums
           for _, typ in helpers[entry].params):
        raise ValueError("Simulator entry must have only scalar parameters")
    marking = {p: 1 if v.initial == net.parameter else int(v.initial) for p, v in net.places.items()}
    events = []
    dispatch_count = 0

    def record(kind, name, tag=None):
        events.append({"kind": kind, "name": name, "tag": tag, "marking": dict(marking)})

    def fire(name):
        t = net.transitions[name]
        if any(marking[p] < n for arcs in (t.take, t.read) for p, n in arcs.items()):
            raise AssertionError(f"Disabled transition in scripted execution: {name}")
        # Guard truth is supplied by the chosen scenario, not a network query.
        for p in marking:
            marking[p] += t.put.get(p, 0) - t.take.get(p, 0)
        record("NET", name)

    def call(name, arguments):
        nonlocal dispatch_count
        bindings = {f"a{i}": Binding(v.type, v.symbol, 0) for i, v in enumerate(arguments)}
        result_type = apply_call(net, name, ", ".join(bindings), bindings, 0, helpers)
        if name in helpers:
            local = {p: value for (p, _), value in zip(helpers[name].params, arguments)}
            result = body(declarations[name].children, local, result_type)
            if result.type != result_type:
                raise AssertionError("Reference execution returned an incorrect type")
            record("RETURN", name, result.tag)
            return result
        sig = net.apis[name]
        if sig.pending is not None:
            dispatch_count += 1
            if dispatch_count > 1:
                raise ValueError("Reference executor supports only one foreign operation per scenario")
        fire(sig.via)
        if sig.pending is not None:
            fire(sig.outcomes[outcome])
            enum = net.enums[result_type.name]
            mapping = dict(zip(enum.keys, result_type.keys))
            payload = enum.cases[outcome]
            return Value(result_type, tag=outcome,
                         payload=Value(Type(payload.name, tuple(mapping[k] for k in payload.keys))))
        return Value(result_type)

    def body(nodes, env, expected):
        for node in nodes:
            text = node.text
            if m := re.fullmatch(r"let (\w+) = await ([\w.]+)\((.*)\)", text):
                env[m[1]] = call(m[2], [env[a] for a in split_commas(m[3])])
            elif m := re.fullmatch(r"await ([\w.]+)\((.*)\)", text):
                call(m[1], [env[a] for a in split_commas(m[2])])
            elif m := re.fullmatch(r"match (\w+):", text):
                value = env[m[1]]
                for child in node.children:
                    case = re.fullmatch(r"(\w+)\((\w*)\):", child.text)
                    if case[1] == value.tag:
                        branch = dict(env)
                        if case[2]:
                            branch[case[2]] = value.payload
                        return body(child.children, branch, expected)
                raise AssertionError("Checked match was not exhaustive")
            elif m := re.fullmatch(r"return(?: (\w+)(?:\((\w*)\))?)?", text):
                if m[2] is not None:
                    payload = env[m[2]] if m[2] else Value(Type("Unit"))
                    return Value(expected, tag=m[1], payload=payload)
                return env[m[1]] if m[1] else Value(Type("Unit"))
            else:
                raise AssertionError(f"Unsupported checked statement: {text}")
        raise AssertionError("Checked body did not return")

    result = call(entry, [Value(typ, param) for param, typ in helpers[entry].params])
    return {"outcome": outcome, "entry": entry, "return_type": str(result.type),
            "return_tag": result.tag, "marking": marking, "events": events}


def simulation_text(result):
    lines = [f"SCRIPTED {result['outcome']} via {result['entry']} (in-memory, one order)"]
    for event in result["events"]:
        places = ", ".join(f"{p}={n}" for p, n in event["marking"].items() if n)
        tag = f" {event['tag']}" if event["tag"] else ""
        lines.append(f"  {event['kind']} {event['name']}{tag}: {places}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outcome", choices=["Ok", "Err", "Unknown"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    net = parse_net((root / "Inventory.weave").read_text())
    source = (root / "examples/checkout_propagating.weave").read_text()
    print(simulation_text(simulate(net, source, "checkout_propagating", args.outcome)))


if __name__ == "__main__":
    main()
