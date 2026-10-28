"""Command line interface. Every command that could write to GitHub is a dry run
unless ``--apply`` is given; read-only commands never write remotely."""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path

from . import docs_audit, events, review, schema
from .github import FakeGitHub, GhCli, GitHubError
from .model import (acceptance_criteria, digest, requirements_digest, snapshot_from_dict,
                    snapshot_to_dict)
from .publisher import DeliveryPaused, Publisher, authenticated_events, maintainer_decisions
from .scheduler import plan as make_plan
from .state import LockHeld, PacketError, Store, new_id, utcnow
from .transitions import TaskView, Transitioner, evaluate

POLICY_PATH = Path(__file__).resolve().parent / "policy.json"


def repo_root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def adapter_for(args, policy: dict):
    if getattr(args, "fixture", None):
        return FakeGitHub(snapshot_from_dict(json.loads(Path(args.fixture).read_text(encoding="utf-8"))))
    p = policy["project"]
    return GhCli(policy["repository"], p["owner"], p["number"])


def emit(args, data, text: str | None = None) -> None:
    if getattr(args, "json", False) or text is None:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(text)


def gate_events(store: Store, snap, policy: dict) -> list[dict]:
    out = []
    for spec in policy["milestones"].values():
        trusted, _ = authenticated_events(store, snap, policy["actors"]["coordinator_logins"], spec["epic"])
        out += [e for e in trusted if e["kind"] == "GATE_EVALUATED"]
    return out


def claim_expiry(policy: dict) -> str:
    from datetime import datetime, timedelta, timezone
    hours = policy["concurrency"].get("claim_ttl_hours", 8)
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def active_claims(store: Store) -> list[int]:
    claimed: dict[int, bool] = {}
    for e in store.events():
        n = int(e["issue"].split("#")[1])
        if e["kind"] == "CLAIMED":
            claimed[n] = True
        elif e["kind"] in ("RELEASED", "COMPLETED"):
            claimed[n] = False
        elif e["kind"] == "STATE_CHANGED" and e["to_status"] in ("In Review", "Done", "Todo"):
            claimed[n] = False
    return sorted(n for n, v in claimed.items() if v)


# ------------------------------------------------------------------ commands


def cmd_capabilities(args) -> int:
    from .capabilities import inspect
    data = inspect(repo_root())
    emit(args, data, json.dumps(data, indent=2))
    return 0


def cmd_discover(args) -> int:
    policy = load_policy()
    adapter = adapter_for(args, policy)
    snap = adapter.snapshot()
    if args.save:
        Path(args.save).write_text(json.dumps(snapshot_to_dict(snap), indent=2), encoding="utf-8")
    proj = snap.project
    data = {
        "issues": len(snap.issues), "open_issues": sum(i.state == "open" for i in snap.issues.values()),
        "milestones": {m.title: m.number for m in snap.milestones},
        "pulls": len(snap.pulls),
        "project": None if proj is None else {
            "id": proj.project_id, "title": proj.title, "status_field_id": proj.status_field_id,
            "status_options": proj.options, "items": len(proj.items),
            "missing_options": [o for o in policy["project"]["status_options"] if o not in proj.options],
            "unexpected_options": [o for o in proj.options if o not in policy["project"]["status_options"]],
        },
        "project_error": snap.project_error, "branch_protection": snap.branch_protection is not None,
        "notes": snap.notes,
    }
    emit(args, data)
    return 0


def cmd_plan(args) -> int:
    policy = load_policy()
    store = Store.for_repo(repo_root())
    snap = adapter_for(args, policy).snapshot()
    p = make_plan(snap, policy, gate_events(store, snap, policy), active_claims(store))
    data = {
        "current_milestone": p.current, "next": p.next.__dict__ if p.next else None,
        "stop_reason": p.stop_reason, "active": p.active,
        "provisional_next": p.provisional_next.__dict__ if p.provisional_next else None,
        "gates": {k: {"passed": g.passed, "reasons": g.reasons} for k, g in p.gates.items()},
        "candidates": [c.__dict__ for c in p.candidates],
        "unscheduled": p.unscheduled, "deferred": p.deferred,
        "graph": {"blocking_edges": [{"blocked": e.blocked, "blocker": e.blocker, "provenance": e.provenance}
                                     for e in p.graph.edges.values()],
                  "membership": p.graph.membership,
                  "contextual_mentions": {k: sorted(v) for k, v in p.graph.contextual.items()},
                  "findings": p.graph.findings},
    }
    emit(args, data)
    return 0


def _view(store: Store, snap, policy: dict, number: int, *, head=None, clean=False, integration=None,
          packet_valid=False, exclusive=False, worktree=None) -> TaskView:
    trusted, _ = authenticated_events(store, snap, policy["actors"]["coordinator_logins"], number)
    decisions = maintainer_decisions(store, snap, policy["actors"]["maintainer_logins"], number)
    return TaskView(issue=snap.issues[number], status=snap.status_of(number), events=trusted,
                    decisions=decisions, candidate_head=head, clean_tree=clean, integration=integration,
                    packet_valid=packet_valid, exclusive_claim=exclusive, worktree=worktree, policy=policy)


def _git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _branch_for(number: int, title: str) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].rstrip("-")
    return f"agent/{number}-{slug}"


