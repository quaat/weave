"""Board transition gates and guarded execution.

Gates are pure functions of authenticated events, maintainer decisions, the
issue's current requirements, the candidate head and integration evidence.
Manual card moves, labels or issue closure never satisfy a gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import events
from .github import AmbiguousWrite, GitHubError
from .model import Issue, ProjectInfo, acceptance_criteria, requirements_digest
from .publisher import DeliveryPaused, Publisher
from .state import Store, new_id

ALLOWED = {
    ("Todo", "In Progress"), ("In Progress", "In Review"), ("In Review", "In Progress"),
    ("In Review", "Done"), ("In Progress", "Todo"),
}


@dataclass
class TaskView:
    issue: Issue
    status: str | None
    events: list[dict]                     # authenticated, causally ordered
    decisions: list[dict] = field(default_factory=list)
    candidate_head: str | None = None      # current head of the task branch
    clean_tree: bool = False
    integration: dict | None = None        # {"pr", "merged", "pr_head_sha", "merge_sha", "checks_passed", "merge_in_base", "required_reviews_passed"}
    packet_valid: bool = False
    exclusive_claim: bool = False
    worktree: str | None = None
    policy: dict = field(default_factory=dict)

    def latest(self, kind: str, **match) -> dict | None:
        for e in reversed(self.events):
            if e["kind"] == kind and all(e.get(k) == v for k, v in match.items()):
                return e
        return None

    def all(self, kind: str, **match) -> list[dict]:
        return [e for e in self.events if e["kind"] == kind and all(e.get(k) == v for k, v in match.items())]


@dataclass
class Gate:
    from_status: str | None
    to_status: str
    passed: bool
    reasons: list[str]
    docs_stale: bool = False


def evaluate(view: TaskView, to_status: str) -> Gate:
    frm = view.status
    reasons: list[str] = []
    gate = Gate(frm, to_status, False, reasons)
    if (frm, to_status) not in ALLOWED:
        reasons.append(f"transition {frm!r} -> {to_status!r} is not permitted")
        return gate
    plan = view.latest("PLAN")
    req_now = requirements_digest(view.issue)
    if to_status == "In Progress" and frm == "Todo":
        _need(view.packet_valid, "complete task packet (including documentation impact) not validated", reasons)
        _need(view.exclusive_claim, "exclusive coordinator claim not held", reasons)
        _need(view.latest("CLAIMED"), "CLAIMED event not published", reasons)
        _need(view.latest("DOCS_IMPACT"), "DOCS_IMPACT event not published", reasons)
        _need(plan, "PLAN event not published", reasons)
        _need(view.worktree, "isolated worktree not assigned", reasons)
        if plan and plan["requirements_digest"] != req_now:
            reasons.append("issue requirements changed since PLAN; re-plan")
    elif to_status == "In Review":
        _gate_in_review(view, plan, req_now, gate)
    elif to_status == "In Progress" and frm == "In Review":
        head = view.candidate_head
        result = view.latest("REVIEW_RESULT")
        changed = result and result.get("verdict") == "REQUEST_CHANGES" and view.latest("CHANGES_REQUESTED")
        stale = view.latest("REVIEW_REQUESTED") and view.latest("REVIEW_REQUESTED")["head_sha"] != head
        failed_ev = (view.latest("VERIFICATION_RESULT", head_sha=head) or {}).get("result") == "FAIL" or \
                    (view.latest("DOCS_AUDIT_RESULT", head_sha=head) or {}).get("result") == "FAIL"
        _need(changed or stale or failed_ev or (plan and plan["requirements_digest"] != req_now),
              "no recorded change request, failed evidence, new edits or requirement change", reasons)
    elif to_status == "Done":
        _gate_done(view, plan, req_now, reasons)
    elif to_status == "Todo":
        _need(view.latest("RELEASED"), "RELEASED event (claim release with partial-work record) not published", reasons)
    gate.passed = not reasons
    return gate


def _need(cond, reason: str, reasons: list[str]) -> None:
    if not cond:
        reasons.append(reason)


def _gate_in_review(view: TaskView, plan: dict | None, req_now: str, gate: Gate) -> None:
    reasons = gate.reasons
    head = view.candidate_head
    _need(plan, "PLAN event missing", reasons)
    _need(head, "no committed candidate head", reasons)
    _need(view.clean_tree, "candidate worktree is not clean", reasons)
    if plan and plan["requirements_digest"] != req_now:
        reasons.append("issue requirements changed since PLAN; plan and evidence are invalid")
    ready = view.latest("IMPLEMENTATION_READY", head_sha=head) if head else None
    _need(ready, "IMPLEMENTATION_READY not published for the candidate head", reasons)
    if ready and plan:
        mapped = {c["id"] for c in ready["criteria_map"]}
        missing = [c["id"] for c in plan["criteria"] if c["id"] not in mapped]
        if missing:
            reasons.append(f"criteria without mapped evidence: {missing}")
    verification = view.latest("VERIFICATION_RESULT", head_sha=head) if head else None
    _need(verification and verification["result"] == "PASS", "required checks have not passed for the candidate head", reasons)
    audit = view.latest("DOCS_AUDIT_RESULT", head_sha=head, scope="change") if head else None
    if not audit or audit["result"] != "PASS":
        reasons.append("DOCS_AUDIT_RESULT is not passing for the candidate head")
        gate.docs_stale = True
    if ready and audit and ready["docs_audit_event_id"] != audit["event_id"]:
        reasons.append("IMPLEMENTATION_READY cites a different documentation audit than the latest for this head")
    for kind in ("local", "safety"):
        r = view.latest("LOCAL_REVIEW_RESULT", head_sha=head, review_kind=kind) if head else None
        _need(r and r["verdict"] == "PASS", f"{kind} review has not passed for the candidate head", reasons)
    req = view.latest("REVIEW_REQUESTED", head_sha=head) if head else None
    _need(req, "independent review not dispatched for the candidate head", reasons)


def _gate_done(view: TaskView, plan: dict | None, req_now: str, reasons: list[str]) -> None:
    head = view.candidate_head
    policy = view.policy
    decision_task = any(d["issue"] == view.issue.number for d in policy.get("decision_tasks", []))
    action = any(a["issue"] == view.issue.number for a in policy.get("maintainer_actions", []))
    if (decision_task or action) and not view.decisions:
        reasons.append("maintainer decision or action not recorded (/weave-decision comment by a maintainer)")
    _need(plan, "PLAN event missing", reasons)
    if plan and plan["requirements_digest"] != req_now:
        reasons.append("issue requirements changed since PLAN")
    request = view.latest("REVIEW_REQUESTED", head_sha=head) if head else None
    result = view.latest("REVIEW_RESULT", head_sha=head) if head else None
    if not result:
        reasons.append("no independent review result for the exact candidate head")
    else:
        if result["verdict"] != "PASS":
            reasons.append(f"latest independent review verdict is {result['verdict']}")
        if not request or result["review_request_id"] != request["event_id"]:
            reasons.append("review result does not answer the latest review request for this head")
        if result["requirements_digest"] != req_now:
            reasons.append("review was performed against different requirements")
        if request and result["base_sha"] != request["base_sha"]:
            reasons.append("review base differs from the requested base")
        idx = next(i for i, e in enumerate(view.events) if e["event_id"] == result["event_id"])
        later = [e for e in view.events[idx + 1:] if e["kind"] in ("REVIEW_RESULT", "REVIEW_REQUESTED")]
        if later:
            reasons.append("a newer review result supersedes the passing one")
    rounds = len(view.all("REVIEW_REQUESTED"))
    budget = policy.get("review", {}).get("max_rounds_per_attempt", 3)
    if rounds > budget:
        reasons.append(f"review budget exhausted ({rounds} > {budget} rounds); maintainer decision required")
    blocking = set()
    for r in view.all("CHANGES_REQUESTED"):
        blocking |= set(r["finding_ids"])
    disposed = {}
    for d in view.all("FINDING_DISPOSITION"):
        disposed[d["finding_id"]] = d["disposition"]
    open_findings = sorted(f for f in blocking if f not in disposed)
    if open_findings:
        reasons.append(f"findings without disposition: {open_findings}")
    accepted_by_maintainer = [f for f, d in disposed.items() if d == "accepted_by_maintainer"]
    if accepted_by_maintainer and not view.decisions:
        reasons.append(f"findings {accepted_by_maintainer} marked maintainer-accepted without a recorded maintainer decision")
    verification = view.latest("VERIFICATION_RESULT", head_sha=head) if head else None
    _need(verification and verification["result"] == "PASS", "checks not passing for the candidate head", reasons)
    audit = view.latest("DOCS_AUDIT_RESULT", head_sha=head, scope="change") if head else None
    _need(audit and audit["result"] == "PASS", "documentation audit not passing for the candidate head", reasons)
    integ = view.integration
    if not integ:
        reasons.append("no integration evidence (merged PR)")
    else:
        _need(integ.get("merged"), "pull request not merged (approved work stays In Review with agent:ready-to-merge)", reasons)
        _need(integ.get("pr_head_sha") == head, "merged PR head differs from the reviewed candidate", reasons)
        _need(integ.get("checks_passed"), "required checks did not pass on the merged head", reasons)
        _need(integ.get("merge_in_base"), "merge commit is not contained in the integration branch", reasons)
        _need(integ.get("tree_matches_candidate"), "integrated tree differs from the reviewed candidate tree", reasons)
        _need(integ.get("required_reviews_passed", False), "required human reviews not satisfied", reasons)


# ------------------------------------------------------------------ execution


@dataclass
class Transitioner:
    store: Store
    adapter: object
    publisher: Publisher
    project: ProjectInfo | None
    policy: dict
    dry_run: bool = True

    def execute(self, view: TaskView, to_status: str, ctx: dict) -> dict:
        """ctx: run_id, attempt, issue (owner/repo#n), milestone."""
        gate = evaluate(view, to_status)
        plan_ops: list[str] = []
        if not gate.passed:
            if gate.docs_stale:
                plan_ops.append("add label agent:docs-stale")
                if not self.dry_run:
                    self.adapter.add_labels(view.issue.number, ["agent:docs-stale"])
            return {"applied": False, "gate": gate.__dict__, "operations": plan_ops}
        if self.project is None:
            return {"applied": False, "gate": gate.__dict__,
                    "operations": ["blocked: project board not readable (missing project scope)"]}
        item = self.project.items.get(view.issue.number)
        if item is None:
            return {"applied": False, "gate": gate.__dict__, "operations": ["blocked: issue not on the board"]}
        op_id = new_id("op")
        plan_ops = [f"publish TRANSITION_INTENT {op_id}", f"set Status {view.status} -> {to_status} on item {item.item_id}",
                    "read back Status", "publish STATE_CHANGED", *self._label_ops(to_status, view.status)]
        if self.dry_run:
            return {"applied": False, "dry_run": True, "gate": gate.__dict__, "operations": plan_ops}
        observed = self.adapter.read_status(item.item_id)
        if observed != view.status:
            return {"applied": False, "gate": gate.__dict__,
                    "operations": [f"refused: observed status {observed!r} differs from expected {view.status!r}; reconcile first"]}
        intent = events.build("TRANSITION_INTENT", sender="orchestrator", recipient="orchestrator",
                              operation_id=op_id, from_status=view.status, to_status=to_status, **ctx)
        self.publisher.publish(intent)
        self.store.append({"type": "operation", "operation_id": op_id, "phase": "intent",
                           "issue": view.issue.number, "item_id": item.item_id,
                           "from_status": view.status, "to_status": to_status, "intent_event": intent["event_id"]})
        try:
            self.adapter.set_status(self.project, item.item_id, to_status)
        except AmbiguousWrite:
            pass  # verified by read-back below
        except GitHubError as exc:
            self.store.append({"type": "operation", "operation_id": op_id, "phase": "write_failed", "error": str(exc)})
            raise DeliveryPaused(f"status write failed; operation {op_id} left for recovery") from exc
        return self.complete(op_id, ctx)

    def complete(self, op_id: str, ctx: dict) -> dict:
        recs = self.store.operations().get(op_id, [])
        intent = next(r for r in recs if r["phase"] == "intent")
        if any(r["phase"] == "completed" for r in recs):
            return {"applied": True, "operation_id": op_id, "note": "already completed"}
        observed = self.adapter.read_status(intent["item_id"])
        if observed != intent["to_status"]:
            self.store.append({"type": "operation", "operation_id": op_id, "phase": "unverified", "observed": observed})
            return {"applied": False, "operation_id": op_id,
                    "operations": [f"status read back as {observed!r}; operation left for recovery"]}
        changed = events.build("STATE_CHANGED", sender="orchestrator", recipient="orchestrator",
                               operation_id=op_id, from_status=intent["from_status"],
                               to_status=intent["to_status"], causation_id=intent["intent_event"], **ctx)
        self.publisher.publish(changed)
        for op in self._label_ops(intent["to_status"], intent["from_status"]):
            verb, label = op.split(" label ")
            if verb == "add":
                self.adapter.add_labels(intent["issue"], [label])
            else:
                self.adapter.remove_label(intent["issue"], label)
        self.store.append({"type": "operation", "operation_id": op_id, "phase": "completed"})
        return {"applied": True, "operation_id": op_id}

    def recover(self, ctx_for: callable) -> list[dict]:
        """Finish or abandon partially applied operations after a restart."""
        out = []
        for op_id, recs in self.store.operations().items():
            phases = {r["phase"] for r in recs}
            if "intent" in phases and "completed" not in phases and "abandoned" not in phases:
                intent = next(r for r in recs if r["phase"] == "intent")
                observed = self.adapter.read_status(intent["item_id"])
                if observed == intent["to_status"]:
                    out.append(self.complete(op_id, ctx_for(intent["issue"])))
                else:
                    self.store.append({"type": "operation", "operation_id": op_id, "phase": "abandoned",
                                       "observed": observed})
                    out.append({"operation_id": op_id, "abandoned": True, "observed": observed,
                                "note": "status write did not land; gate must be re-evaluated before retrying"})
        return out

    def _label_ops(self, to_status: str, from_status: str | None = None) -> list[str]:
        group = self.policy["labels"]["exclusive_groups"][0]
        target = {"In Review": "agent:review-requested",
                  "In Progress": "agent:changes-requested" if from_status == "In Review" else None}.get(to_status)
        ops = [f"remove label {l}" for l in group if l != target]
        if target:
            ops.append(f"add label {target}")
        if to_status == "In Progress" and from_status == "Todo":
            ops.append("add label agent:managed")
        if to_status in ("In Review", "Done", "Todo"):
            ops.append("remove label agent:docs-stale")
        return ops
