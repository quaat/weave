"""Integration evidence for the Done gate, derived from GitHub PR data and local Git.

Nothing here is taken from the caller: the merged state, merging actor, check results and
review decision come from the fetched pull request, and branch containment and tree
equality are recomputed with Git.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .model import PullRequest, Snapshot

PASSING = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip()


def find_pr(snap: Snapshot, issue: int, head: str | None = None) -> PullRequest | None:
    """The task's PR: head branch ``agent/<issue>-…``, preferring the one at ``head``."""
    prs = [p for p in snap.pulls if re.match(rf"agent/{issue}-", p.head_ref)]
    if head:
        exact = [p for p in prs if p.head_sha == head]
        prs = exact or prs
    merged = [p for p in prs if p.merged]
    return (merged or [p for p in prs if p.state == "open"] or prs or [None])[-1]


def integration_evidence(repo: Path, snap: Snapshot, policy: dict, issue: int, head: str,
                         base_ref: str = "origin/main") -> dict | None:
    pr = find_pr(snap, issue, head)
    if pr is None:
        return None
    ev = {"pr": pr.number, "merged": pr.merged, "pr_head_sha": pr.head_sha, "merge_sha": pr.merge_sha,
          "merged_by": pr.merged_by, "checks": pr.checks}
    ev["checks_passed"] = bool(pr.checks) and all(state in PASSING for _, state in pr.checks)
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