def build_task_packet(snap, policy: dict, number: int, run_id: str, attempt: int, base_sha: str,
                      worktree: str, branch: str, allowed_paths: list[str], non_goals: list[str],
                      docs_impact: list[dict], dependency_evidence: list[str]) -> dict:
    issue = snap.issues[number]
    crit = acceptance_criteria(issue.body)
    packet = {
        "schema_version": 1, "issue_url": issue.url or f"https://github.com/{policy['repository']}/issues/{number}",
        "issue": f"{policy['repository']}#{number}", "milestone": issue.milestone_key,
        "run_id": run_id, "attempt": attempt, "role": "implementer",
        "dependency_evidence": dependency_evidence,
        "criteria": [{"id": c["id"], "text": c["text"], "text_digest": c["text_digest"],
                      "verification": "to be planned by the orchestrator before delegation"} for c in crit],
        "docs_impact": docs_impact, "allowed_paths": allowed_paths, "non_goals": non_goals,
        "base_sha": base_sha, "worktree": worktree, "branch": branch,
        "checks": derive_checks(repo_root(), allowed_paths),
        "reporting_contract": "Return one JSON message per schemas/event.v1.schema.json (IMPLEMENTATION_READY, QUESTION or BLOCKED) to the orchestrator; never write to GitHub.",
        "escalation_conditions": [
            "acceptance criteria conflict with the specification or each other",
            "a check, guarantee, evidence label or provenance record would have to be weakened",
            "work is needed outside allowed_paths",
            "a maintainer decision (rights, semantics, architecture) is required",
        ],
        "requirements_digest": requirements_digest(issue),
    }
    errors = schema.validate(packet, schema.load("task-packet.v1.schema.json"))
    if errors:
        raise SystemExit(f"invalid task packet: {errors}")
    return packet


def derive_checks(repo: Path, paths: list[str]) -> list[dict]:
    """Checks derived from current CI for the affected components (run each in its directory)."""
    checks = []
    touched = lambda prefix: any(p.startswith(prefix) or p in ("**", "*") for p in paths)  # noqa: E731
    if touched("inventory-proof"):
        checks += [{"name": "inventory-proof tests", "cwd": "inventory-proof", "argv": ["python3", "-m", "unittest", "discover", "-s", "tests"]},
                   {"name": "inventory-proof demo regenerates outputs", "cwd": "inventory-proof", "argv": ["python3", "demo.py"], "then": "git diff --exit-code -- ."},
                   {"name": "inventory-proof crash model", "cwd": "inventory-proof", "argv": ["python3", "durable.py"]}]
    if touched("agent-kit"):
        checks += [{"name": "agent-kit doctor", "cwd": "agent-kit", "argv": ["python3", "scripts/weave.py", "doctor"]},
                   {"name": "agent-kit tests", "cwd": "agent-kit", "argv": ["python3", "-B", "-m", "unittest", "discover", "-s", "tests"]},
                   {"name": "agent-kit examples", "cwd": "agent-kit", "argv": ["python3", "scripts/weave.py", "examples"]},
                   {"name": "agent-kit bundled regressions", "cwd": "agent-kit", "argv": ["python3", "scripts/weave.py", "test"]}]
        for demo in sorted(p for p in (repo / "agent-kit/demos").glob("*/") if (p / "tests").is_dir()):
            checks.append({"name": f"agent-kit demo {demo.name} tests", "cwd": f"agent-kit/demos/{demo.name}",
                           "argv": ["python3", "-B", "-m", "unittest", "discover", "-s", "tests"]})
    if touched("specification"):
        checks += [{"name": "specification offline validation", "cwd": "specification", "argv": ["make", "validate-offline"]},
                   {"name": "specification single-page and text", "cwd": "specification", "argv": ["make", "singlehtml", "text"]},
                   {"name": "specification single-page HTML audit", "cwd": "specification",
                    "argv": ["python3", "scripts/audit_html.py", "_build/singlehtml"]}]
    if touched("tools") or touched(".claude") or touched(".github") or touched("docs/development"):
        checks += [{"name": "workflow tests", "cwd": ".", "argv": ["python3", "-m", "unittest", "discover", "-s", "tools/weave_workflow/tests", "-t", "."]},
                   {"name": "documentation map current", "cwd": ".", "argv": ["python3", "-m", "tools.weave_workflow", "docs-map"]}]
    if (repo / "Cargo.toml").exists():
        checks += [{"name": "cargo fmt", "cwd": ".", "argv": ["cargo", "fmt", "--all", "--check"]},
                   {"name": "cargo clippy", "cwd": ".", "argv": ["cargo", "clippy", "--all-targets", "--", "-D", "warnings"]},
                   {"name": "cargo test", "cwd": ".", "argv": ["cargo", "test", "--all"]}]
    checks.append({"name": "documentation audit", "cwd": ".", "argv": ["python3", "-m", "tools.weave_workflow", "docs-audit"]})
    return checks


def select_for_claim(args, store: Store, snap, policy: dict):
    """Returns (plan, candidate, refusal); refusal is None when the issue may be claimed now."""
    p = make_plan(snap, policy, gate_events(store, snap, policy), active_claims(store))
    cand = next((c for c in p.candidates if c.issue == args.issue), None)
    if cand is None or not cand.eligible:
        return p, cand, {"claimable": False, "issue": args.issue, "stop_reason": p.stop_reason,
                         "reasons": cand.reasons if cand else [f"#{args.issue} is not a candidate in {p.current}"]}
    if p.next is None:
        return p, cand, {"claimable": False, "issue": args.issue, "reasons": [p.stop_reason or "no task selected"]}
    if p.next.issue != args.issue and not args.override_order:
        return p, cand, {"claimable": False, "reasons": [f"#{p.next.issue} precedes #{args.issue} in the deterministic order"]}
    return p, cand, None


