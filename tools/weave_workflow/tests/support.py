"""Deterministic offline fixtures: a small roadmap, a fake board and a temporary ledger."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.weave_workflow import events
from tools.weave_workflow.github import FakeGitHub
from tools.weave_workflow.model import (Issue, Milestone, ProjectInfo, ProjectItem, PullRequest,
                                        Snapshot, requirements_digest)
from tools.weave_workflow.publisher import Publisher
from tools.weave_workflow.state import Store

ROOT = Path(__file__).resolve().parents[3]
POLICY = json.loads((ROOT / "tools/weave_workflow/policy.json").read_text())
REPO = POLICY["repository"]
HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40

TASK_BODY = """## Scope
Do the thing.

## Acceptance criteria
- [ ] First criterion
- [ ] Second criterion
"""


def policy(**overrides) -> dict:
    p = copy.deepcopy(POLICY)
    p.update(overrides)
    return p


def mini_policy() -> dict:
    """Policy for the miniature roadmap: M0 (epic 100), M1 (epic 101), M10 (epic 110)."""
    p = policy()
    p["milestones"] = {
        "M0": {"epic": 100, "requires": [], "source": "test"},
        "M1": {"epic": 101, "requires": ["M0"], "source": "test"},
        "M10": {"epic": 110, "requires": ["M1"], "source": "test"},
    }
    p["dependencies"] = []
    p["cross_milestone_requirements"] = [{"issue": 21, "owner_milestone": "M1", "required_by": "M10", "source": "test"}]
    p["early_start_exceptions"] = [{"milestone": "M10", "issues": [31], "allowed_scope": "design only",
                                     "allowed_during": "M0", "source": "test"}]
    p["early_start_exceptions_active"] = False
    p["decision_tasks"] = [{"issue": 12, "decision": "pick one", "maintainer_evidence": [], "source": "test"}]
    p["maintainer_actions"] = []
    return p


def mini_snapshot(with_project: bool = True) -> Snapshot:
    ms = {"M0": Milestone(1, "M0 Start", "open"), "M1": Milestone(2, "M1 Next", "open"),
          "M10": Milestone(3, "M10 Later", "open")}
    issues = {}

    def add(n, key, body=TASK_BODY, labels=None, **kw):
        issues[n] = Issue(number=n, title=f"Task {n}", body=body, labels=labels or ["roadmap"],
                          milestone=ms[key] if key else None, url=f"https://github.com/{REPO}/issues/{n}", **kw)

    add(100, "M0", body="Depends on: Start\n\n## Work items\n- [ ] #11\n- [ ] #10\n- [ ] #12\n", labels=["roadmap", "epic"])
    add(101, "M1", body="Depends on: M0\n\n## Work items\n- [ ] #20\n- [ ] #21\n", labels=["roadmap", "epic"])
    add(110, "M10", body="Depends on: M1\n\n## Work items\n- [ ] #30\n- [ ] #21\n", labels=["roadmap", "epic"])
    add(10, "M0")
    add(11, "M0")
    add(12, "M0")
    add(20, "M1")
    add(21, "M1", body=TASK_BODY + "\n## Depends on\n#20\n")
    add(30, "M10")
    add(31, "M10")
    add(40, None)
    add(41, None, labels=["roadmap", "deferred"])
    project = None
    if with_project:
        options = {"Todo": "opt-todo", "In Progress": "opt-prog", "In Review": "opt-rev", "Done": "opt-done"}
        items = {n: ProjectItem(f"item-{n}", n, "Todo", "opt-todo") for n in issues}
        project = ProjectInfo("proj-1", "Weave", "field-status", options, items)
    return Snapshot(issues=issues, milestones=list(ms.values()), project=project)


class Harness:
    """Fake GitHub plus a temporary ledger; publishes events the way the coordinator does."""

    def __init__(self, snap: Snapshot | None = None, pol: dict | None = None):
        self.tmp = tempfile.mkdtemp(prefix="weave-wf-test-")
        self.store = Store(Path(self.tmp))
        self.snap = snap or mini_snapshot()
        self.policy = pol or mini_policy()
        self.gh = FakeGitHub(self.snap)
        self.publisher = Publisher(self.store, self.gh, REPO, self.policy["actors"]["coordinator_logins"])
        self.attempt = 1  # attempt of the events published next (a new claim starts a new attempt)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ctx(self, n: int, attempt: int | None = None) -> dict:
        return {"run_id": "run-test-0001", "attempt": attempt or self.attempt, "issue": f"{REPO}#{n}",
                "milestone": self.snap.issues[n].milestone_key}

    def publish(self, kind: str, n: int, sender="orchestrator", recipient="orchestrator", body="", origin=None, **fields) -> dict:
        """Publish as the command that owns the kind would (reserved kinds), else through the relay."""
        from tools.weave_workflow.publisher import RESERVED_ORIGINS
        ev = events.build(kind, sender=sender, recipient=recipient, **self.ctx(n), **fields)
        if origin is None:
            origin = next(iter(sorted(RESERVED_ORIGINS.get(kind) or {"relay"})))
        return self.publisher.publish(ev, body, origin=origin)

    def plan_event(self, n: int) -> dict:
        from tools.weave_workflow.model import acceptance_criteria
        crit = [{"id": c["id"], "text_digest": c["text_digest"], "verification": "unit test"}
                for c in acceptance_criteria(self.snap.issues[n].body)]
        return self.publish("PLAN", n, requirements_digest=requirements_digest(self.snap.issues[n]), criteria=crit)

    def ready_for_review(self, n: int, head: str = HEAD) -> None:
        """Publish the full evidence chain required for In Progress -> In Review."""
        self.publish("CLAIMED", n, claim_expires_at="2026-10-28T08:00:00Z", coordinator_host="test", work_type="implementation")
        self.publish("DOCS_IMPACT", n, docs_impact=[{"path": "README.md", "reason": "test", "status": "required"}])
        self.plan_event(n)
        audit = self.publish("DOCS_AUDIT_RESULT", n, head_sha=head, result="PASS", error_count=0, scope="change")
        self.publish("VERIFICATION_RESULT", n, head_sha=head, result="PASS",
                     checks=[{"name": "tests", "command": ["python3", "-m", "unittest"], "cwd": ".", "exit_code": 0}])
        self.publish("IMPLEMENTATION_READY", n, head_sha=head, docs_updated=["README.md"],
                     docs_audit_event_id=audit["event_id"],
                     criteria_map=[{"id": f"AC-{i}", "location": "x.py", "check": "test_x", "evidence": "pass",
                                    "docs_location": "README.md"} for i in (1, 2)])
        for kind in ("local", "safety"):
            self.publish("LOCAL_REVIEW_RESULT", n, head_sha=head, verdict="PASS", review_kind=kind)

    def request_review(self, n: int, head: str = HEAD, base: str = BASE, rnd: int = 1) -> dict:
        return self.publish("REVIEW_REQUESTED", n, recipient="codex-reviewer", head_sha=head, base_sha=base,
                            requirements_digest=requirements_digest(self.snap.issues[n]), review_round=rnd)

    def review_result(self, n: int, request: dict, verdict: str = "PASS", head: str = HEAD) -> dict:
        return self.publish("REVIEW_RESULT", n, sender="codex-reviewer", head_sha=head, base_sha=request["base_sha"],
                            requirements_digest=request["requirements_digest"], review_round=request["review_round"],
                            verdict=verdict, review_digest="sha256:" + "0" * 64, review_request_id=request["event_id"],
                            reviewer_provenance={"cli": "codex exec", "version": "test", "session": "s-1"},
                            causation_id=request["event_id"])

    def view(self, n: int, **kw):
        from tools.weave_workflow.cli import _view
        return _view(self.store, self.snap, self.policy, n, **kw)


def integration(**overrides) -> dict:
    data = {"pr": 1, "merged": True, "pr_head_sha": HEAD, "merge_sha": MERGE, "checks_passed": True,
            "merge_in_base": True, "tree_matches_candidate": True, "required_reviews_passed": True}
    data.update(overrides)
    return data


def repo_copy() -> Path:
    """A throwaway Git repository holding the current working-tree files (tracked and untracked)."""
    tmp = Path(tempfile.mkdtemp(prefix="weave-audit-test-")) / "repo"
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.split("\0")
    for rel in filter(None, files):
        src = ROOT / rel
        if not src.is_file():
            continue
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", *args], cwd=tmp, check=True, env=env, capture_output=True)
    return tmp
