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
from .integration import find_pr
from .publisher import DeliveryPaused, Publisher, authenticated_events
from .scheduler import active_implementation_issues, active_issues, capacity_history
from .state import PacketError, Store, run_issues
from .transitions import TaskView, Transitioner, automation_moved_done


def review_round(view: TaskView) -> int:
    return 1 + len(view.all("REVIEW_REQUESTED", attempt=view.attempt))


def automation_done_pr(store: Store, snap, n: int, trusted: list[dict]) -> int | None:
    """The merged PR whose closure of #n let project automation move the card to Done, when the
    recorded state is still In Review (see ``transitions.automation_moved_done``); else None."""
    plan = next((e for e in reversed(trusted) if e["kind"] == "PLAN"), None)
    if plan is None:
        return None
    try:
        branch = store.packet(n, plan["run_id"], plan["attempt"])["branch"]
    except (PacketError, OSError, KeyError):
        return None
    pr = find_pr(snap, n, None, branch)
    if pr is None:
        return None
    view = TaskView(issue=snap.issues[n], status=snap.status_of(n), events=trusted,
                    integration={"pr": pr.number, "merged": pr.merged, "head_ref": pr.head_ref,
                                 "claim_branch": branch, "closes_issue": n in pr.closes})
    return pr.number if automation_moved_done(view) else None


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
            pr = automation_done_pr(store, snap, n, trusted)
            if pr is not None:
                report["notes"].append(f"#{n}: board moved to Done by project automation after merged PR #{pr}; "
                                       f"run `transition {n} Done` to record it")
            else:
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
    # Capacity: exactly the planner's set (ledger plus open cards In Progress).
    ledger = store.events()
    ledger_active = active_implementation_issues(ledger)
    active = active_issues(snap, ledger_active)
    limit = policy["concurrency"]["max_active_implementation_issues"]
    report["active_implementation_issues"] = active
    if len(active) > limit:
        beyond, returned = capacity_history(ledger, limit, set(active) - set(ledger_active))
        returned = sorted({n for n in returned if n in ledger_active})
        listed = ", ".join(f"#{n}" for n in active)
        if returned and not beyond:
            report["notes"].append(
                f"{len(active)} active implementation issues exceed the limit of {limit} ({listed}) because "
                f"{', '.join(f'#{n}' for n in returned)} returned from In Review to In Progress; "
                "no new claim until the count is back under the limit")
        else:
            report["conflicts"].append(f"more active implementation issues than permitted ({len(active)} > {limit}): {listed}")
    for issue in run_issues(store.active_run()):
        if not any(c["issue"] == issue for c in report["claims"]):
            report["notes"].append(f"active run names #{issue} but no published claim exists; resume or release explicitly")
    return report