def cmd_claim(args) -> int:
    """Prepare (dry run) or perform a claim: CLAIMED, DOCS_IMPACT, PLAN, worktree, Todo -> In Progress."""
    policy = load_policy()
    repo = repo_root()
    store = Store.for_repo(repo)
    adapter = adapter_for(args, policy)
    snap = adapter.snapshot()
    p, cand, refusal = select_for_claim(args, store, snap, policy)
    if refusal:
        emit(args, refusal)
        return 2
    issue = snap.issues[args.issue]
    run = store.active_run() or {}
    run_id = run.get("run_id") or new_id("run")
    attempt = 1 + sum(1 for e in store.events(f"{policy['repository']}#{args.issue}") if e["kind"] == "CLAIMED")
    try:
        base_sha = _git(repo, "rev-parse", "--verify", f"{args.base}^{{commit}}")
    except subprocess.CalledProcessError:
        emit(args, {"claimable": False, "issue": args.issue,
                     "reasons": [f"base revision {args.base!r} not found; fetch it first"]})
        return 2
    branch = _branch_for(args.issue, issue.title)
    worktree = str(repo / ".worktrees" / branch.replace("/", "-"))
    allowed = args.allowed_path or ["**"]
    impact = [{"path": d, "reason": f"required by {', '.join(sorted(set(r)))}", "status": "required"}
              for d, r in sorted(docs_audit.required_documents(docs_audit.docmap_for(repo), {a: "M" for a in allowed if "*" not in a}).items())]
    if not args.allowed_path:
        impact.append({"path": "(computed from the final diff)", "reason": "allowed paths unrestricted; impact recomputed at the In Review gate", "status": "required"})
    deps = [f"#{e.blocker} completed ({'; '.join(e.provenance)})" for e in p.graph.blockers_of(args.issue)]
    deps.append(f"milestone {p.current}: predecessors {policy['milestones'][p.current]['requires'] or ['Start']} passed")
    packet = build_task_packet(snap, policy, args.issue, run_id, attempt, base_sha, worktree, branch,
                               allowed, args.non_goal or [], impact, deps)
    ctx = {"run_id": run_id, "attempt": attempt, "issue": packet["issue"], "milestone": packet["milestone"]}
    ops = [f"acquire coordinator lock for {run_id}", "publish CLAIMED", "publish DOCS_IMPACT", "publish PLAN",
           f"git worktree add {worktree} -b {branch} {base_sha}", "transition Todo -> In Progress (gated)"]
    if not args.apply:
        emit(args, {"dry_run": True, "work_type": cand.work_type, "notes": cand.notes, "packet": packet, "operations": ops})
        return 0
    publisher = Publisher(store, adapter, policy["repository"], policy["actors"]["coordinator_logins"])
    try:
        with store.coordinator_lock(run_id):
            # Another coordinator may have claimed between selection and the lock: select again.
            _, _, refusal = select_for_claim(args, store, adapter.snapshot(), policy)
            if refusal:
                refusal["note"] = "selection changed while waiting for the coordinator lock"
                emit(args, refusal)
                return 2
            store.set_active_run({**run, "run_id": run_id, "active_issue": args.issue, "since": run.get("since", utcnow())})
            claimed = publisher.publish(events.build("CLAIMED", sender="orchestrator", recipient="orchestrator",
                                                     claim_expires_at=claim_expiry(policy), coordinator_host=socket.gethostname(),
                                                     work_type=cand.work_type, summary=f"Claimed for run {run_id}.", **ctx), origin="claim")
            impact_ev = publisher.publish(events.build("DOCS_IMPACT", sender="orchestrator", recipient="implementer",
                                                       docs_impact=packet["docs_impact"], causation_id=claimed["event_id"],
                                                       correlation_id=claimed["event_id"], **ctx), origin="claim")
            plan_ev = publisher.publish(events.build(
                "PLAN", sender="orchestrator", recipient="implementer", requirements_digest=packet["requirements_digest"],
                criteria=[{"id": c["id"], "text_digest": c["text_digest"], "verification": c["verification"]} for c in packet["criteria"]],
                causation_id=impact_ev["event_id"], correlation_id=claimed["event_id"], **ctx),
                body="\n".join(f"- **{c['id']}** {c['text']}" for c in packet["criteria"]), origin="claim")
            _git(repo, "worktree", "add", worktree, "-b", branch, base_sha)
            packet_path = store.run_dir(run_id) / f"packet-{args.issue}-a{attempt}.json"
            packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
            store.append({"type": "packet", "issue": args.issue, "run_id": run_id, "attempt": attempt,
                          "path": str(packet_path), "digest": digest(packet_path.read_text(encoding="utf-8"))})
            snap = adapter.snapshot()
            view = _view(store, snap, policy, args.issue, packet_valid=True, exclusive=True, worktree=worktree)
            proj = snap.project
            result = Transitioner(store, adapter, publisher, proj, policy, dry_run=False).execute(view, "In Progress", ctx)
            store.checkpoint({"run_id": run_id, "active_issue": args.issue, "attempt": attempt,
                              "status": "In Progress" if result.get("applied") else "claimed",
                              "packet": str(packet_path), "next_action": "delegate implementation with the packet"})
    except LockHeld as exc:
        emit(args, {"applied": False, "reason": str(exc)})
        return 3
    except DeliveryPaused as exc:
        emit(args, {"applied": False, "paused": str(exc), "note": "messages remain queued; run `reconcile --apply`"})
        return 4
    emit(args, {"applied": True, "packet": str(packet_path), "plan_event": plan_ev["event_id"], "transition": result})
    return 0


