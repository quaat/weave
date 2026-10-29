#!/usr/bin/env python3
"""Restricted net/linear-capability checker. No network or source evaluation.

PROVED labels apply only to exact integer linear invariants of the parsed net.
The separate bounded explorer checks guard placement for one order. The flow
checker supports nominal linear helper calls/returns and terminal matches, not
the general language. See README.md for its trusted boundary and limitations.
"""
from __future__ import annotations

import argparse
import ast
import copy
import functools
import hashlib
import json
import re
import sys
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path


DIAGNOSTIC_FORMAT = "weave-diagnostic-v1"


@dataclass(frozen=True)
class Span:
    """A source region. Lines and columns are 1-based; end_column is one past the last character."""
    line: int
    column: int
    end_line: int
    end_column: int


@dataclass
class Related:
    """A secondary location of a diagnostic, such as where a live handle was bound.

    ``name`` selects an identifier on ``line`` ("?" selects the propagation operator);
    without it, or when it is not found, the span covers the statement on that line.
    """
    role: str
    label: str
    line: int
    name: str | None = None
    span: Span | None = None


def statement_span(source: str, line: int) -> Span:
    """The statement on ``line`` without indentation or comment; the whole source when there is no such line."""
    lines = source.splitlines()
    if 1 <= line <= len(lines):
        text = lines[line - 1].split("#", 1)[0].rstrip()
        if text.strip():
            return Span(line, len(text) - len(text.lstrip()) + 1, line, len(text) + 1)
    if not lines:
        return Span(1, 1, 1, 1)
    return Span(1, 1, len(lines), len(lines[-1]) + 1)


def name_span(source: str, line: int, name: str | None) -> Span:
    """The first occurrence of ``name`` on ``line`` (after the parameter list opens on a flow header)."""
    lines = source.splitlines()
    if name and 1 <= line <= len(lines):
        text = lines[line - 1].split("#", 1)[0].rstrip()
        if name == "?":
            found = text.rfind("?")
            if found >= 0:
                return Span(line, found + 1, line, found + 2)
        else:
            start = text.find("(") + 1 if text.lstrip().startswith("flow ") else 0
            match = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)").search(text, start)
            if match:
                return Span(line, match.start() + 1, line, match.end() + 1)
    return statement_span(source, line)


class CheckError(Exception):
    """A rejection with a code, a message and its source location.

    ``line`` is the legacy 1-based line (0 when no single line applies). After
    ``locate`` the primary ``span`` and the spans of ``related`` locations are set.
    """

    def __init__(self, code: str, message: str, line: int = 0, related=(), details: dict | None = None):
        self.code, self.message, self.line = code, message, line
        self.span: Span | None = None
        self.related: list[Related] = list(related)
        self.details: dict = dict(details or {})
        super().__init__(message)

    def render(self, source: str) -> str:
        where = f"{source}:{self.line}" if self.line else source
        return f"{where}: {self.code}\n  " + self.message.replace("\n", "\n  ")

    def locate(self, source: str, force: bool = False) -> CheckError:
        """Compute spans against the checked source text; an already located error is kept unless forced."""
        if self.span is None or force:
            self.span = statement_span(source, self.line)
            for item in self.related:
                item.span = name_span(source, item.line, item.name) if item.line else None
        return self

    def diagnostic(self, file: str, source: str | None = None, stage: str = "check", rule: str | None = None,
                   secondary_rules=(), category: str = "specification") -> dict:
        """This error as a weave-diagnostic-v1 document; the rule mapping is supplied by the caller."""
        if source is not None:
            self.locate(source)

        def region(span: Span | None):
            if span is None:
                return None
            return {"file": file, "start": {"line": span.line, "column": span.column},
                    "end": {"line": span.end_line, "column": span.end_column}}

        return {"format": DIAGNOSTIC_FORMAT, "code": self.code, "category": category, "rule": rule,
                "secondary_rules": list(secondary_rules), "severity": "error", "stage": stage,
                "message": self.message, "span": region(self.span),
                "related": [{"role": r.role, "label": r.label, "span": region(r.span)}
                            for r in self.related if r.span is not None],
                "details": dict(self.details)}


