"""Integration evidence for the Done gate, derived from GitHub PR data and local Git.

Nothing here is taken from the caller: the merged state, merging actor, check results and
review decision come from the fetched pull request, and branch containment and tree
equality are recomputed with Git.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .model import PullRequest, Snapshot

PASSING = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def find_pr(snap: Snapshot, issue: int, head: str | None, branch: str) -> PullRequest | None:
    """The task's PR: from the claim's exact branch and declaring that it closes the issue."""
    prs = [p for p in snap.pulls if p.head_ref == branch and issue in p.closes]
    if head:
        exact = [p for p in prs if p.head_sha == head]
        prs = exact or prs
    merged = [p for p in prs if p.merged]
    return (merged or [p for p in prs if p.state == "open"] or prs or [None])[-1]


def required_checks(snap: Snapshot, policy: dict) -> tuple[set[str], str | None]:
    """Required check names: the policy's CI jobs plus those required by branch protection.
    Returns (names, error); an unreadable protection setting is an error, never an empty set."""
    names = set(policy["integration"]["required_checks"])
    if snap.branch_protection_error:
        return names, f"branch protection unreadable: {snap.branch_protection_error}"
    rsc = (snap.branch_protection or {}).get("required_status_checks") or {}
    names |= set(rsc.get("contexts") or [])
    names |= {c["context"] for c in rsc.get("checks") or []}
    return names, None


def integration_evidence(repo: Path, snap: Snapshot, policy: dict, issue: int, head: str, branch: str) -> dict | None:
    base_ref = policy["integration"]["ref"]
    pr = find_pr(snap, issue, head, branch)
    if pr is None:
        return None
    ev = {"pr": pr.number, "merged": pr.merged, "pr_head_sha": pr.head_sha, "merge_sha": pr.merge_sha,
          "merged_by": pr.merged_by, "checks": pr.checks, "integration_ref": base_ref,
          "pr_base_ref": pr.base_ref}
    required, error = required_checks(snap, policy)
    states = {}
    for name, state in pr.checks:
        states.setdefault(name, []).append(state)
    missing = sorted(n for n in required if n not in states)
    failing = sorted(n for n, s in states.items() if any(x not in PASSING for x in s))
    ev.update({"required_checks": sorted(required), "missing_checks": missing, "failing_checks": failing,
               "checks_complete": pr.checks_complete, "check_evidence_error": error})
    ev["checks_passed"] = (pr.checks_complete and error is None and not missing and not failing
                           and pr.base_ref == policy["integration"]["branch"])
    protection = snap.branch_protection or {}
    if protection.get("required_pull_request_reviews"):
        ev["required_reviews_passed"] = pr.review_decision == "APPROVED"
        ev["review_rule"] = "branch protection requires approving reviews"
    else:
        ev["required_reviews_passed"] = pr.merged and pr.merged_by in policy["actors"]["maintainer_logins"]
        ev["review_rule"] = "no required reviews configured; the maintainer's own merge is the human acceptance"
    ev["merge_in_base"] = False
    ev["tree_matches_candidate"] = False
    if pr.merged and pr.merge_sha:
        rc, _ = _git(repo, "merge-base", "--is-ancestor", pr.merge_sha, base_ref)
        ev["merge_in_base"] = rc == 0
        rc1, merged_tree = _git(repo, "rev-parse", f"{pr.merge_sha}^{{tree}}")
        rc2, parent = _git(repo, "rev-parse", f"{pr.merge_sha}^1")
        if rc1 == 0 and rc2 == 0:
            # Merge commit, squash or fast-forward: merging the candidate into the first parent must
            # reproduce the integrated tree exactly; anything else changed the reviewed content.
            rc3, expected = _git(repo, "merge-tree", "--write-tree", parent, head)
            ev["tree_matches_candidate"] = rc3 == 0 and expected.splitlines()[0] == merged_tree
    return ev