def cmd_event(args) -> int:
    """Validate a worker's message from the local outbox, or publish it with attribution."""
    policy = load_policy()
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    errors = events.validate(data)
    if errors:
        emit(args, {"valid": False, "errors": errors})
        return 1
    problems = relay_problems(data)
    if problems:
        emit(args, {"valid": False, "errors": problems})
        return 1
    if args.action == "validate" or not args.apply:
        text, clean = events.render(data, args.body or "")
        emit(args, {"valid": True, "dry_run": True, "comment": text})
        return 0
    store = Store.for_repo(repo_root())
    publisher = Publisher(store, adapter_for(args, policy), policy["repository"], policy["actors"]["coordinator_logins"])
    try:
        published = publisher.publish(data, args.body or "", origin="relay")
    except DeliveryPaused as exc:
        emit(args, {"published": False, "paused": str(exc)})
        return 4
    emit(args, {"published": True, "event_id": published["event_id"]})
    return 0


RELAY_SENDERS = {
    "QUESTION": {"implementer", "verifier", "docs-editor", "local-reviewer", "safety-reviewer", "investigator", "orchestrator"},
    "ANSWER": {"orchestrator", "investigator"},
    "PROGRESS": {"orchestrator", "implementer", "verifier", "docs-editor", "investigator"},
    "DELEGATED": {"orchestrator"},
    "IMPLEMENTATION_READY": {"implementer"},
    "LOCAL_REVIEW_RESULT": {"local-reviewer", "safety-reviewer"},
    "FINDING_DISPOSITION": {"orchestrator"},
    "CHANGES_REQUESTED": {"orchestrator"},
    "BLOCKED": {"orchestrator", "implementer", "verifier", "docs-editor", "local-reviewer", "safety-reviewer", "investigator"},
    "RESUMED": {"orchestrator"},
    "RELEASED": {"orchestrator"},
}


def relay_problems(data: dict) -> list[str]:
    """Why a message may not go through the generic relay (empty list: it may)."""
    from .publisher import RESERVED_ORIGINS
    kind, sender = data["kind"], data["sender"]
    if kind in RESERVED_ORIGINS:
        owners = sorted(RESERVED_ORIGINS[kind]) or ["a maintainer comment"]
        return [f"{kind} is produced only by {', '.join(owners)}; it cannot be relayed"]
    if sender not in RELAY_SENDERS.get(kind, set()):
        return [f"{sender} may not send {kind}"]
    if sender != "orchestrator" and data["recipient"] != "orchestrator":
        return ["worker messages must be addressed to the orchestrator"]
    if kind == "LOCAL_REVIEW_RESULT" and {"local-reviewer": "local", "safety-reviewer": "safety"}[sender] != data["review_kind"]:
        return ["review_kind does not match the reviewer role"]
    return []


def cmd_new_event(args) -> int:
    """Build a validated event skeleton (for workers' outbox messages and orchestrator records)."""
    fields = json.loads(args.fields) if args.fields else {}
    try:
        ev = events.build(args.kind, run_id=args.run_id, attempt=args.attempt, issue=args.issue,
                          milestone=args.milestone, sender=args.sender, recipient=args.recipient,
                          correlation_id=args.correlation_id, causation_id=args.causation_id,
                          summary=args.summary or "", **fields)
    except events.EventError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    out = json.dumps(ev, indent=2)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


def _task_context(store: Store, snap, policy: dict, number: int) -> dict:
    trusted, _ = authenticated_events(store, snap, policy["actors"]["coordinator_logins"], number)
    plan_ev = next((e for e in reversed(trusted) if e["kind"] == "PLAN"), None)
    if plan_ev is None:
        raise SystemExit(f"#{number} has no published PLAN; claim it first")
    return {"run_id": plan_ev["run_id"], "attempt": plan_ev["attempt"], "issue": plan_ev["issue"],
            "milestone": plan_ev["milestone"]}


def recorded_packet(store: Store, snap, policy: dict, number: int) -> dict:
    """The packet recorded when the issue was claimed, verified against its ledger digest."""
    ctx = _task_context(store, snap, policy, number)
    try:
        return store.packet(number, ctx["run_id"], ctx["attempt"])
    except PacketError as exc:
        raise SystemExit(str(exc)) from exc


def _publish_task_event(args, number: int, kind: str, origin: str, body: str = "", **fields) -> dict | None:
    policy = load_policy()
    store = Store.for_repo(repo_root())
    adapter = adapter_for(args, policy)
    snap = adapter.snapshot()
    ev = events.build(kind, sender="orchestrator", recipient="orchestrator",
                      **_task_context(store, snap, policy, number), **fields)
    if not args.apply:
        return {"dry_run": True, "event": ev}
    publisher = Publisher(store, adapter, policy["repository"], policy["actors"]["coordinator_logins"])
    return {"event_id": publisher.publish(ev, body, origin=origin)["event_id"]}


