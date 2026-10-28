"""Restart reconciliation: board status, issue events, claims, worktrees, PR heads,
review identity, outbox deliveries and partial operations.

Discrepancies are reported, never silently overwritten: a maintainer may have
moved a card deliberately.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .github import GitHubError
from .publisher import DeliveryPaused, Publisher, authenticated_events
from .state import Store
from .transitions import TaskView, Transitioner


def review_round(view: TaskView) -> int:
    attempt = max([e["attempt"] for e in view.events] or [1])
    return 1 + len([e for e in view.all("REVIEW_REQUESTED") if e["attempt"] == attempt])


def _worktrees(repo: Path) -> list[dict]:
    out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    trees, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                trees.append(cur)
            cur = {}
            continue
        key, _, value = line.partition(" ")
        cur[key] = value
    return trees


def reconcile(repo: Path, store: Store, adapter, policy: dict, apply: bool = False) -> dict:
    report = {"conflicts": [], "notes": [], "rejected_envelopes": [], "outbox_pending": len(store.pending()),
              "recovered_operations": [], "claims": [], "worktrees": []}
    try:
        snap = adapter.snapshot()
    except GitHubError as exc:
        report["conflicts"].append(f"GitHub unavailable: {exc}; dispatches and transitions are paused")
        return report
    coordinators = policy["actors"]["coordinator_logins"]
    publisher = Publisher(store, adapter, policy["repository"], coordinators)
    if apply and store.pending():
        try:
            report["delivered"] = publisher.flush()
        except DeliveryPaused as exc:
            report["conflicts"].append(str(exc))
    if apply:
        tr = Transitioner(store, adapter, publisher, snap.project, policy, dry_run=False)
        report["recovered_operations"] = tr.recover(lambda n: {"run_id": (store.active_run() or {}).get("run_id", "run-recovery"),
                                                                 "attempt": 1, "issue": f"{policy['repository']}#{n}",
                                                                 "milestone": snap.issues[n].milestone_key})
    else:
        partial = [op for op, recs in store.operations().items()
                   if {"intent"} <= {r["phase"] for r in recs} and not {"completed", "abandoned"} & {r["phase"] for r in recs}]
        if partial:
            report["notes"].append(f"partial operations awaiting recovery: {partial}")
    issues_with_events = {int(e["issue"].split("#")[1]) for e in store.events()}
    managed = {n for n, i in snap.issues.items() if "agent:managed" in i.labels} | issues_with_events
    for n in sorted(managed):
        if n not in snap.issues:
            continue
        trusted, rejected = authenticated_events(store, snap, coordinators, n)
        for r in rejected:
            report["rejected_envelopes"].append({"issue": n, **r})
        changes = [e for e in trusted if e["kind"] == "STATE_CHANGED"]
        board = snap.status_of(n)
        if changes and snap.project is not None and board != changes[-1]["to_status"]:
            report["conflicts"].append(
                f"#{n}: board status {board!r} differs from last recorded transition {changes[-1]['to_status']!r} "
                f"(manual change?); record the discrepancy and confirm with the maintainer before acting")
        claimed = [e for e in trusted if e["kind"] == "CLAIMED"]
        released = [e for e in trusted if e["kind"] in ("RELEASED", "COMPLETED")]
        if claimed and (not released or released[-1]["created_at"] < claimed[-1]["created_at"]):
            report["claims"].append({"issue": n, "run_id": claimed[-1]["run_id"], "attempt": claimed[-1]["attempt"],
                                     "claimed_at": claimed[-1]["created_at"]})
        heads = [e["head_sha"] for e in trusted if e["kind"] == "REVIEW_RESULT"]
        for pr in snap.pulls:
            if pr.head_ref.startswith(f"agent/{n}-") and pr.state == "open" and heads and pr.head_sha != heads[-1]:
                report["notes"].append(f"#{n}: PR #{pr.number} head {pr.head_sha[:12]} differs from last reviewed {heads[-1][:12]}; earlier review is stale")
    for tree in _worktrees(repo):
        branch = tree.get("branch", "").removeprefix("refs/heads/")
        m = re.match(r"agent/(\d+)-", branch)
        if m:
            num = m.group(1)
            active = any(str(c["issue"]) == num for c in report["claims"])
            report["worktrees"].append({"path": tree.get("worktree"), "branch": branch, "claim_active": active})
            if not active:
                report["notes"].append(f"worktree {tree.get('worktree')} ({branch}) has no active claim; preserved, not removed")
    if len(report["claims"]) > policy["concurrency"]["max_active_implementation_issues"]:
        report["conflicts"].append(f"more active claims than permitted: {report['claims']}")
    run = store.active_run()
    if run and run.get("active_issue") and not any(c["issue"] == run["active_issue"] for c in report["claims"]):
        report["notes"].append(f"active run names #{run['active_issue']} but no published claim exists; resume or release explicitly")
    return report
