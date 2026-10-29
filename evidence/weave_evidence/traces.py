# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Convert existing step records to weave-trace-v1 documents.

Each converter reads one existing record shape exactly and raises
``ConversionError`` on anything else; it never guesses at an unknown shape.
Token counts are kept as recorded, including zero counts, and only reordered.
"""
from __future__ import annotations

import re

from .documents import TRACE


class ConversionError(ValueError):
    """The input does not have the shape this converter reads."""


MARKING_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[([^\[\]]+)\])?$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ConversionError(message)


def marking(mapping: dict, where: str) -> list[dict]:
    """``{"held": 1, "sold[tenant,order1]": 1}`` -> sorted token counts."""
    require(isinstance(mapping, dict), f"{where}: marking must be an object")
    out = []
    for key, count in mapping.items():
        match = MARKING_KEY.match(key)
        require(match is not None, f"{where}: unrecognised marking key {key!r}")
        require(isinstance(count, int) and not isinstance(count, bool) and count >= 0,
                f"{where}: count for {key!r} must be a nonnegative integer")
        colour = match[2].split(",") if match[2] else []
        out.append({"place": match[1], "colour": colour, "count": count})
    return sorted(out, key=lambda m: (m["place"], m["colour"]))


def marking_dict(counts: list[dict]) -> dict:
    """Inverse of :func:`marking` for the key spelling used by the prototype."""
    return {m["place"] + (f"[{','.join(m['colour'])}]" if m["colour"] else ""): m["count"] for m in counts}


def from_simulation(run: dict, where: str) -> dict:
    """One element of inventory-proof/scenarios.json (``simulate.simulate`` output)."""
    require(isinstance(run, dict) and set(run) == {"outcome", "entry", "return_type", "return_tag", "marking", "events"},
            f"{where}: expected keys outcome, entry, return_type, return_tag, marking, events")
    steps = []
    for i, event in enumerate(run["events"], start=1):
        require(isinstance(event, dict) and set(event) == {"kind", "name", "tag", "marking"},
                f"{where}/events/{i - 1}: expected keys kind, name, tag, marking")
        step = {"sequence": i, "marking": marking(event["marking"], f"{where}/events/{i - 1}")}
        if event["kind"] == "NET":
            require(event["tag"] is None, f"{where}/events/{i - 1}: a NET event has no tag")
            step.update(kind="fire", transition=event["name"])
        elif event["kind"] == "RETURN":
            step.update(kind="return", flow=event["name"], tag=event["tag"])
        else:
            raise ConversionError(f"{where}/events/{i - 1}: unrecognised event kind {event['kind']!r}")
        steps.append(step)
    return {
        "format": TRACE,
        "kind": "scenario",
        "subject": run["entry"],
        "model": None,
        "steps": steps,
        "final_marking": marking(run["marking"], f"{where}/marking"),
        "outcome": run["outcome"],
        "context": {"return_type": run["return_type"], "return_tag": run["return_tag"]},
    }


DURABLE_KEYS = {"scenario", "status", "crash", "marking", "jobs", "operations", "results", "provider", "events"}


def from_durable(case: dict, where: str) -> dict:
    """One element of inventory-proof/durable-scenarios.json (``durable.run_crash_cases`` output)."""
    require(isinstance(case, dict) and set(case) == DURABLE_KEYS, f"{where}: expected keys {sorted(DURABLE_KEYS)}")
    steps = []
    for i, event in enumerate(case["events"]):
        require(isinstance(event, dict) and set(event) == {"sequence", "kind", "detail", "marking"},
                f"{where}/events/{i}: expected keys sequence, kind, detail, marking")
        require(isinstance(event["detail"], dict), f"{where}/events/{i}: detail must be an object")
        detail = dict(event["detail"])
        step = {"sequence": event["sequence"], "kind": event["kind"]}
        if "colour" in detail:
            step["colour"] = detail.pop("colour")
        if "transition" in detail:
            step["transition"] = detail.pop("transition")
        require(event["kind"] != "fire" or "transition" in step, f"{where}/events/{i}: a fire event names a transition")
        if detail:
            step["detail"] = detail
        step["marking"] = marking(event["marking"], f"{where}/events/{i}")
        steps.append(step)
    return {
        "format": TRACE,
        "kind": "scenario",
        "subject": case["scenario"],
        "model": None,
        "steps": steps,
        "final_marking": marking(case["marking"], f"{where}/marking"),
        "outcome": None,
        "context": {k: case[k] for k in ("status", "crash", "jobs", "operations", "results", "provider")},
    }


FIRING = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[([^\[\]]*)\])?$")


def from_counterexample(text: str, where: str) -> dict:
    """A rendered E320 or E420 diagnostic, as in specification/validation/counterexample-E320.txt.

    Expected shape (``CheckError.render``): a ``<file>:<line>: <code>`` header, a
    ``VIOLATED <property> ...`` line, a ``Trace: a -> b -> ...`` line, and either a
    ``Marking: p=n, ...; flag=bool, ...`` line (E320) or one detail line (E420).
    """
    lines = text.rstrip("\n").split("\n")
    require(len(lines) == 4, f"{where}: expected four lines")
    header = re.fullmatch(r"(.+):(\d+): (E\d{3})", lines[0])
    require(header is not None, f"{where}: expected '<file>:<line>: <code>' header")
    violated = re.fullmatch(r"  VIOLATED (\w+) (.+)\.", lines[1])
    require(violated is not None, f"{where}: expected a 'VIOLATED <property> ...' line")
    trace = re.fullmatch(r"  Trace: (.+)", lines[2])
    require(trace is not None, f"{where}: expected a 'Trace:' line")
    steps = []
    for i, label in enumerate(trace[1].split(" -> "), start=1):
        firing = FIRING.fullmatch(label)
        require(firing is not None, f"{where}: unrecognised firing {label!r}")
        step = {"sequence": i, "kind": "fire", "transition": firing[1]}
        if firing[2]:
            binding = {}
            for part in firing[2].split(","):
                name, sep, value = part.partition("=")
                require(sep == "=" and name and value, f"{where}: unrecognised binding {part!r}")
                binding[name] = value
            step["detail"] = {"binding": binding}
        steps.append(step)
    context = {"diagnostic": header[3], "location": f"{header[1]}:{header[2]}", "model": violated[2]}
    final = None
    mark = re.fullmatch(r"  Marking: (.*); (.+)\.", lines[3])
    if mark:
        counts = {}
        for part in mark[1].split(", "):
            name, sep, value = part.partition("=")
            require(sep == "=" and value.isdigit(), f"{where}: unrecognised marking entry {part!r}")
            counts[name] = int(value)
        final = marking(counts, f"{where}/marking")
        flags = {}
        for part in mark[2].split(", "):
            name, sep, value = part.partition("=")
            require(sep == "=" and value in ("true", "false"), f"{where}: unrecognised flag {part!r}")
            flags[name] = value == "true"
        context["flags"] = flags
        context["marking_lists"] = "occupied places only"
    else:
        context["detail"] = lines[3].strip()
    return {
        "format": TRACE,
        "kind": "counterexample",
        "subject": violated[1],
        "model": None,
        "steps": steps,
        "final_marking": final,
        "outcome": None,
        "context": context,
    }


SCHEDULER_STEP_KEYS = {"seq", "event", "task"}


def from_scheduler_run(run: dict, where: str) -> dict:
    """An agent-kit pure-runtime trace, as in agent-kit/demos/merge_sort/artifacts/trace-concurrent.json."""
    require(isinstance(run, dict) and isinstance(run.get("events"), list) and isinstance(run.get("entry"), str),
            f"{where}: expected an object with 'entry' and 'events'")
    steps = []
    for i, event in enumerate(run["events"]):
        require(isinstance(event, dict) and SCHEDULER_STEP_KEYS <= set(event),
                f"{where}/events/{i}: expected keys seq, event, task")
        step = {"sequence": event["seq"], "kind": event["event"], "task": event["task"]}
        detail = {k: v for k, v in event.items() if k not in SCHEDULER_STEP_KEYS}
        if detail:
            step["detail"] = detail
        steps.append(step)
    return {
        "format": TRACE,
        "kind": "scheduler-run",
        "subject": run["entry"],
        "model": None,
        "steps": steps,
        "final_marking": None,
        "outcome": None,
        "context": {k: v for k, v in run.items() if k != "events"},
    }