def cmd_verify(args) -> int:
    """Run the claim's checks plus those derived from the actual diff in the claimed worktree."""
    policy = load_policy()
    repo = repo_root()
    store = Store.for_repo(repo)
    snap = adapter_for(args, policy).snapshot()
    packet = recorded_packet(store, snap, policy, args.issue)
    worktree = Path(packet["worktree"])
    if _git(worktree, "status", "--porcelain"):
        emit(args, {"ok": False, "reason": "candidate worktree is not clean; commit first"})
        return 2
    head = _git(worktree, "rev-parse", "HEAD")
    if subprocess.run(["git", "merge-base", "--is-ancestor", packet["base_sha"], head], cwd=worktree).returncode != 0:
        emit(args, {"ok": False, "reason": "candidate does not descend from the claimed base"})
        return 2
    changed = _git(worktree, "diff", "--name-only", packet["base_sha"], head).splitlines()
    required = {c["name"]: c for c in packet["checks"]}
    for c in derive_checks(worktree, changed):
        required.setdefault(c["name"], c)
    log_dir = store.run_dir(packet["run_id"]) / f"verify-{args.issue}-{head[:12]}"
    log_dir.mkdir(parents=True, exist_ok=True)
    checks = []
    for i, check in enumerate(required.values(), 1):
        cwd = worktree / check["cwd"]
        proc = subprocess.run(check["argv"], cwd=cwd, capture_output=True, text=True)
        rc = proc.returncode
        if rc == 0 and check.get("then") == "git diff --exit-code -- .":
            rc = subprocess.run(["git", "diff", "--exit-code", "--", "."], cwd=cwd, capture_output=True).returncode
        log = log_dir / f"{i:02d}.log"
        log.write_text(proc.stdout + proc.stderr, encoding="utf-8")
        checks.append({"name": check["name"], "command": check["argv"], "cwd": check["cwd"], "exit_code": rc, "log": str(log)})
    result = "PASS" if checks and all(c["exit_code"] == 0 for c in checks) else "FAIL"
    body = "\n".join(f"- `{' '.join(c['command'])}` in `{c['cwd']}` → exit {c['exit_code']}" for c in checks)
    out = {"head_sha": head, "result": result, "checks": checks}
    out["published"] = _publish_task_event(args, args.issue, "VERIFICATION_RESULT", "verify", body=body,
                                           head_sha=head, result=result, checks=checks)
    emit(args, out)
    return 0 if result == "PASS" else 1


def cmd_milestone_gate(args) -> int:
    """Mechanical exit-gate checks; GATE_EVALUATED PASS is published only when they all hold."""
    from .scheduler import milestone_gate, milestone_members
    policy = load_policy()
    repo = repo_root()
    store = Store.for_repo(repo)
    adapter = adapter_for(args, policy)
    snap = adapter.snapshot()
    key = args.milestone
    spec = policy["milestones"][key]
    reasons = [r for r in milestone_gate(snap, policy, key, [{"gate": f"milestone-exit:{key}", "result": "PASS"}]).reasons
               if "epic" not in r]
    for pred in spec["requires"]:
        if not milestone_gate(snap, policy, pred, gate_events(store, snap, policy)).passed:
            reasons.append(f"predecessor {pred} has not passed its exit gate")
    audit = docs_audit.audit(repo)
    if audit.result != "PASS":
        reasons.append(f"whole-repository documentation audit fails ({audit.error_count} errors)")
    if not args.evidence:
        reasons.append("no exit-criteria evidence supplied (--evidence)")
    result = "PASS" if not reasons else "FAIL"
    out = {"milestone": key, "result": result, "reasons": reasons,
           "members": [i.number for i in milestone_members(snap, policy, key)]}
    if args.apply:
        evidence = Path(args.evidence).read_text(encoding="utf-8") if args.evidence else ""
        ev = events.build("GATE_EVALUATED", sender="orchestrator", recipient="orchestrator", gate=f"milestone-exit:{key}",
                          result=result, run_id=(store.active_run() or {}).get("run_id") or new_id("run"), attempt=1,
                          issue=f"{policy['repository']}#{spec['epic']}", milestone=key)
        body = evidence + ("\n\nUnmet: " + "; ".join(reasons) if reasons else "")
        publisher = Publisher(store, adapter, policy["repository"], policy["actors"]["coordinator_logins"])
        out["event_id"] = publisher.publish(ev, body, origin="milestone-gate")["event_id"]
    emit(args, out)
    return 0 if result == "PASS" else 2


def cmd_transition(args) -> int:
    policy = load_policy()
    repo = repo_root()
    store = Store.for_repo(repo)
    adapter = adapter_for(args, policy)
    snap = adapter.snapshot()
    worktree = Path(args.worktree) if args.worktree else None
    head = args.head or (_git(worktree, "rev-parse", "HEAD") if worktree else None)
    integration = None
    if args.to == "Done" and head:
        from .integration import integration_evidence
        packet = recorded_packet(store, snap, policy, args.issue)
        integration = integration_evidence(repo, snap, policy, args.issue, head, packet["branch"])
    clean = bool(worktree) and _git(worktree, "status", "--porcelain") == ""
    view = _view(store, snap, policy, args.issue, head=head, clean=clean, integration=integration,
                 worktree=str(worktree) if worktree else None)
    run = store.active_run() or {}
    ctx = {"run_id": run.get("run_id") or "run-unset", "attempt": view.attempt,
           "issue": f"{policy['repository']}#{args.issue}", "milestone": view.issue.milestone_key}
    if not args.apply:
        g = evaluate(view, args.to)
        emit(args, {"dry_run": True, "gate": g.__dict__, "integration": integration})
        return 0 if g.passed else 2
    publisher = Publisher(store, adapter, policy["repository"], policy["actors"]["coordinator_logins"])
    try:
        with store.coordinator_lock(ctx["run_id"]):
            result = Transitioner(store, adapter, publisher, snap.project, policy, dry_run=False).execute(view, args.to, ctx)
    except (LockHeld, DeliveryPaused) as exc:
        emit(args, {"applied": False, "reason": str(exc)})
        return 3
    emit(args, result)
    return 0 if result.get("applied") else 2


def cmd_reconcile(args) -> int:
    from .reconcile import reconcile
    policy = load_policy()
    repo = repo_root()
    store = Store.for_repo(repo)
    adapter = adapter_for(args, policy)
    report = reconcile(repo, store, adapter, policy, apply=args.apply)
    emit(args, report)
    return 0 if not report["conflicts"] else 2


