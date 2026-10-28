"""Dependency graph, milestone gates and next-task selection.

Selection is deterministic: lowest unfinished milestone by numeric order, then
documented sequence (the epic's work-item order), then project rank when it is
available, then issue number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Issue, Snapshot, acceptance_criteria, milestone_key, milestone_order, sections

ISSUE_REF = re.compile(r"(?<![\w/])#(\d+)\b")


@dataclass
class Edge:
    blocked: int
    blocker: int
    provenance: list[str] = field(default_factory=list)


@dataclass
class Graph:
    edges: dict[tuple[int, int], Edge] = field(default_factory=dict)
    membership: dict[int, list[int]] = field(default_factory=dict)  # epic -> members
    contextual: dict[int, set[int]] = field(default_factory=dict)  # issue -> bare mentions
    findings: list[str] = field(default_factory=list)
    cycles: list[list[int]] = field(default_factory=list)

    def add(self, blocked: int, blocker: int, source: str) -> None:
        edge = self.edges.setdefault((blocked, blocker), Edge(blocked, blocker))
        if source not in edge.provenance:
            edge.provenance.append(source)

    def blockers_of(self, issue: int) -> list[Edge]:
        return [e for (b, _), e in sorted(self.edges.items()) if b == issue]

    def in_cycle(self, issue: int) -> bool:
        return any(issue in c for c in self.cycles)


def build_graph(snap: Snapshot, policy: dict) -> Graph:
    g = Graph()
    epics = {m["epic"] for m in policy["milestones"].values()}
    for issue in snap.issues.values():
        for n in issue.blocked_by:
            g.add(issue.number, n, "native GitHub blocked-by relationship")
        secs = sections(issue.body)
        for heading, text in secs.items():
            if heading.lower().startswith("depends on"):
                for n in map(int, ISSUE_REF.findall(text)):
                    g.add(issue.number, n, f"#{issue.number} body section '{heading}'")
            if heading.lower().startswith("work items") and issue.number in epics:
                g.membership[issue.number] = [int(n) for n in ISSUE_REF.findall(text)]
        if issue.sub_issues:
            g.membership.setdefault(issue.number, [])
            for n in issue.sub_issues:
                if n not in g.membership[issue.number]:
                    g.membership[issue.number].append(n)
        blocking_text = "\n".join(t for h, t in secs.items() if h.lower().startswith("depends on"))
        mentions = {int(n) for n in ISSUE_REF.findall(issue.body)} - {issue.number}
        mentions -= {int(n) for n in ISSUE_REF.findall(blocking_text)}
        mentions -= set(g.membership.get(issue.number, []))
        if mentions:
            g.contextual[issue.number] = mentions
    for dep in policy.get("dependencies", []):
        g.add(dep["issue"], dep["blocked_by"], f"policy.json: {dep['source']}")
    # Validate edges.
    for (blocked, blocker), edge in g.edges.items():
        if blocker not in snap.issues:
            g.findings.append(f"#{blocked} is blocked by unknown issue #{blocker} ({'; '.join(edge.provenance)})")
            continue
        mb, mk = snap.issues[blocked].milestone_key, snap.issues[blocker].milestone_key
        if mb and mk and milestone_order(mk) > milestone_order(mb):
            g.findings.append(f"contradictory dependency: #{blocked} ({mb}) is blocked by #{blocker} in later milestone {mk}")
        if blocker in epics:
            g.findings.append(f"#{blocked} is blocked by epic #{blocker}; epics are aggregate gates, not prerequisites")
    g.cycles = _cycles({k[0] for k in g.edges} | {k[1] for k in g.edges}, g.edges)
    for c in g.cycles:
        g.findings.append("dependency cycle: " + " -> ".join(f"#{n}" for n in c))
    # Cross-check prose milestone dependencies on epics against the policy baseline.
    for key, spec in policy["milestones"].items():
        epic = snap.issues.get(spec["epic"])
        if epic is None:
            g.findings.append(f"{key}: epic #{spec['epic']} not found")
            continue
        m = re.search(r"Depends on:\s*([^·\n;]+)", epic.body)
        if m:
            stated = sorted(set(re.findall(r"\bM\d+\b", m.group(1))), key=milestone_order)
            if stated != sorted(spec["requires"], key=milestone_order):
                g.findings.append(f"{key}: epic states predecessors {stated or ['Start']} but policy has {spec['requires']}")
    return g


def _cycles(nodes: set[int], edges: dict) -> list[list[int]]:
    adj: dict[int, list[int]] = {}
    for blocked, blocker in edges:
        adj.setdefault(blocked, []).append(blocker)
    color, stack, found = {}, [], []

    def visit(n: int) -> None:
        color[n] = 1
        stack.append(n)
        for m in sorted(adj.get(n, [])):
            if color.get(m) == 1:
                found.append(stack[stack.index(m):] + [m])
            elif color.get(m) is None:
                visit(m)
        stack.pop()
        color[n] = 2

    for n in sorted(nodes):
        if color.get(n) is None:
            visit(n)
    return found


# --------------------------------------------------------------------- gates


@dataclass
class GateResult:
    key: str
    passed: bool
    reasons: list[str]


def milestone_members(snap: Snapshot, policy: dict, key: str) -> list[Issue]:
    tracking = set(policy["labels"]["tracking"]) | set(policy["labels"]["deferred"])
    members = [i for i in snap.issues.values()
               if i.milestone_key == key and not tracking & set(i.labels)]
    for req in policy.get("cross_milestone_requirements", []):
        if req["required_by"] == key and req["issue"] in snap.issues:
            if snap.issues[req["issue"]] not in members:
                members.append(snap.issues[req["issue"]])
    return sorted(members, key=lambda i: i.number)


def milestone_gate(snap: Snapshot, policy: dict, key: str, gate_events: list[dict]) -> GateResult:
    spec = policy["milestones"][key]
    reasons = []
    epic = snap.issues.get(spec["epic"])
    for issue in milestone_members(snap, policy, key):
        if issue.state == "closed" and issue.state_reason == "not_planned":
            reasons.append(f"#{issue.number} closed as not planned (not success)")
        elif not issue.completed:
            reasons.append(f"#{issue.number} not completed")
        elif snap.project and snap.status_of(issue.number) != "Done":
            reasons.append(f"#{issue.number} closed but board status is {snap.status_of(issue.number)!r}, not Done")
    if epic is None or not epic.completed:
        reasons.append(f"epic #{spec['epic']} not closed as completed")
    passed_events = [e for e in gate_events if e.get("gate") == f"milestone-exit:{key}" and e.get("result") == "PASS"]
    if not passed_events:
        reasons.append(f"no recorded passing exit-gate evaluation for {key} (exit criteria, maintainer evidence, documentation audit)")
    return GateResult(key, not reasons, reasons)


# ---------------------------------------------------------------- selection


@dataclass
class Candidate:
    issue: int
    title: str
    milestone: str | None
    eligible: bool
    work_type: str = "implementation"
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sequence: tuple = ()


@dataclass
class Plan:
    milestone_order: list[str]
    gates: dict[str, GateResult]
    current: str | None
    candidates: list[Candidate]
    next: Candidate | None
    active: list[int]
    unscheduled: list[int]
    deferred: list[int]
    graph: Graph
    stop_reason: str | None = None
    provisional_next: Candidate | None = None


def plan(snap: Snapshot, policy: dict, gate_events: list[dict] | None = None,
         active_claims: list[int] | None = None) -> Plan:
    gate_events = gate_events or []
    graph = build_graph(snap, policy)
    keys = sorted(policy["milestones"], key=milestone_order)
    live_keys = {milestone_key(m.title) for m in snap.milestones}
    gates = {}
    for key in keys:
        gates[key] = milestone_gate(snap, policy, key, gate_events)
        if key not in live_keys:
            gates[key].reasons.append(f"milestone {key} not found on GitHub")
            gates[key].passed = False
    current = next((k for k in keys if not gates[k].passed), None)
    deferred_labels = set(policy["labels"]["deferred"])
    tracking = set(policy["labels"]["tracking"])
    deferred = sorted(i.number for i in snap.issues.values() if deferred_labels & set(i.labels) and i.state == "open")
    unscheduled = sorted(i.number for i in snap.issues.values()
                         if i.milestone is None and i.state == "open"
                         and not (deferred_labels | tracking) & set(i.labels))
    active = sorted(set(active_claims or []) | {
        n for n, i in snap.issues.items()
        if i.state == "open" and snap.status_of(n) == "In Progress"})
    candidates: list[Candidate] = []
    if current:
        missing_preds = [p for p in policy["milestones"][current]["requires"] if not gates[p].passed]
        epic_order = graph.membership.get(policy["milestones"][current]["epic"], [])
        for issue in milestone_members(snap, policy, current):
            if issue.milestone_key != current:
                continue  # cross-milestone requirement owned elsewhere: never scheduled twice
            candidates.append(_assess(issue, snap, policy, graph, missing_preds, epic_order))
        for exc in policy.get("early_start_exceptions", []):
            for n in exc["issues"]:
                if n in snap.issues and snap.issues[n].state == "open":
                    c = Candidate(n, snap.issues[n].title, snap.issues[n].milestone_key, False, "early-start")
                    c.reasons.append(f"early-start exception ({exc['allowed_scope']}) is "
                                     + ("active" if policy.get("early_start_exceptions_active") else "inactive")
                                     + f"; source: {exc['source']}")
                    if policy.get("early_start_exceptions_active") and exc["allowed_during"] in ("any", current):
                        c.eligible = True
                        c.notes.append("scope restricted to the exception; no dependency or exit gate is waived")
                    c.sequence = (1, 0, n)
                    candidates.append(c)
    eligible = sorted((c for c in candidates if c.eligible), key=lambda c: c.sequence)
    stop = None
    nxt = None
    max_active = policy["concurrency"]["max_active_implementation_issues"]
    if current is None:
        stop = "all milestone gates passed"
    elif len(active) >= max_active:
        stop = f"active implementation slot occupied by {', '.join(f'#{n}' for n in active)}; resume it before claiming new work"
    elif not eligible:
        stop = f"no eligible task in {current}; blockers recorded"
    elif snap.project is None:
        stop = "project board unreadable (missing project scope): selection is provisional and no claim can proceed"
    else:
        nxt = eligible[0]
    provisional = eligible[0] if eligible and nxt is None and snap.project is None else None
    return Plan(keys, gates, current, candidates, nxt, active, unscheduled, deferred, graph, stop, provisional)


def _assess(issue: Issue, snap: Snapshot, policy: dict, graph: Graph,
            missing_preds: list[str], epic_order: list[int]) -> Candidate:
    c = Candidate(issue.number, issue.title, issue.milestone_key, True)
    decision = {d["issue"]: d for d in policy.get("decision_tasks", [])}
    actions = {a["issue"]: a for a in policy.get("maintainer_actions", [])}
    agent_labels = set(issue.labels)
    if issue.state != "open":
        c.eligible = False
        c.reasons.append(f"issue is {issue.state} ({issue.state_reason})")
    if missing_preds:
        c.eligible = False
        c.reasons.append(f"predecessor milestones without passed exit gates: {missing_preds}")
    criteria = acceptance_criteria(issue.body)
    if not criteria:
        c.eligible = False
        c.reasons.append("no actionable acceptance criteria")
    if snap.project is None:
        c.notes.append("board status unknown (project not readable); eligibility is provisional")
    else:
        status = snap.status_of(issue.number)
        if status is None:
            c.eligible = False
            c.reasons.append("issue is not on the project board")
        elif status != "Todo":
            c.eligible = False
            c.reasons.append(f"board status is {status!r}, not Todo")
    for label in ("agent:blocked", "agent:needs-human"):
        if label in agent_labels:
            c.eligible = False
            c.reasons.append(f"labelled {label}")
    if graph.in_cycle(issue.number):
        c.eligible = False
        c.reasons.append("participates in a dependency cycle")
    for edge in graph.blockers_of(issue.number):
        blocker = snap.issues.get(edge.blocker)
        src = "; ".join(edge.provenance)
        if blocker is None:
            c.eligible = False
            c.reasons.append(f"blocked by unknown #{edge.blocker} ({src})")
        elif blocker.state == "closed" and blocker.state_reason == "not_planned":
            c.eligible = False
            c.reasons.append(f"prerequisite #{edge.blocker} closed as not planned ({src})")
        elif not blocker.completed or (snap.project and snap.status_of(edge.blocker) != "Done"):
            c.eligible = False
            c.reasons.append(f"blocked by #{edge.blocker} ({src})")
        if blocker is not None and blocker.number in decision and not blocker.completed:
            c.reasons.append(f"depends on unresolved decision #{blocker.number}")
        if blocker is not None and blocker.milestone_key and issue.milestone_key and \
                milestone_order(blocker.milestone_key) > milestone_order(issue.milestone_key):
            c.eligible = False
            c.reasons.append(f"contradictory dependency on later milestone #{blocker.number}")
    if issue.number in decision:
        c.work_type = "decision-preparation"
        c.notes.append("agents prepare a proposal; Done requires the maintainer's recorded decision: "
                       + decision[issue.number]["decision"])
    if issue.number in actions:
        c.notes.append("completion requires maintainer action: " + actions[issue.number]["action"])
    pos = epic_order.index(issue.number) if issue.number in epic_order else len(epic_order)
    c.sequence = (0, pos, issue.number)
    return c