def located(source_of):
    """Locate any CheckError raised by the wrapped function against the source text it checked."""
    def wrap(function):
        @functools.wraps(function)
        def inner(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except CheckError as error:
                error.locate(source_of(*args, **kwargs))
                raise
        return inner
    return wrap


def at_line(error: CheckError, line: int) -> CheckError:
    """Give an error raised without a line (by a helper parser) the line of the enclosing statement."""
    if not error.line:
        error.line = line
    return error


@dataclass
class Node:
    text: str
    line: int
    children: list[Node] = field(default_factory=list)
    origin: str | None = None


def tree(source: str) -> list[Node]:
    roots: list[Node] = []
    stack: list[tuple[int, list[Node]]] = [(-4, roots)]
    previous: Node | None = None
    previous_indent = -4
    for number, raw in enumerate(source.splitlines(), 1):
        if "\t" in raw:
            raise CheckError("E001", "Tabs are not supported.", number)
        text = raw.split("#", 1)[0].rstrip()
        if not text.strip():
            continue
        indent = len(text) - len(text.lstrip())
        if indent % 4:
            raise CheckError("E001", "Indentation must use four spaces.", number)
        if indent > previous_indent:
            if indent != previous_indent + 4:
                raise CheckError("E001", "Indentation skipped a level.", number)
            if previous is not None:
                if not previous.text.endswith(":"):
                    raise CheckError("E001", "Unexpected nested block.", number)
                stack.append((previous_indent, previous.children))
        else:
            while stack[-1][0] >= indent:
                stack.pop()
        node = Node(text.strip(), number)
        stack[-1][1].append(node)
        previous, previous_indent = node, indent
    return roots


def split_commas(text: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for i, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 1
        if depth < 0:
            raise CheckError("E002", "Unbalanced type brackets.")
    if depth:
        raise CheckError("E002", "Unbalanced type brackets.")
    if text.strip():
        parts.append(text[start:].strip())
    if any(not part for part in parts):
        raise CheckError("E002", "Empty argument or type index.")
    return parts


@dataclass(frozen=True)
class Type:
    name: str
    keys: tuple[str, ...] = ()

    def __str__(self) -> str:
        suffix = f"[{', '.join(self.keys)}]" if self.keys else ""
        return self.name + suffix


def type_of(text: str) -> Type:
    match = re.fullmatch(r"(\w+)(?:\[([\w, ]+)\])?", text.strip())
    if not match:
        raise CheckError("E002", f"Unsupported type: {text}. Use nominal types; no open unions.")
    keys = tuple(split_commas(match[2] or ""))
    if any(not re.fullmatch(r"[A-Za-z_]\w*", key) for key in keys):
        raise CheckError("E002", "Type indices must be identifiers.")
    return Type(match[1], keys)


def parameters(text: str) -> list[tuple[str, Type]]:
    result = []
    for part in split_commas(text):
        match = re.fullmatch(r"([A-Za-z_]\w*)\s*:\s*(.+)", part)
        if not match or any(name == match[1] for name, _ in result):
            raise CheckError("E002", f"Invalid or duplicate parameter: {part}")
        result.append((match[1], type_of(match[2])))
    return result


@dataclass
class Place:
    initial: str
    owner: str


@dataclass
class Transition:
    name: str
    line: int
    take: dict[str, int] = field(default_factory=dict)
    put: dict[str, int] = field(default_factory=dict)
    read: dict[str, int] = field(default_factory=dict)
    guards: list[str] = field(default_factory=list)


@dataclass
class Resource:
    name: str
    keys: tuple[str, ...]
    place: str
    issuer: str
    cancel: str
    registration: str | None
    line: int


@dataclass
class Enum:
    keys: tuple[str, ...]
    cases: dict[str, Type]


@dataclass
class Signature:
    params: list[tuple[str, Type]]
    result: Type
    via: str
    line: int
    pending: str | None = None
    outcomes: dict[str, str] = field(default_factory=dict)
    key_source: tuple[str, ...] = ()
    correlation: str | None = None


@dataclass
class OrderCheck:
    name: str
    admission: str
    dispatch: str
    bound: int
    guards: dict[str, str]
    properties: dict[str, tuple[str, str, str]]
    line: int


@dataclass
class Net:
    name: str
    parameter: str
    source: str
    places: dict[str, Place] = field(default_factory=dict)
    transitions: dict[str, Transition] = field(default_factory=dict)
    resources: dict[str, Resource] = field(default_factory=dict)
    enums: dict[str, Enum] = field(default_factory=dict)
    invariants: dict[str, tuple[str, int]] = field(default_factory=dict)
    apis: dict[str, Signature] = field(default_factory=dict)
    runtime_cancels: dict[str, str] = field(default_factory=dict)
    runtime_consumers: dict[str, tuple[tuple[str, ...], int]] = field(default_factory=dict)
    order_check: OrderCheck | None = None
    header_line: int = 0
    # Text that diagnostic lines refer to, when it differs from ``source`` (a coloured net's erased view).
    span_source: str | None = None


def net_text(net: Net, *_, **__) -> str:
    return net.span_source or net.source


def insert(mapping: dict, name: str, value: object, line: int) -> None:
    if name in mapping:
        raise CheckError("E003", f"Duplicate declaration: {name}", line)
    mapping[name] = value


def leaf(node: Node) -> None:
    if node.children:
        raise CheckError("E003", "This declaration cannot contain a block.", node.line)


@located(lambda source: source)
def parse_net(source: str) -> Net:
    roots = tree(source)
    match = re.fullmatch(r"net (\w+)\((\w+): Nat\):", roots[0].text) if len(roots) == 1 else None
    if not match:
        raise CheckError("E003", "Expected one net Name(stock: Nat) block.", roots[-1].line if roots else 0)
    net = Net(match[1], match[2], source, header_line=roots[0].line)
    for node in roots[0].children:
        try:
            parse_declaration(net, node)
        except CheckError as error:
            raise at_line(error, node.line)
    validate(net)
    return net


def parse_declaration(net: Net, node: Node) -> None:
    line, text = node.line, node.text
    if m := re.fullmatch(r"place (\w+) = (\w+) owner (domain|activation|runtime|adapter)", text):
        leaf(node)
        if m[2] != net.parameter and not m[2].isdigit():
            raise CheckError("E003", "Initial count must be Nat or the stock parameter.", line)
        insert(net.places, m[1], Place(m[2], m[3]), line)
    elif m := re.fullmatch(r"linear (\w+)\[([\w, ]+)\] at (\w+) issuer (\w+) cancel (\w+)(?: registered (\w+))?", text):
        leaf(node)
        r = Resource(m[1], tuple(split_commas(m[2])), m[3], m[4], m[5], m[6], line)
        insert(net.resources, r.name, r, line)
    elif m := re.fullmatch(r"enum (\w+)\[([\w, ]+)\]:", text):
        cases = {}
        for child in node.children:
            leaf(child)
            case = re.fullmatch(r"(\w+)\((.+)\)", child.text)
            if not case:
                raise CheckError("E003", "Expected a named enum constructor with one payload.", child.line)
            insert(cases, case[1], type_of(case[2]), child.line)
        if not cases:
            raise CheckError("E003", "An enum needs at least one case.", line)
        insert(net.enums, m[1], Enum(tuple(split_commas(m[2])), cases), line)
    elif m := re.fullmatch(r"invariant (\w+):", text):
        if len(node.children) != 1:
            raise CheckError("E003", "An invariant needs one equality.", line)
        leaf(node.children[0])
        insert(net.invariants, m[1], (node.children[0].text, node.children[0].line), line)
    elif m := re.fullmatch(r"check (\w+) for one_order:", text):
        if net.order_check is not None:
            raise CheckError("E300", "Only one order-check model is supported.", line)
        clauses, guards, properties = {}, {}, {}
        for child in node.children:
            leaf(child)
            if clause := re.fullmatch(r"admit (\w+) once", child.text):
                insert(clauses, "admission", clause[1], child.line)
            elif clause := re.fullmatch(r"observe dispatch (\w+)", child.text):
                insert(clauses, "dispatch", clause[1], child.line)
            elif clause := re.fullmatch(r"place_bound ([1-9]\d*)", child.text):
                insert(clauses, "bound", int(clause[1]), child.line)
            elif clause := re.fullmatch(r"guard (\w+) (establishes_paid|establishes_rejected|nondeterministic)", child.text):
                insert(guards, clause[1], clause[2], child.line)
            elif clause := re.fullmatch(r"property (\w+): marked (\w+) requires (paid_evidence|rejected_evidence|marked \w+)", child.text):
                insert(properties, clause[1], ("requires", clause[2], clause[3]), child.line)
            elif clause := re.fullmatch(r"property (\w+): after paid_evidence forbid (\w+)", child.text):
                insert(properties, clause[1], ("forbid", clause[2], "paid_evidence"), child.line)
            elif clause := re.fullmatch(r"property (\w+): after dispatch marked (\w+) requires rejected_evidence", child.text):
                insert(properties, clause[1], ("after_dispatch", clause[2], "rejected_evidence"), child.line)
            else:
                raise CheckError("E300", f"Unsupported order-check clause: {child.text}", child.line)
        if set(clauses) != {"admission", "dispatch", "bound"} or not properties:
            raise CheckError("E300", "Order check needs admission, dispatch observation, place_bound, and properties.", line)
        net.order_check = OrderCheck(m[1], clauses["admission"], clauses["dispatch"], clauses["bound"], guards, properties, line)
    elif m := re.fullmatch(r"transition (\w+):", text):
        transition = Transition(m[1], line)
        for child in node.children:
            leaf(child)
            if arc := re.fullmatch(r"(take|put|read) ([1-9]\d*) (\w+)", child.text):
                insert(getattr(transition, arc[1]), arc[3], int(arc[2]), child.line)
            elif guard := re.fullmatch(r"guard (\w+)", child.text):
                transition.guards.append(guard[1])
            else:
                raise CheckError("E003", f"Unsupported transition statement: {child.text}", child.line)
        if not node.children:
            raise CheckError("E003", "Empty transition.", line)
        insert(net.transitions, transition.name, transition, line)
    elif m := re.fullmatch(r"runtime_cancel (\w+) via (\w+)", text):
        leaf(node)
        insert(net.runtime_cancels, m[1], m[2], line)
    elif m := re.fullmatch(r"runtime_state (\w+) (?:consumers ([\w, ]+)|terminal)", text):
        leaf(node)
        consumers = tuple(split_commas(m[2])) if m[2] else ()
        if len(set(consumers)) != len(consumers):
            raise CheckError("E100", "Duplicate runtime consumer.", line)
        insert(net.runtime_consumers, m[1], (consumers, line), line)
    elif m := re.fullmatch(r"api (\w+)\((.*)\) -> (.+) via (\w+)", text):
        leaf(node)
        insert(net.apis, net.name + "." + m[1], Signature(parameters(m[2]), type_of(m[3]), m[4], line), line)
    elif m := re.fullmatch(r"foreign ([\w.]+)\((.*)\) -> (.+):", text):
        sig = Signature(parameters(m[2]), type_of(m[3]), "", line)
        seen = set()
        for child in node.children:
            leaf(child)
            if clause := re.fullmatch(r"(dispatch|pending) (\w+)", child.text):
                if clause[1] in seen:
                    raise CheckError("E003", "Duplicate foreign clause.", child.line)
                seen.add(clause[1])
                if clause[1] == "dispatch":
                    sig.via = clause[2]
                else:
                    sig.pending = clause[2]
            elif clause := re.fullmatch(r"keyed by ([\w, ]+)", child.text):
                if sig.key_source:
                    raise CheckError("E003", "Duplicate key source.", child.line)
                sig.key_source = tuple(split_commas(clause[1]))
            elif child.text == "correlate client_key or provider_reference":
                if sig.correlation:
                    raise CheckError("E003", "Duplicate correlation clause.", child.line)
                sig.correlation = "client_key or provider_reference"
            elif clause := re.fullmatch(r"outcome (\w+) via (\w+)", child.text):
                insert(sig.outcomes, clause[1], clause[2], child.line)
            else:
                raise CheckError("E003", "Unsupported foreign clause.", child.line)
        if not sig.via or not sig.pending or not sig.key_source or not sig.correlation:
            raise CheckError("E003", "Foreign operation needs dispatch, pending, key source, and correlation.", line)
        insert(net.apis, m[1], sig, line)
    else:
        raise CheckError("E003", f"Unsupported net declaration: {text}", line)


def validate(net: Net) -> None:
    def fail(message: str, line: int = 0) -> None:
        raise CheckError("E100", message, line or net.header_line)

    def transition(name: str) -> Transition:
        if name not in net.transitions:
            fail(f"Unknown transition: {name}")
        return net.transitions[name]

    if not net.places or not net.transitions or not net.invariants:
        fail("A net needs places, transitions, and declared invariants.")
    for t in net.transitions.values():
        unknown = (t.take.keys() | t.put.keys() | t.read.keys()) - net.places.keys()
        if unknown:
            fail(f"Unknown places in {t.name}: {sorted(unknown)}", t.line)
    by_place = {}
    for resource in net.resources.values():
        if resource.place not in net.places or net.places[resource.place].owner != "activation":
            fail(f"{resource.name} must name an activation-owned place.", resource.line)
        if resource.place in by_place:
            fail("Two resource types cannot own the same place.", resource.line)
        if net.places[resource.place].initial != "0":
            fail("Sealed resources must be issued by a transition, not initial handles.", resource.line)
        by_place[resource.place] = resource
        producers = [t.name for t in net.transitions.values() if t.put.get(resource.place, 0)]
        if producers != [resource.issuer] or transition(resource.issuer).put[resource.place] != 1:
            fail(f"{resource.name} must be minted only, once per firing, by {resource.issuer}.", resource.line)
        if len(set(resource.keys)) != len(resource.keys):
            fail("Duplicate resource type index.", resource.line)
        if resource.registration:
            if resource.registration not in net.places or net.places[resource.registration].owner != "runtime":
                fail("Recovery registration must be a runtime-owned place.", resource.line)
            if transition(resource.issuer).put.get(resource.registration) != 1:
                fail(f"Issuing {resource.name} must atomically register recovery.", resource.line)
    if {p for p, v in net.places.items() if v.owner == "activation"} != set(by_place):
        fail("Every activation-owned place needs one linear resource declaration.")

    def verify_cancel(place: str, name: str) -> None:
        t = transition(name)
        if t.take.get(place) != 1 or t.guards or t.read:
            fail(f"Cancellation {name} must consume its resource and have no guard/read wait.", t.line)
        if any(net.places[p].owner == "activation" for p in t.put):
            fail(f"Cancellation {name} must transfer all outputs to durable owners.", t.line)
        # Additional consumed tokens may only be armed recovery registrations.
        registration_places = {r.registration for r in net.resources.values() if r.registration}
        if any(p != place and p not in registration_places for p in t.take):
            fail(f"Cancellation {name} waits for another resource.", t.line)
    for resource in net.resources.values():
        verify_cancel(resource.place, resource.cancel)
    for place, cancel in net.runtime_cancels.items():
        if place not in net.places or net.places[place].owner != "runtime":
            fail("A runtime cancellation target must be runtime-owned.")
        verify_cancel(place, cancel)
    for name, enum in net.enums.items():
        if name in net.resources or name == "Unit" or len(set(enum.keys)) != len(enum.keys):
            fail(f"Invalid or colliding enum: {name}")
        for payload in enum.cases.values():
            if payload == Type("Unit"):
                continue
            if payload.name not in net.resources or len(payload.keys) != len(net.resources[payload.name].keys):
                fail("This fragment requires each enum case to contain one linear resource.")
            if set(payload.keys) - set(enum.keys):
                fail("Unbound enum payload index.")

    def activation_arcs(arcs: dict[str, int]) -> Counter:
        return Counter({p: n for p, n in arcs.items() if p in by_place})

    for name, sig in net.apis.items():
        t = transition(sig.via)
        inputs = Counter()
        bound_keys = {p for p, typ in sig.params if typ.name not in net.resources and not typ.keys}
        resource_params = []
        for _, typ in sig.params:
            if typ.name in net.enums:
                fail("Enum parameters are not supported in net API declarations.", sig.line)
            if typ.name in net.resources:
                r = net.resources[typ.name]
                if len(typ.keys) != len(r.keys):
                    fail("Resource type has incorrect index arity.", sig.line)
                inputs[r.place] += 1
                bound_keys.update(typ.keys)
                resource_params.append(typ)
            elif typ.keys or typ.name == "Unit":
                fail("Invalid scalar parameter type.", sig.line)
        if inputs != activation_arcs(t.take):
            fail(f"{name}: signature does not consume the transition's activation resources.", sig.line)
        if activation_arcs(t.read):
            fail("Borrowing linear handles through read arcs is not supported in this fragment.", sig.line)
        if set(sig.result.keys) - bound_keys:
            fail("Unbound result index.", sig.line)
        if sig.pending is None:
            outputs = Counter()
            if sig.result.name in net.resources:
                r = net.resources[sig.result.name]
                if len(sig.result.keys) != len(r.keys):
                    fail("Result index arity mismatch.", sig.line)
                outputs[r.place] = 1
            elif sig.result != Type("Unit"):
                fail("Local APIs return a resource or Unit in this fragment.", sig.line)
            if outputs != activation_arcs(t.put):
                fail(f"{name}: result does not account for produced activation resources.", sig.line)
        else:
            if sig.pending not in net.places or net.places[sig.pending].owner != "runtime":
                fail("Foreign pending state must be runtime-owned.", sig.line)
            if sig.pending not in net.runtime_cancels:
                fail("Foreign pending state needs an explicit cancellation route.", sig.line)
            if t.put.get(sig.pending) != 1 or activation_arcs(t.put):
                fail("Foreign dispatch must transfer its resource into pending runtime ownership.", sig.line)
            if len(resource_params) != 1:
                fail("Foreign dispatch requires exactly one linear permit in this fragment.", sig.line)
            permit = net.resources[resource_params[0].name]
            if not permit.registration or t.read.get(permit.registration, 0) + t.take.get(permit.registration, 0) < 1:
                fail("Foreign dispatch requires an armed recovery registration.", sig.line)
            if sig.key_source != resource_params[0].keys:
                fail("Idempotency key fields must equal the permit's declared identity indices.", sig.line)
            scalar_names = {p for p, typ in sig.params if typ.name not in net.resources}
            if set(sig.key_source) - scalar_names:
                fail("Key fields must name explicit scalar parameters.", sig.line)
            if sig.result.name not in net.enums:
                fail("Foreign results must be a declared closed outcome enum.", sig.line)
            enum = net.enums[sig.result.name]
            if len(sig.result.keys) != len(enum.keys) or set(enum.cases) != {"Ok", "Err", "Unknown"}:
                fail("Foreign outcome must have exactly Ok, Err, Unknown.", sig.line)
            if set(sig.outcomes) != set(enum.cases):
                fail("Foreign outcome transition mapping is not exhaustive.", sig.line)
            substitution = dict(zip(enum.keys, sig.result.keys))
            for tag, target in sig.outcomes.items():
                out = transition(target)
                payload = enum.cases[tag]
                if payload.name not in net.resources:
                    fail("Foreign outcomes must carry a linear protocol resource.", sig.line)
                if tuple(substitution[k] for k in payload.keys) != resource_params[0].keys:
                    fail("Outcome resource identity must match the consumed permit.", sig.line)
                if out.take.get(sig.pending) != 1 or activation_arcs(out.take):
                    fail("Outcome must consume pending runtime state.", out.line)
                if activation_arcs(out.put) != Counter({net.resources[payload.name].place: 1}):
                    fail("Outcome transition and enum payload disagree.", out.line)

    # Seal consumption too: exported signatures above account for every handle
    # consumed by their via transition; no other firing may steal that handle.
    for place, resource in by_place.items():
        allowed = {resource.cancel} | {
            sig.via for sig in net.apis.values()
            if any(typ.name == resource.name for _, typ in sig.params)
        }
        for t in net.transitions.values():
            if place in t.take and t.name not in allowed:
                raise CheckError("E101", f"{t.name} cannot consume sealed {resource.name} at {place}.\nAllowed consumers: {', '.join(sorted(allowed))}.", t.line)
            if place in t.read:
                raise CheckError("E101", f"{t.name} cannot read activation-owned {place}; linear borrowing is unsupported.", t.line)

    # Every runtime-owned place has a closed list, including registration state.
    # Omitting a declaration must not silently reopen that place to theft.
    runtime_places = {p for p, value in net.places.items() if value.owner == "runtime"}
    if runtime_places != net.runtime_consumers.keys():
        fail(f"Runtime consumer declarations must cover exactly runtime-owned places. Missing: {sorted(runtime_places - net.runtime_consumers.keys())}; extra: {sorted(net.runtime_consumers.keys() - runtime_places)}.")
    for place, (allowed, line) in net.runtime_consumers.items():
        for consumer in allowed:
            if transition(consumer).take.get(place) != 1:
                fail(f"Declared consumer {consumer} must take exactly one {place} token.", line)
        for t in net.transitions.values():
            if place in t.take and t.name not in allowed:
                raise CheckError("E101", f"{t.name} cannot consume sealed runtime state {place}.\nAllowed consumers: {', '.join(allowed) or '<none>'}.", t.line)

    if net.order_check:
        model = net.order_check
        if model.admission not in net.transitions:
            raise CheckError("E300", "Unknown admission transition.", model.line)
        dispatches = {sig.via for sig in net.apis.values() if sig.pending is not None}
        if dispatches != {model.dispatch}:
            raise CheckError("E300", "This one-operation model must observe the foreign dispatch transition.", model.line)
        used_guards = {g for t in net.transitions.values() for g in t.guards}
        if used_guards - model.guards.keys():
            raise CheckError("E300", f"Unclassified guards: {sorted(used_guards - model.guards.keys())}", model.line)
        for _, place, requirement in model.properties.values():
            required = requirement.removeprefix("marked ") if requirement.startswith("marked ") else None
            if place not in net.places or (required is not None and required not in net.places):
                raise CheckError("E300", "Property names an undeclared place.", model.line)


def linear_expression(text: str) -> tuple[dict[str, int], int]:
    """Parse exact affine integer expressions, without evaluating user code."""
    try:
        expression = ast.parse(text.strip(), mode="eval").body
    except SyntaxError as error:
        raise CheckError("E110", "Invalid invariant expression.") from error

    def visit(node: ast.AST) -> tuple[dict[str, int], int]:
        if isinstance(node, ast.Name):
            return {node.id: 1}, 0
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return {}, node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            terms, constant = visit(node.operand)
            return {k: -v for k, v in terms.items()}, -constant
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            a, ac = visit(node.left)
            b, bc = visit(node.right)
            sign = 1 if isinstance(node.op, ast.Add) else -1
            terms = dict(a)
            for key, value in b.items():
                terms[key] = terms.get(key, 0) + sign * value
            return {k: v for k, v in terms.items() if v}, ac + sign * bc
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            a, ac = visit(node.left)
            b, bc = visit(node.right)
            if a and b:
                raise CheckError("E110", "Only linear invariants are supported.")
            if not a:
                return {k: ac * v for k, v in b.items()}, ac * bc
            return {k: bc * v for k, v in a.items()}, ac * bc
        raise CheckError("E110", "Only names, integers, +, -, and scalar multiplication are supported.")
    return visit(expression)


@located(net_text)
def prove(net: Net) -> dict:
    places, transitions = list(net.places), list(net.transitions)
    incidence = [[net.transitions[t].put.get(p, 0) - net.transitions[t].take.get(p, 0)
                  for t in transitions] for p in places]
    initial = [[1, 0] if net.places[p].initial == net.parameter else [0, int(net.places[p].initial)] for p in places]
    results = []
    for name, (expression, line) in net.invariants.items():
        parts = expression.split("==")
        if len(parts) != 2:
            raise CheckError("E110", "Invariant must be an equality.", line)
        try:
            lhs, lc = linear_expression(parts[0])
            rhs, rc = linear_expression(parts[1])
        except CheckError as error:
            raise at_line(error, line)
        if set(lhs) - set(places) or set(rhs) - {net.parameter}:
            raise CheckError("E110", "Left side must name places; right side may name only the stock parameter.", line)
        weights = [lhs.get(p, 0) for p in places]
        if not any(weights):
            raise CheckError("E110", "Invariant must have a nonzero place vector.", line)
        target = [rhs.get(net.parameter, 0), rc - lc]
        actual = [sum(w * values[k] for w, values in zip(weights, initial)) for k in (0, 1)]
        if actual != target:
            raise CheckError("E111", f"{name}: initial marking does not satisfy the invariant; got {actual}, expected {target} as [stock coefficient, constant].", line)
        residuals = [sum(weights[i] * incidence[i][j] for i in range(len(places))) for j in range(len(transitions))]
        failures = [(transitions[j], value) for j, value in enumerate(residuals) if value]
        if failures:
            transition_name, value = failures[0]
            raise CheckError("E112", f"{name} is NOT PROVED: transition {transition_name} changes the invariant by {value:+d}.\nSee transition at line {net.transitions[transition_name].line}.", line)
        results.append({"name": name, "expression": expression, "status": "PROVED", "weights": weights,
                        "initial_actual": actual, "initial_target": target, "transition_residuals": residuals})
    return {"format": "weave-place-invariant-v1", "net": net.name, "parameter": net.parameter,
            "source_sha256": hashlib.sha256(net.source.encode()).hexdigest(),
            "places": places, "transitions": transitions, "incidence": incidence,
            "initial_affine": initial, "invariants": results,
            "scope": "All finite firing sequences, every nonnegative integer stock; named guards relaxed. No reachability enumeration."}


@located(net_text)
def explore_order(net: Net, max_states: int = 10000) -> dict:
    """Exhaust the declared one-order abstraction, or fail without a safety label.

    Guards classified establishes_paid/rejected witness evidence on that firing.
    Other guards are nondeterministic predicates: their true branch is explored;
    their false branch is stuttering and adds no safety-relevant state. No guard
    creates evidence elsewhere, and every net transition participates.
    """
    model = net.order_check
    if model is None:
        raise CheckError("E300", "NOT ESTABLISHED: no one-order check declared.", net.header_line)
    if max_states < 1:
        raise CheckError("E321", "NOT ESTABLISHED: state budget must be positive.", model.line)
    places = list(net.places)
    index = {p: i for i, p in enumerate(places)}
    initial = tuple(1 if p.initial == net.parameter else int(p.initial) for p in net.places.values())
    if any(n > model.bound for n in initial):
        raise CheckError("E321", "NOT ESTABLISHED: initial marking exceeds place_bound.", model.line)
    # State: marking, admitted, dispatched, paid witness, rejection witness.
    # Witnesses never reset and are not silently made mutually exclusive.
    start = (initial, False, False, False, False)
    parents = {start: None}
    pending = deque([start])
    fired = set()
    edges = 0
    triggers = dict.fromkeys(model.properties, 0)

    def trace(state, last=None):
        path = [] if last is None else [last]
        while parents[state] is not None:
            state, transition_name = parents[state]
            path.append(transition_name)
        return " -> ".join(reversed(path)) or "<initial marking>"

    def inspect(state, path):
        marking, _, dispatched, paid, rejected = state
        for name, (kind, place, requirement) in model.properties.items():
            present = marking[index[place]] > 0
            premise = paid if kind == "forbid" else present
            if kind == "after_dispatch":
                premise = dispatched and present
            if kind == "forbid":
                valid = not present
            elif requirement == "paid_evidence":
                valid = paid
            elif requirement == "rejected_evidence":
                valid = rejected
            else:
                valid = marking[index[requirement.removeprefix("marked ")]] > 0
            if premise and not valid:
                occupied = ", ".join(f"{p}={marking[i]}" for p, i in index.items() if marking[i])
                raise CheckError("E320", f"VIOLATED {name} within one-order model.\nTrace: {path}\nMarking: {occupied}; dispatched={str(dispatched).lower()}, paid_evidence={str(paid).lower()}, rejected_evidence={str(rejected).lower()}.", model.line)

    inspect(start, "<initial marking>")
    while pending:
        state = pending.popleft()
        marking, admitted, dispatched, paid, rejected = state
        for name, (kind, place, _) in model.properties.items():
            premise = paid if kind == "forbid" else marking[index[place]] > 0
            if kind == "after_dispatch":
                premise = dispatched and marking[index[place]] > 0
            if premise:
                triggers[name] += 1
        for t in net.transitions.values():
            if t.name == model.admission and admitted:
                continue
            if any(marking[index[p]] < n for arcs in (t.take, t.read) for p, n in arcs.items()):
                continue
            after = tuple(marking[i] - t.take.get(p, 0) + t.put.get(p, 0) for p, i in index.items())
            new_paid = paid or any(model.guards[g] == "establishes_paid" for g in t.guards)
            new_rejected = rejected or any(model.guards[g] == "establishes_rejected" for g in t.guards)
            next_state = (after, admitted or t.name == model.admission,
                          dispatched or t.name == model.dispatch, new_paid, new_rejected)
            path = trace(state, t.name)
            # No successor is silently pruned to obtain a safety result.
            if any(n > model.bound for n in after):
                raise CheckError("E321", f"NOT ESTABLISHED: place_bound={model.bound} exceeded.\nTrace: {path}", t.line)
            inspect(next_state, path)
            edges += 1
            fired.add(t.name)
            if next_state not in parents:
                if len(parents) >= max_states:
                    raise CheckError("E321", f"NOT ESTABLISHED: state budget {max_states} exhausted.", model.line)
                parents[next_state] = (state, t.name)
                pending.append(next_state)
    return {
        "format": "weave-one-order-check-v2",
        "source_sha256": hashlib.sha256(net.source.encode()).hexdigest(),
        "model": model.name, "stock": 1, "orders": 1,
        "admission": model.admission, "admission_limit": 1,
        "dispatch": model.dispatch,
        "place_bound": model.bound, "max_states": max_states,
        "states": len(parents), "edges": edges, "complete": True,
        "fired_transitions": sorted(fired),
        "unreached_transitions": sorted(net.transitions.keys() - fired),
        "properties": [{"name": name, "status": "CHECKED WITHIN BOUNDS", "premise_states": triggers[name]}
                       for name in model.properties],
        "assumptions": ["One identity, one stock unit, at most one admission; no other orders.",
                        "Payment and final-rejection evidence are abstract witnesses, assumed truthful, consistent, and correlated to this order.",
                        "Independent contradictory/late provider replies and quantitative escalation budgets are not modeled.",
                        "Other guards may enable nondeterministically; no liveness or fairness claim."],
    }


def ordering_text(result: dict) -> str:
    lines = [f"MODEL {result['model']}: orders=1, stock=1, {result['admission']}<=1, tokens/place<={result['place_bound']}",
             f"  Exhausted {result['states']} states and {result['edges']} edges; no successors pruned."]
    for prop in result["properties"]:
        lines.append(f"CHECKED WITHIN BOUNDS {prop['name']} (premise in {prop['premise_states']} states)")
    lines.append("  Evidence guards are abstract witnesses; provider truthfulness, consistency, and identity correlation are assumptions.")
    return "\n".join(lines)


@dataclass
class Binding:
    type: Type
    symbol: str
    line: int
    live: bool = True
    moved: int = 0  # line of the statement that consumed a linear binding


def binding_spans(name: str, binding: Binding) -> list[Related]:
    """Where a linear binding was bound and, once moved, where it was consumed."""
    related = [Related("binding", f"{name}: {binding.type} is bound here", binding.line, name)] if binding.line else []
    if binding.moved:
        related.append(Related("moved", f"{name} was consumed here", binding.moved, name))
    return related


def is_linear(net: Net, typ: Type) -> bool:
    return typ.name in net.resources or typ.name in net.enums


@located(lambda source: source)
def lower_questions(source: str) -> list[Node]:
    """Lower ? to ordinary terminal matches with source-line diagnostics.

    All branch ownership checks are then performed by the existing checker.
    In particular there is no implicit drop, cleanup, or cancellation at ?.
    """
    used = set(re.findall(r"\w+", source))
    counter = 0

    def fresh():
        nonlocal counter
        while True:
            counter += 1
            name = f"_try_{counter}"
            if name not in used:
                used.add(name)
                return name

    def lower(nodes):
        lowered = []
        for position, node in enumerate(nodes):
            awaited = re.fullmatch(r"let (\w+) = \(await ([\w.]+)\((.*)\)\)\?", node.text)
            bound = re.fullmatch(r"let (\w+) = (\w+)\?", node.text)
            if awaited or bound:
                leaf(node)
                if awaited:
                    variable, operand = awaited[1], fresh()
                    lowered.append(Node(f"let {operand} = await {awaited[2]}({awaited[3]})", node.line))
                else:
                    variable, operand = bound[1], bound[2]
                err, unknown = fresh(), fresh()
                branches = [
                    Node(f"Ok({variable}):", node.line, lower(nodes[position + 1:])),
                    Node(f"Err({err}):", node.line, [Node(f"return Err({err})", node.line, origin="?")]),
                    Node(f"Unknown({unknown}):", node.line, [Node(f"return Unknown({unknown})", node.line, origin="?")]),
                ]
                lowered.append(Node(f"match {operand}:", node.line, branches))
                return lowered
            lowered.append(Node(node.text, node.line, lower(node.children)))
        return lowered

    return lower(tree(source))


@located(lambda source: source)
def lower_flow_source(source: str) -> str:
    def render(nodes, depth=0):
        lines = []
        for node in nodes:
            lines.append("    " * depth + node.text)
            lines.extend(render(node.children, depth + 1))
        return lines
    return "\n".join(render(lower_questions(source))) + "\n"


@located(lambda net, source: source)
def check_flow(net: Net, source: str) -> list[str]:
    roots = lower_questions(source)
    helpers = {}
    declarations = {}
    for root in roots:
        match = re.fullmatch(r"flow (\w+)\((.*)\)(?: -> (.+))?:", root.text)
        if not match or match[1] in helpers:
            raise CheckError("E200", "Expected a uniquely named flow with an optional nominal return type.", root.line)
        name = match[1]
        if name in net.resources or name in net.enums or name == "Unit":
            raise CheckError("E200", "Flow name collides with a type declaration.", root.line)
        try:
            sig = Signature(parameters(match[2]), type_of(match[3] or "Unit"), "", root.line)
        except CheckError as error:
            raise at_line(error, root.line)
        bound = set()
        linear_names = {p for p, typ in sig.params if is_linear(net, typ)}
        for param, typ in sig.params:
            if is_linear(net, typ):
                declaration = net.resources.get(typ.name) or net.enums[typ.name]
                if len(typ.keys) != len(declaration.keys) or set(typ.keys) & linear_names:
                    raise CheckError("E216", "Invalid flow parameter indices.", root.line)
                bound.update(typ.keys)
            elif typ.keys or typ.name == "Unit":
                raise CheckError("E216", "Unsupported scalar flow parameter.", root.line)
            else:
                bound.add(param)
        if is_linear(net, sig.result):
            declaration = net.resources.get(sig.result.name) or net.enums[sig.result.name]
            if len(sig.result.keys) != len(declaration.keys) or set(sig.result.keys) - bound:
                raise CheckError("E216", "Unbound or invalid flow result indices.", root.line)
        elif sig.result != Type("Unit"):
            raise CheckError("E216", "Flows return Unit, a linear handle, or a closed outcome enum.", root.line)
        helpers[name] = sig
        declarations[name] = root
    if not helpers:
        raise CheckError("E200", "No flows to check.")

    # Signatures allow forward references, but every helper body is checked.
    # Recursion is deliberately excluded; cyclic signatures cannot stand in for
    # an implemented ownership transfer.
    calls = {name: set() for name in helpers}
    def gather(nodes, edges):
        for node in nodes:
            call = re.fullmatch(r"(?:let \w+ = )?await ([\w.]+)\(.*\)", node.text)
            if call and call[1] in helpers:
                edges.add(call[1])
            gather(node.children, edges)
    for name, root in declarations.items():
        gather(root.children, calls[name])
    visited, active = set(), set()
    def visit(name):
        if name in active:
            raise CheckError("E218", f"Recursive flow calls are unsupported: {name}.", declarations[name].line)
        if name in visited:
            return
        active.add(name)
        for callee in sorted(calls[name]):
            visit(callee)
        active.remove(name)
        visited.add(name)
    for name in helpers:
        visit(name)

    for name, root in declarations.items():
        env = {}
        for param, typ in helpers[name].params:
            env[param] = Binding(typ, param, root.line)
        try:
            check_body(net, root.children, env, helpers, helpers[name].result)
        except CheckError as error:
            raise at_line(error, root.line)
    return list(helpers)


def apply_call(net: Net, name: str, arguments: str, env: dict[str, Binding], line: int,
               helpers: dict[str, Signature] | None = None) -> Type:
    constructor = name.split(".")[-1]
    if constructor in net.resources:
        resource = net.resources[constructor]
        raise CheckError("E205", f"{constructor} is sealed; it cannot be constructed by client code.\nIts only minting transition is {net.name}.{resource.issuer}.", line)
    signatures = net.apis | (helpers or {})
    if name not in signatures:
        raise CheckError("E206", f"Unknown or private operation: {name}. Only declared APIs are callable.", line)
    try:
        sig, args = signatures[name], split_commas(arguments)
    except CheckError as error:
        raise at_line(error, line)
    if len(args) != len(sig.params):
        missing = sig.params[len(args):]
        detail = ", ".join(f"{n}: {t}" for n, t in missing) if missing else "too many arguments"
        hint = ""
        for _, typ in missing:
            if typ.name in net.resources:
                r = net.resources[typ.name]
                hint += f"\nObtain {typ.name} through {net.name}.{r.issuer}; its constructor is sealed."
        raise CheckError("E201", f"{name} expects {len(sig.params)} arguments; got {len(args)}.\nMissing or invalid arguments: {detail}.{hint}", line)
    actual = []
    for arg in args:
        if not re.fullmatch(r"[A-Za-z_]\w*", arg) or arg not in env:
            raise CheckError("E207", f"Unknown argument binding: {arg}", line)
        binding = env[arg]
        if is_linear(net, binding.type) and not binding.live:
            raise CheckError("E203", f"{arg} was already moved; linear handles cannot be reused.", line,
                             binding_spans(arg, binding), {"binding": arg, "type": str(binding.type)})
        actual.append(binding)
    substitutions = {}
    for (param, expected), binding in zip(sig.params, actual):
        if expected.name != binding.type.name:
            raise CheckError("E208", f"{name}: expected {expected}, got {binding.type}.", line)
        if not is_linear(net, expected):
            substitutions[param] = binding.symbol
    to_move = []
    for arg, (_, expected), binding in zip(args, sig.params, actual):
        if len(expected.keys) != len(binding.type.keys):
            raise CheckError("E208", "Type index arity mismatch.", line)
        for wanted, found in zip(expected.keys, binding.type.keys):
            if wanted in substitutions and substitutions[wanted] != found:
                raise CheckError("E209", f"{name}: resource identity mismatch for {wanted}.\nRequest uses {substitutions[wanted]}; permit belongs to {found}.", line)
            substitutions[wanted] = found
        if is_linear(net, expected):
            if arg in to_move:
                raise CheckError("E203", f"{arg} would be consumed twice by one call.", line,
                                 binding_spans(arg, env[arg]), {"binding": arg, "type": str(env[arg].type)})
            to_move.append(arg)
    for arg in to_move:
        env[arg].live = False
        env[arg].moved = line
    try:
        return Type(sig.result.name, tuple(substitutions[k] for k in sig.result.keys))
    except KeyError as error:
        raise CheckError("E208", "Unresolved result identity.", line) from error


def check_body(net: Net, nodes: list[Node], env: dict[str, Binding],
               helpers: dict[str, Signature], result: Type) -> None:
    for position, node in enumerate(nodes):
        text, line = node.text, node.line
        if returned := re.fullmatch(r"return(?: (\w+)(?:\((\w*)\))?)?", text):
            leaf(node)
            expected, value_name = result, returned[1]
            if returned[2] is not None:
                if result.name not in net.enums or returned[1] not in net.enums[result.name].cases:
                    raise CheckError("E219", f"Return constructor {returned[1]} does not belong to {result}.", line)
                enum = net.enums[result.name]
                substitutions = dict(zip(enum.keys, result.keys))
                payload = enum.cases[returned[1]]
                expected = Type(payload.name, tuple(substitutions[k] for k in payload.keys))
                value_name = returned[2] or None
            if value_name is None:
                if expected != Type("Unit"):
                    raise CheckError("E217", f"Return requires {expected}.", line)
            else:
                value = env.get(value_name)
                if value is None:
                    raise CheckError("E207", f"Unknown return binding: {value_name}", line)
                if not value.live and is_linear(net, value.type):
                    raise CheckError("E203", f"{value_name} was already moved.", line,
                                     binding_spans(value_name, value), {"binding": value_name, "type": str(value.type)})
                if value.type != expected:
                    raise CheckError("E217", f"Return expects {expected}, got {value.type}.", line)
                if is_linear(net, value.type):
                    value.live = False
                    value.moved = line
            held = [(name, b) for name, b in env.items() if b.live and is_linear(net, b.type)]
            outstanding = [f"{name}: {b.type}" for name, b in held]
            if outstanding:
                related = [r for name, b in held for r in binding_spans(name, b)]
                details = {"outstanding": [{"name": name, "type": str(b.type)} for name, b in held],
                           "propagation": node.origin == "?"}
                if node.origin == "?":
                    related.append(Related("propagation", "'?' may propagate Err/Unknown here", line, "?"))
                    raise CheckError("E204", f"'?' on line {line} may propagate Err/Unknown while these linear handles are still held: " + ", ".join(outstanding) + ".\nConsume them before '?', or handle the outcome explicitly and return the obligations.", line, related, details)
                raise CheckError("E204", "Linear obligations left at normal return: " + ", ".join(outstanding) + ".\nConsume or hand off every handle. Cancellation routes do not permit silent normal drops.", line, related, details)
            if position != len(nodes) - 1:
                raise CheckError("E210", "Unreachable statements after return.", line)
            return
        if m := re.fullmatch(r"let (\w+) = (await )?([\w.]+)\((.*)\)", text):
            leaf(node)
            if m[1] in env:
                raise CheckError("E211", "Shadowing is not supported in this fragment.", line)
            if not m[2] and m[3].split(".")[-1] not in net.resources:
                raise CheckError("E212", "Net and foreign operations require await.", line)
            typ = apply_call(net, m[3], m[4], env, line, helpers)
            env[m[1]] = Binding(typ, m[1], line)
        elif m := re.fullmatch(r"await ([\w.]+)\((.*)\)", text):
            leaf(node)
            typ = apply_call(net, m[1], m[2], env, line, helpers)
            if typ != Type("Unit"):
                raise CheckError("E202", f"Discarded {typ}; bind the returned linear value.", line)
        elif m := re.fullmatch(r"match (\w+):", text):
            if position != len(nodes) - 1:
                raise CheckError("E213", "This fragment supports terminal matches only.", line)
            name = m[1]
            if name not in env or env[name].type.name not in net.enums:
                raise CheckError("E213", "Match requires a declared nominal outcome enum.", line)
            binding = env[name]
            if not binding.live:
                raise CheckError("E203", f"{name} was already moved.", line,
                                 binding_spans(name, binding), {"binding": name, "type": str(binding.type)})
            enum = net.enums[binding.type.name]
            cases = {}
            for child in node.children:
                case = re.fullmatch(r"(\w+)\((\w*)\):", child.text)
                if not case:
                    raise CheckError("E213", "Expected Case(payload): branch.", child.line)
                insert(cases, case[1], (case[2], child), child.line)
            if set(cases) != set(enum.cases):
                missing = sorted(set(enum.cases) - set(cases))
                extra = sorted(set(cases) - set(enum.cases))
                raise CheckError("E214", f"Non-exhaustive or invalid {binding.type.name} match. Missing {missing}; extra {extra}.", line)
            binding.live = False
            binding.moved = line
            substitutions = dict(zip(enum.keys, binding.type.keys))
            for tag, (variable, child) in cases.items():
                branch = copy.deepcopy(env)
                if variable in branch:
                    raise CheckError("E211", "Branch payload shadows another binding.", child.line)
                payload = enum.cases[tag]
                typ = Type(payload.name, tuple(substitutions[k] for k in payload.keys))
                if variable:
                    branch[variable] = Binding(typ, variable, child.line)
                elif typ != Type("Unit"):
                    raise CheckError("E202", f"Discarded {typ}; bind the branch payload.", child.line)
                try:
                    check_body(net, child.children, branch, helpers, result)
                except CheckError as error:
                    raise at_line(error, child.line)
            return
        else:
            raise CheckError("E200", f"Unsupported flow statement: {text}", line)
    raise CheckError("E215", "Flow path must end with return or an exhaustive terminal match.", nodes[-1].line if nodes else 0)


def proof_text(net: Net, certificate: dict) -> str:
    lines = [f"NET {net.name}: {len(net.places)} places, {len(net.transitions)} transitions",
             "METHOD standard P-invariant induction; aggregate accounting only"]
    for item in certificate["invariants"]:
        lines += [f"PROVED {item['name']}", f"  {item['expression']}",
                  f"  Initial marking: equality holds for every {net.parameter} >= 0.",
                  f"  Preservation: w^T C = 0 for all {len(net.transitions)} transition columns."]
    lines += [f"CHECKED {len(net.resources)} linear resources: sealed production, consumption, and cancellation routes",
              f"CHECKED {len(net.runtime_consumers)} runtime-owned places: closed consumer lists",
              "CHECKED foreign dispatch consumes an identity-matched, recovery-registered permit",
              "  These equalities do not establish payment ordering or per-order recovery coverage.",
              "NOT ESTABLISHED orders>=2 or cross-order token matching in this uncoloured model; liveness, provider truthfulness/consistency (including contradictory late replies), escalation budgets, or implementation refinement"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prove", "check", "order", "analyze"])
    parser.add_argument("net", type=Path)
    parser.add_argument("program", type=Path, nargs="?")
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--max-states", type=int, default=10000)
    args = parser.parse_args()
    source_label = str(args.net)
    try:
        net = parse_net(args.net.read_text())
        certificate = prove(net)
        if args.command in {"prove", "analyze"}:
            # Complete all requested checks before printing any success labels.
            ordering = explore_order(net, args.max_states) if args.command == "analyze" else None
            print(proof_text(net, certificate))
            if ordering:
                print(ordering_text(ordering))
            if args.certificate:
                args.certificate.write_text(json.dumps(certificate, indent=2) + "\n")
        elif args.command == "order":
            print(ordering_text(explore_order(net, args.max_states)))
        else:
            if args.program is None:
                parser.error("check requires a program path")
            explore_order(net, args.max_states)
            source_label = str(args.program)
            for name in check_flow(net, args.program.read_text()):
                print(f"CHECKED {name}: nominal types, indexed permits, exhaustive outcomes, no linear drops")
        return 0
    except CheckError as error:
        print(error.render(source_label), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