def cmd_outbox(args) -> int:
    store = Store.for_repo(repo_root())
    emit(args, {"pending": [{"event_id": i["event_id"], "issue": i["issue_number"], "kind": i["event"]["kind"],
                             "sequence": i["sequence"]} for i in store.pending()]})
    return 0


def bound_impact(recorded: list[dict], supplied: list[dict] | None) -> list[dict]:
    """The claim's impact list, optionally extended or justified, never shortened."""
    if supplied is None:
        return recorded
    by_path = {i["path"]: i for i in supplied}
    dropped = [i["path"] for i in recorded if i["path"] not in by_path]
    if dropped:
        raise SystemExit(f"the impact list may not be shortened; missing: {dropped}")
    for item in supplied:
        if item.get("status") == "not-applicable" and not item.get("justification"):
            raise SystemExit(f"{item['path']}: not-applicable needs a justification")
    return supplied


def cmd_docs_audit(args) -> int:
    impact = json.loads(Path(args.impact).read_text())["docs_impact"] if args.impact else None
    repo = Path(args.repo).resolve() if args.repo else repo_root()
    base = args.base
    if args.publish:
        policy = load_policy()
        store = Store.for_repo(repo_root())
        snap = adapter_for(args, policy).snapshot()
        packet = recorded_packet(store, snap, policy, args.publish)
        trusted, _ = authenticated_events(store, snap, policy["actors"]["coordinator_logins"], args.publish)
        recorded = next((e for e in reversed(trusted) if e["kind"] == "DOCS_IMPACT"), None)
        if recorded is None:
            print("no published DOCS_IMPACT for this claim", file=sys.stderr)
            return 2
        if (args.repo and Path(args.repo).resolve() != Path(packet["worktree"]).resolve()) or \
                (args.base and _git(repo_root(), "rev-parse", args.base) != packet["base_sha"]):
            print("--repo and --base must match the claim (worktree and base); omit them when publishing", file=sys.stderr)
            return 2
        repo, base = Path(packet["worktree"]), packet["base_sha"]
        impact = bound_impact(recorded["docs_impact"], impact)
    result = docs_audit.audit(repo, base=base, impact=impact)
    data = result.to_dict()
    if args.publish:
        if _git(repo, "status", "--porcelain"):
            print("the audited worktree is not clean; commit the candidate first", file=sys.stderr)
            return 2
        data["published"] = _publish_task_event(args, args.publish, "DOCS_AUDIT_RESULT", "docs-audit",
                                                head_sha=result.head_sha, result=result.result,
                                                error_count=result.error_count, scope="change",
                                                body="\n".join(f"- {f.severity}: [{f.check}] `{f.path}`: {f.message}"
                                                                for f in result.findings) or "No findings.")
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"docs-audit {result.result} ({result.scope} scope, head {result.head_sha[:12] if result.head_sha else '-'}): "
              + ", ".join(f"{k}={v}" for k, v in result.counts.items()))
        for f in result.findings:
            print(f"  {f.severity.upper():7} [{f.check}] {f.path}: {f.message}")
    return 0 if result.result == "PASS" else 1


def cmd_docs_map(args) -> int:
    repo = repo_root()
    docmap = docs_audit.docmap_for(repo)
    path = repo / "docs/development/documentation-map.md"
    text = path.read_text(encoding="utf-8")
    start, end = text.find(docs_audit.GEN_BEGIN), text.find(docs_audit.GEN_END)
    if start < 0 or end < 0:
        print("documentation-map.md has no generated section markers", file=sys.stderr)
        return 1
    new = text[:start] + docs_audit.render_docs_map(docmap) + text[end + len(docs_audit.GEN_END):]
    if args.write:
        path.write_text(new, encoding="utf-8")
        print("documentation-map.md regenerated")
        return 0
    print("current" if new == text else "stale: run docs-map --write")
    return 0 if new == text else 1


def cmd_review(args) -> int:
    """Build the review packet for the candidate; with --apply, run the independent Codex review."""
    from .integration import find_pr
    from .reconcile import review_round
    policy = load_policy()
    repo = repo_root()
    store = Store.for_repo(repo)
    adapter = adapter_for(args, policy)
    snap = adapter.snapshot()
    worktree = Path(args.worktree)
    head = _git(worktree, "rev-parse", "HEAD")
    if _git(worktree, "status", "--porcelain"):
        emit(args, {"ok": False, "reason": "candidate worktree is not clean; commit first"})
        return 2
    view = _view(store, snap, policy, args.issue, head=head, clean=True)
    plan_ev = view.latest("PLAN")
    if not plan_ev:
        emit(args, {"ok": False, "reason": "no PLAN event"})
        return 2
    base = _git(worktree, "merge-base", head, args.base)
    issue = snap.issues[args.issue]
    crit = acceptance_criteria(issue.body)
    impact_ev = view.latest("DOCS_IMPACT")
    audit_ev = view.latest("DOCS_AUDIT_RESULT", head_sha=head, scope="change")
    verification = view.latest("VERIFICATION_RESULT", head_sha=head)
    rnd = review_round(view)
    if rnd > policy["review"]["max_rounds_per_attempt"]:
        emit(args, {"ok": False, "reason": "review budget exhausted; mark agent:needs-human and summarise the disagreement"})
        return 2
    p = make_plan(snap, policy, gate_events(store, snap, policy), active_claims(store))
    deps = [f"#{e.blocker}: {snap.issues[e.blocker].state} ({snap.issues[e.blocker].state_reason}), board "
            f"{snap.status_of(e.blocker)!r}; edge from {'; '.join(e.provenance)}" for e in p.graph.blockers_of(args.issue)
            if e.blocker in snap.issues]
    key = issue.milestone_key
    if key in policy["milestones"]:
        for pred in policy["milestones"][key]["requires"]:
            g = p.gates[pred]
            deps.append(f"predecessor {pred}: exit gate {'passed' if g.passed else 'NOT passed: ' + '; '.join(g.reasons[:3])}")
    live = []
    for path in args.evidence or []:
        live.append({"file": path, "content": Path(path).read_text(encoding="utf-8")[:20000]})
    request_id = new_id("ev")
    packet = review.build_packet(
        run_id=plan_ev["run_id"], attempt=plan_ev["attempt"], request_id=request_id, issue_url=issue.url,
        milestone=key, criteria=crit, requirements_digest=requirements_digest(issue),
        base_sha=base, head_sha=head, dependency_evidence=deps, decisions=[d["text"] for d in view.decisions],
        checks=(verification or {}).get("checks", []), ci_links=args.ci_link or [], limitations=args.limitation or [],
        docs_impact=(impact_ev or {}).get("docs_impact", []),
        docs_changed=(view.latest("IMPLEMENTATION_READY", head_sha=head) or {}).get("docs_updated", []),
        docs_audit=audit_ev or {"result": "MISSING"},
        local_findings=view.all("LOCAL_REVIEW_RESULT", head_sha=head) + view.all("FINDING_DISPOSITION"),
        review_round=rnd, previous_findings=view.all("CHANGES_REQUESTED"),
        mode="delta" if args.delta else "full")
    if live:
        packet["additional_evidence"] = live
    pr = find_pr(snap, args.issue, head, recorded_packet(store, snap, policy, args.issue)["branch"])
    if not args.apply:
        emit(args, {"dry_run": True, "packet": packet, "mirror_to_pr": pr.number if pr else None})
        return 0
    ctx = {"run_id": plan_ev["run_id"], "attempt": plan_ev["attempt"], "issue": f"{policy['repository']}#{args.issue}",
           "milestone": key}
    publisher = Publisher(store, adapter, policy["repository"], policy["actors"]["coordinator_logins"])
    req = events.build("REVIEW_REQUESTED", sender="orchestrator", recipient="codex-reviewer", head_sha=head, base_sha=base,
                       requirements_digest=packet["requirements_digest"], review_round=rnd, **ctx)
    req["event_id"] = req["correlation_id"] = request_id
    publisher.publish(req, origin="review")
    out_dir = store.run_dir(plan_ev["run_id"]) / "reviews"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"packet-{request_id}.json").write_text(json.dumps(packet, indent=2), encoding="utf-8")
    try:
        run = review.run_codex(packet, worktree, out_dir, policy)
        accepted = review.accept(run.result, request=req, current_head=_git(worktree, "rev-parse", "HEAD"),
                                 current_base=_git(worktree, "merge-base", "HEAD", args.base),
                                 requirements_now=requirements_digest(adapter.snapshot().issues[args.issue]),
                                 criteria_ids=[c["id"] for c in crit],
                                 doc_criteria_ids=[c["id"] for c in review.documentation_criteria(packet["documentation_impact"])])
    except review.ReviewRejected as exc:
        publisher.publish(events.build("BLOCKED", sender="orchestrator", recipient="orchestrator", blocker="review-outage",
                                       reason=f"independent review not accepted: {exc}", causation_id=request_id,
                                       correlation_id=request_id, **ctx))
        emit(args, {"ok": False, "reason": str(exc)})
        return 2
    body = review.render_result(run.result, run.provenance)
    result_ev = publisher.publish(events.build(
        "REVIEW_RESULT", sender="codex-reviewer", recipient="orchestrator", head_sha=head, base_sha=base,
        requirements_digest=packet["requirements_digest"], review_round=rnd, verdict=accepted["verdict"],
        review_digest=accepted["review_digest"], review_request_id=request_id, reviewer_provenance=run.provenance,
        causation_id=request_id, correlation_id=request_id, **ctx), body=body, origin="review")
    mirrored = None
    if pr is not None:
        mirror = (f"Relayed from {issue.url}#issuecomment (event `{result_ev['event_id']}`) by the orchestrator. "
                  "This is not a GitHub review approval.\n\n" + body)
        mirrored = adapter.post_comment(pr.number, mirror).id
        store.append({"type": "mirror", "event_id": result_ev["event_id"], "pr": pr.number, "comment_id": mirrored})
    if accepted["verdict"] == "PASS":
        publisher.publish(events.build("READY_TO_MERGE", sender="orchestrator", recipient="maintainer", head_sha=head,
                                       causation_id=result_ev["event_id"], correlation_id=request_id, **ctx), origin="review")
        adapter.remove_label(args.issue, "agent:changes-requested")
        adapter.add_labels(args.issue, ["agent:ready-to-merge"])
    emit(args, {"ok": True, "verdict": accepted["verdict"], "result": str(run.raw_path), "accepted": accepted,
                "mirrored_to_pr": pr.number if mirrored else None})
    return 0


def cmd_report(args) -> int:
    from .report import dry_run_report
    policy = load_policy()
    repo = repo_root()
    text = dry_run_report(repo, Store.for_repo(repo), adapter_for(args, policy), policy, run_audit=not args.skip_audit)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def cmd_run(args) -> int:
    store = Store.for_repo(repo_root())
    if args.action == "status":
        emit(args, {"active_run": store.active_run(), "checkpoint": store.read_checkpoint(),
                    "pending_messages": len(store.pending())})
        return 0
    if args.action == "start":
        if store.active_run():
            emit(args, {"started": False, "reason": "a run is already active; resume it or stop it first"})
            return 2
        run = {"run_id": new_id("run"), "since": utcnow(), "scope": args.scope or "next eligible task",
               "budget": {"tasks": args.max_tasks, "review_rounds": load_policy()["review"]["max_rounds_per_attempt"]}}
        store.set_active_run(run)
        store.append({"type": "run", "phase": "started", **run})
        emit(args, {"started": True, **run})
        return 0
    run = store.active_run()
    store.set_active_run(None)
    store.append({"type": "run", "phase": "stopped", "run_id": (run or {}).get("run_id"), "reason": args.reason or "stopped"})
    store.checkpoint({"run_id": (run or {}).get("run_id"), "status": "stopped", "reason": args.reason or "stopped",
                      "next_action": "start a new run or resume with the weave-project skill"})
    emit(args, {"stopped": True, "run": run})
    return 0


def cmd_hook(args) -> int:
    from .hooks import main as hook_main
    return hook_main(args.event)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m tools.weave_workflow", description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--fixture", help="use a saved snapshot instead of live GitHub (offline rehearsal)")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="machine-readable output")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities", parents=[common], help="inspect installed tools, versions and scopes").set_defaults(fn=cmd_capabilities)
    p = sub.add_parser("discover", parents=[common], help="read-only live discovery of issues, milestones, board and PRs")
    p.add_argument("--save", help="write the snapshot to a JSON file")
    p.set_defaults(fn=cmd_discover)
    sub.add_parser("plan", parents=[common], help="dependency graph, milestone gates and the next eligible task (read-only)").set_defaults(fn=cmd_plan)
    p = sub.add_parser("reconcile", parents=[common], help="compare board, events, claims, worktrees, PRs and outbox")
    p.add_argument("--apply", action="store_true", help="replay the outbox and recover partial operations")
    p.set_defaults(fn=cmd_reconcile)
    p = sub.add_parser("claim", parents=[common], help="claim one eligible issue (dry run unless --apply)")
    p.add_argument("issue", type=int)
    p.add_argument("--base", default="origin/main")
    p.add_argument("--allowed-path", action="append")
    p.add_argument("--non-goal", action="append")
    p.add_argument("--override-order", action="store_true", help="claim an eligible task that is not first (recorded)")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_claim)
    p = sub.add_parser("event", parents=[common], help="validate or publish a protocol event from a JSON file")
    p.add_argument("action", choices=["validate", "publish"])
    p.add_argument("file")
    p.add_argument("--body")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_event)
    p = sub.add_parser("new-event", parents=[common], help="build a validated event (workers write it to the local outbox)")
    for flag in ("kind", "run-id", "issue", "sender", "recipient"):
        p.add_argument(f"--{flag}", required=True)
    p.add_argument("--attempt", type=int, default=1)
    p.add_argument("--milestone")
    p.add_argument("--correlation-id")
    p.add_argument("--causation-id")
    p.add_argument("--summary")
    p.add_argument("--fields", help="JSON object with kind-specific fields")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_new_event)
    p = sub.add_parser("transition", parents=[common], help="evaluate (dry run) or apply a board transition")
    p.add_argument("issue", type=int)
    p.add_argument("to", choices=["Todo", "In Progress", "In Review", "Done"])
    p.add_argument("--worktree")
    p.add_argument("--head")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_transition)
    p = sub.add_parser("verify", parents=[common], help="run the claim's checks on its candidate; --apply publishes VERIFICATION_RESULT")
    p.add_argument("issue", type=int)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("milestone-gate", parents=[common], help="evaluate a milestone exit gate; --apply publishes GATE_EVALUATED on the epic")
    p.add_argument("milestone")
    p.add_argument("--evidence", help="Markdown file: how each exit criterion and maintainer requirement is met")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_milestone_gate)
    sub.add_parser("outbox", parents=[common], help="list undelivered messages").set_defaults(fn=cmd_outbox)
    p = sub.add_parser("docs-audit", parents=[common], help="offline documentation drift audit")
    p.add_argument("--base", help="also run change checks against this base revision")
    p.add_argument("--impact", help="DOCS_IMPACT event or packet JSON with docs_impact")
    p.add_argument("--repo", help="audit this worktree instead of the current repository")
    p.add_argument("--publish", type=int, metavar="ISSUE", help="publish DOCS_AUDIT_RESULT for the audited head (needs --base and --apply)")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_docs_audit)
    p = sub.add_parser("docs-map", parents=[common], help="check or regenerate the generated part of the documentation map")
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_docs_map)
    p = sub.add_parser("review", parents=[common], help="build the review packet; --apply runs the independent Codex review")
    p.add_argument("issue", type=int)
    p.add_argument("--worktree", required=True)
    p.add_argument("--base", default="origin/main")
    p.add_argument("--ci-link", action="append")
    p.add_argument("--limitation", action="append")
    p.add_argument("--evidence", action="append", help="file with additional evidence (for example a live dry-run report)")
    p.add_argument("--delta", action="store_true", help="justified delta review of fixes (state why in --limitation)")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_review)
    p = sub.add_parser("report", parents=[common], help="full dry-run report (no remote writes)")
    p.add_argument("--out")
    p.add_argument("--skip-audit", action="store_true")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("run", parents=[common], help="start, stop or show the development run")
    p.add_argument("action", choices=["start", "stop", "status"])
    p.add_argument("--scope")
    p.add_argument("--max-tasks", type=int, default=1)
    p.add_argument("--reason")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("hook", parents=[common], help="Claude Code hook adapter (reads the hook payload on stdin)")
    p.add_argument("event")
    p.set_defaults(fn=cmd_hook)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except GitHubError as exc:
        print(f"GitHub error: {exc}", file=sys.stderr)
        return 5
