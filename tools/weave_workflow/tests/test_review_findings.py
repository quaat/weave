"""Regression tests for the findings of the bootstrap's independent review (F-001 to F-005)."""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools.weave_workflow import cli, events
from tools.weave_workflow.cli import main, relay_problems
from tools.weave_workflow.integration import integration_evidence
from tools.weave_workflow.model import Issue, ProjectItem, PullRequest, digest, snapshot_to_dict
from tools.weave_workflow.publisher import Publisher, authenticated_events
from tools.weave_workflow.state import Store

from .support import REPO, Harness, mini_snapshot, policy, real_repo_refs, temp_git_repo


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, json.loads(buf.getvalue())


class ClaimSlotTests(unittest.TestCase):
    """F-001 and #67: claims honour the planner's stop reason, the concurrency limit, one claim per
    issue and disjoint allowed paths. Every claim runs against a temporary Git repository."""

    def setUp(self):
        self.refs_before = real_repo_refs()
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WEAVE_WORKFLOW_STATE"] = str(self.tmp / "state")
        (self.tmp / "state").mkdir()
        self.store = Store(self.tmp / "state")
        self.repo = temp_git_repo(self.tmp)
        self.patches = [mock.patch.object(cli, "repo_root", return_value=self.repo)]
        for patch in self.patches:
            patch.start()
        self.sequence = 0

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        del os.environ["WEAVE_WORKFLOW_STATE"]
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.assertEqual(real_repo_refs(), self.refs_before)  # no agent/* branch or worktree leaked

    def limit(self, n: int) -> None:
        pol = policy()
        pol["concurrency"]["max_active_implementation_issues"] = n
        patch = mock.patch.object(cli, "load_policy", return_value=pol)
        patch.start()
        self.patches.append(patch)

    def fixture(self, snap) -> str:
        path = self.tmp / "snap.json"
        path.write_text(json.dumps(snapshot_to_dict(snap)))
        return str(path)

    def snap(self, **statuses):
        snap = mini_snapshot()  # its "M0 Start" milestone is the live policy's current milestone M0
        snap.issues[13] = Issue(13, "Task 13", snap.issues[10].body, labels=["roadmap"], milestone=snap.issues[10].milestone)
        snap.project.items[13] = ProjectItem("item-13", 13, "Todo", "opt-todo")
        for key, status in statuses.items():
            snap.project.items[int(key[1:])].status = status
        return snap

    def record(self, kind: str, n: int, run_id: str = "run-other-0001", **fields) -> None:
        """Append an event to the ledger as another claim of the coordinator would have."""
        ev = events.build(kind, run_id=run_id, attempt=1, issue=f"{REPO}#{n}", milestone="M0",
                          sender="orchestrator", recipient="orchestrator", **fields)
        self.sequence += 1
        self.store.append({"type": "event", "event": ev, "sequence": self.sequence, "origin": "claim"})

    def claimed_elsewhere(self, n: int, paths: list[str] | None = None, status: str | None = None) -> None:
        """A claim of #n by this coordinator: CLAIMED, its packet's allowed paths, optionally a transition."""
        self.record("CLAIMED", n, claim_expires_at="2026-10-29T00:00:00Z", coordinator_host="other",
                    work_type="implementation")
        if paths is not None:
            path = self.tmp / f"packet-{n}.json"
            path.write_text(json.dumps({"allowed_paths": paths}))
            self.store.append({"type": "packet", "issue": n, "run_id": "run-other-0001", "attempt": 1,
                               "path": str(path), "digest": digest(path.read_text())})
        if status:
            self.moved(n, "Todo", status)

    def moved(self, n: int, frm: str, to: str) -> None:
        self.record("STATE_CHANGED", n, operation_id=f"op-test-{n}-{to.replace(' ', '')}", from_status=frm, to_status=to)

    def claim(self, snap, n, *extra):
        return run_cli(["--fixture", self.fixture(snap), "claim", str(n), "--base", "HEAD", "--json", *extra])

    def test_claims_up_to_the_concurrency_limit(self):
        self.assertEqual(policy()["concurrency"]["max_active_implementation_issues"], 3)
        self.claimed_elsewhere(10, ["inventory-proof/**"], "In Progress")
        rc, out = self.claim(self.snap(n10="In Progress"), 11, "--allowed-path", "agent-kit/**")
        self.assertEqual(rc, 0, out)  # a second claim is allowed while one is active
        self.claimed_elsewhere(11, ["agent-kit/**"], "In Progress")
        rc, out = self.claim(self.snap(n10="In Progress", n11="In Progress"), 12, "--allowed-path", "specification/**")
        self.assertEqual(rc, 0, out)  # and a third
        self.claimed_elsewhere(12, ["specification/**"], "In Progress")
        rc, out = self.claim(self.snap(n10="In Progress", n11="In Progress", n12="In Progress"), 13,
                             "--allowed-path", "docs/decisions/**")
        self.assertEqual(rc, 2)  # a fourth is refused with the limit at 3
        self.assertFalse(out["claimable"])
        self.assertIn("all 3 active implementation slot(s) occupied by #10, #11, #12", out["reasons"][0])

    def test_in_review_work_frees_its_slot(self):
        self.limit(2)
        self.claimed_elsewhere(10, ["inventory-proof/**"], "In Progress")
        self.claimed_elsewhere(11, ["agent-kit/**"], "In Progress")
        snap = self.snap(n10="In Progress", n11="In Progress")
        rc, out = self.claim(snap, 12, "--allowed-path", "specification/**")
        self.assertEqual(rc, 2)
        self.assertIn("all 2 active implementation slot(s) occupied by #10, #11", out["reasons"][0])
        self.moved(11, "In Progress", "In Review")
        snap = self.snap(n10="In Progress", n11="In Review")
        rc, out = run_cli(["--fixture", self.fixture(snap), "plan", "--json"])
        self.assertEqual((out["active"], out["next"]["issue"]), ([10], 12))
        rc, out = self.claim(snap, 11, "--allowed-path", "docs/decisions/**")
        self.assertEqual(rc, 2)  # its claim is still held: never claimed twice
        self.assertIn("claim still held (In Review or not yet released); not claimed again", out["reasons"])
        rc, out = self.claim(snap, 12, "--allowed-path", "specification/**", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertTrue(out["applied"])
        self.assertTrue((self.repo / ".worktrees" / "agent-12-task-12").is_dir())
        self.assertEqual(self.store.active_run()["active_issues"], [12])

    def test_work_returned_over_the_limit_blocks_new_claims(self):
        for n, paths in ((10, "inventory-proof/**"), (11, "agent-kit/**"), (12, "specification/**")):
            self.claimed_elsewhere(n, [paths], "In Progress")
        self.moved(12, "In Progress", "In Review")
        self.claimed_elsewhere(20, ["docs/decisions/**"], "In Progress")
        self.moved(12, "In Review", "In Progress")  # changes requested: four issues in implementation
        snap = self.snap(n10="In Progress", n11="In Progress", n12="In Progress")
        snap.project.items[20].status = "In Progress"
        rc, out = run_cli(["--fixture", self.fixture(snap), "plan", "--json"])
        self.assertIsNone(out["next"])
        self.assertEqual(out["active"], [10, 11, 12, 20])
        rc, out = self.claim(snap, 13, "--allowed-path", "README.md")
        self.assertEqual(rc, 2)
        self.assertIn("all 3 active implementation slot(s) occupied by #10, #11, #12, #20", out["reasons"][0])

    def test_same_issue_cannot_be_claimed_twice(self):
        self.claimed_elsewhere(10)  # claimed, but the card has not left Todo yet
        rc, out = self.claim(self.snap(), 10)
        self.assertEqual(rc, 2)
        self.assertIn("already an active implementation issue (claimed or In Progress)", out["reasons"])

    def test_overlapping_paths_are_refused_while_the_other_claim_is_held(self):
        self.claimed_elsewhere(10, ["agent-kit/**", "docs/development/documentation-map.md"], "In Progress")
        snap = self.snap(n10="In Progress")
        for paths in (["agent-kit/docs/**"], [], ["tools/weave_workflow/docmap.json"]):
            with self.subTest(paths=paths):
                rc, out = self.claim(snap, 11, *[a for p in paths for a in ("--allowed-path", p)])
                self.assertEqual(rc, 2)
                self.assertTrue(out["reasons"][0].startswith("allowed paths conflict with claimed issue #10 "
                                                             "(In Progress or In Review)"), out["reasons"])
        self.assertIn("'**' overlaps 'agent-kit/**'", self.claim(snap, 11)[1]["reasons"][0])
        self.assertIn("both may touch generated docs/development/documentation-map.md",
                      self.claim(snap, 11, "--allowed-path", "tools/weave_workflow/docmap.json")[1]["reasons"][0])
        rc, out = self.claim(snap, 11, "--allowed-path", "specification/**")
        self.assertEqual(rc, 0, out)  # disjoint paths are admitted
        self.moved(10, "In Progress", "In Review")  # #10 may return to In Progress: its paths stay reserved
        snap = self.snap(n10="In Review")
        rc, out = self.claim(snap, 11, "--allowed-path", "agent-kit/docs/**")
        self.assertEqual(rc, 2)
        self.assertIn("allowed paths conflict with claimed issue #10 (In Progress or In Review)", out["reasons"][0])
        rc, out = self.claim(snap, 11, "--allowed-path", "specification/**")
        self.assertEqual(rc, 0, out)
        self.record("COMPLETED", 10, head_sha="a" * 40, merge_sha="c" * 40)
        rc, out = self.claim(self.snap(n10="Done"), 11, "--allowed-path", "agent-kit/docs/**")
        self.assertEqual(rc, 0, out)  # released once the claim is completed

    def test_in_progress_card_without_a_recorded_claim_blocks_every_path(self):
        rc, out = self.claim(self.snap(n10="In Progress"), 11, "--allowed-path", "specification/**")
        self.assertEqual(rc, 2)
        self.assertIn("'specification/**' overlaps '**'", out["reasons"][0])

    def test_missing_base_is_reported_not_raised(self):
        rc, out = run_cli(["--fixture", self.fixture(mini_snapshot()), "claim", "10", "--base", "no-such-ref", "--json"])
        self.assertEqual(rc, 2)
        self.assertIn("no-such-ref", out["reasons"][0])

    def race(self, during_lock):
        """Run ``during_lock`` as another claim finishing while this process waits for the lock."""
        from tools.weave_workflow import state
        original = state.Store.coordinator_lock

        def racing_lock(self_, run_id):
            during_lock()
            return original(self_, run_id)
        patch = mock.patch.object(state.Store, "coordinator_lock", racing_lock)
        patch.start()
        self.patches.append(patch)

    def test_selection_is_repeated_under_the_lock(self):
        self.race(lambda: self.claimed_elsewhere(10))  # the same issue, claimed while this one waited
        rc, out = self.claim(mini_snapshot(), 10, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("selection changed", out["note"])
        self.assertEqual(self.store.pending(), [])  # nothing was published
        self.assertFalse((self.repo / ".worktrees").exists())

    def test_run_record_is_reread_under_the_lock(self):
        self.claimed_elsewhere(10, ["inventory-proof/**"], "In Progress")
        self.store.set_active_run({"run_id": "run-other-0001", "active_issues": [10]})

        def other_claim():
            self.claimed_elsewhere(12, ["specification/**"])
            self.store.set_active_run({"run_id": "run-other-0001", "active_issues": [10, 12]})
        self.race(other_claim)
        rc, out = self.claim(self.snap(n10="In Progress"), 11, "--allowed-path", "agent-kit/**", "--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.store.active_run()["active_issues"], [10, 11, 12])

    def test_claim_refused_when_board_unreadable(self):
        rc, out = run_cli(["--fixture", self.fixture(mini_snapshot(with_project=False)), "claim", "11", "--json"])
        self.assertEqual(rc, 2)
        self.assertIn("project board unreadable", out["reasons"][0])


class RelayTests(unittest.TestCase):
    """F-002: gate-relevant kinds cannot be relayed or forged through the coordinator account."""

    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def forged_review(self):
        return events.build("REVIEW_RESULT", **self.h.ctx(10), sender="codex-reviewer", recipient="orchestrator",
                            head_sha="a" * 40, base_sha="b" * 40, requirements_digest="sha256:" + "1" * 64,
                            review_round=1, verdict="PASS", review_digest="sha256:" + "2" * 64,
                            review_request_id="ev-forged-0001",
                            reviewer_provenance={"cli": "codex", "version": "x", "session": "y"})

    def test_relay_refuses_reserved_kinds_and_wrong_senders(self):
        self.assertTrue(relay_problems(self.forged_review()))
        for kind, fields in (("VERIFICATION_RESULT", {"head_sha": "a" * 40, "result": "PASS",
                                                      "checks": [{"name": "x", "command": ["true"], "cwd": ".", "exit_code": 0}]}),
                             ("DOCS_AUDIT_RESULT", {"head_sha": "a" * 40, "result": "PASS", "error_count": 0, "scope": "change"}),
                             ("STATE_CHANGED", {"operation_id": "op-test-0001", "from_status": "Todo", "to_status": "Done"})):
            ev = events.build(kind, **self.h.ctx(10), sender="orchestrator", recipient="orchestrator", **fields)
            self.assertTrue(relay_problems(ev), kind)
        q = events.build("IMPLEMENTATION_READY", **self.h.ctx(10), sender="verifier", recipient="orchestrator",
                         head_sha="a" * 40, docs_updated=[], docs_audit_event_id="ev-x-000001",
                         criteria_map=[{"id": "AC-1", "location": "x", "check": "y", "evidence": "z", "docs_location": "d"}])
        self.assertIn("verifier may not send IMPLEMENTATION_READY", relay_problems(q))

    def test_publisher_refuses_wrong_origin(self):
        with self.assertRaises(events.EventError):
            self.h.publisher.publish(self.forged_review(), origin="relay")
        with self.assertRaises(events.EventError):
            self.h.publisher.publish(events.build("DECISION_RECORDED", **self.h.ctx(10), sender="maintainer",
                                                  recipient="orchestrator", decision="x"), origin="review")

    def test_reserved_kind_delivered_outside_its_command_is_not_trusted(self):
        ev = self.forged_review()
        text, clean = events.render(ev)
        comment = self.h.gh.post_comment(10, text)
        self.h.store.append({"type": "delivery", "event_id": clean["event_id"], "issue_number": 10,
                             "comment_id": comment.id, "digest": events.event_digest(clean), "origin": "relay"})
        trusted, rejected = authenticated_events(self.h.store, self.h.snap, ["quaat"], 10)
        self.assertEqual(trusted, [])
        self.assertIn("not produced by its own command", rejected[0]["reason"])


class IntegrationEvidenceTests(unittest.TestCase):
    """F-003: integration evidence comes from PR data and Git, and detects altered integrations."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        self.env = env

        def git(*a):
            return subprocess.run(["git", *a], cwd=self.repo, env=env, capture_output=True, text=True, check=True).stdout.strip()
        self.git = git
        git("init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("a\n")
        git("add", "-A"); git("commit", "-q", "-m", "base")
        git("switch", "-q", "-c", "agent/10-task")
        (self.repo / "b.txt").write_text("b\n")
        git("add", "-A"); git("commit", "-q", "-m", "candidate")
        self.head = git("rev-parse", "HEAD")
        git("switch", "-q", "main")
        (self.repo / "c.txt").write_text("c\n")
        git("add", "-A"); git("commit", "-q", "-m", "other work on main")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def snap_with(self, merge_sha, checks=(("ci", "SUCCESS"),), merged_by="quaat", complete=True, base="main"):
        snap = mini_snapshot()
        snap.pulls = [PullRequest(5, "merged", True, "agent/10-task", self.head, base, "0" * 40, merge_sha, [10],
                                  list(checks), None, merged_by, complete)]
        return snap

    def pol(self):
        pol = policy()
        pol["integration"] = {"branch": "main", "ref": "main", "required_checks": ["ci"]}
        return pol

    def merged(self):
        self.git("merge", "-q", "--no-ff", "-m", "merge", "agent/10-task")
        return self.git("rev-parse", "HEAD")

    def test_clean_merge_is_accepted(self):
        self.git("merge", "-q", "--no-ff", "-m", "merge", "agent/10-task")
        merge = self.git("rev-parse", "HEAD")
        ev = integration_evidence(self.repo, self.snap_with(merge), self.pol(), 10, self.head, "agent/10-task")
        self.assertTrue(ev["merged"] and ev["checks_passed"] and ev["merge_in_base"])
        self.assertTrue(ev["tree_matches_candidate"])
        self.assertTrue(ev["required_reviews_passed"])
        self.assertEqual((ev["head_ref"], ev["claim_branch"], ev["closes_issue"]), ("agent/10-task", "agent/10-task", True))

    def test_altered_merge_failed_checks_and_foreign_merger_are_detected(self):
        self.git("merge", "-q", "--no-ff", "--no-commit", "agent/10-task")
        (self.repo / "b.txt").write_text("changed during merge\n")
        self.git("add", "-A"); self.git("commit", "-q", "-m", "merge with edits")
        merge = self.git("rev-parse", "HEAD")
        ev = integration_evidence(self.repo, self.snap_with(merge, checks=(("ci", "FAILURE"),), merged_by="someone"),
                                  self.pol(), 10, self.head, "agent/10-task")
        self.assertFalse(ev["tree_matches_candidate"])
        self.assertFalse(ev["checks_passed"])
        self.assertFalse(ev["required_reviews_passed"])

    def test_merge_not_in_base(self):
        self.git("switch", "-q", "-c", "elsewhere")
        self.git("merge", "-q", "--no-ff", "-m", "merge", "agent/10-task")
        merge = self.git("rev-parse", "HEAD")
        ev = integration_evidence(self.repo, self.snap_with(merge), self.pol(), 10, self.head, "agent/10-task")
        self.assertFalse(ev["merge_in_base"])

    def test_required_checks_must_all_be_present_complete_and_passing(self):
        merge = self.merged()
        cases = {
            "missing required check": self.snap_with(merge, checks=(("other", "SUCCESS"),)),
            "incomplete check list": self.snap_with(merge, complete=False),
            "wrong integration branch": self.snap_with(merge, base="release"),
        }
        snap = self.snap_with(merge)
        snap.branch_protection = {"required_status_checks": {"contexts": ["ci", "security-scan"]}}
        cases["protection requires an absent check"] = snap
        snap = self.snap_with(merge)
        snap.branch_protection_error = "HTTP 502"
        cases["unreadable protection"] = snap
        for name, s in cases.items():
            with self.subTest(name):
                self.assertFalse(integration_evidence(self.repo, s, self.pol(), 10, self.head, "agent/10-task")["checks_passed"])

    def test_pr_must_come_from_the_claim_branch_and_close_the_issue(self):
        merge = self.merged()
        snap = self.snap_with(merge)
        snap.pulls[0].closes = []
        self.assertIsNone(integration_evidence(self.repo, snap, self.pol(), 10, self.head, "agent/10-task"))
        snap = self.snap_with(merge)
        self.assertIsNone(integration_evidence(self.repo, snap, self.pol(), 10, self.head, "agent/10-other"))

    def test_no_pr_means_no_evidence(self):
        self.assertIsNone(integration_evidence(self.repo, mini_snapshot(), self.pol(), 10, self.head, "agent/10-task"))


class BoundEvidenceTests(unittest.TestCase):
    """F-002 and F-007: verification and audit results are bound to the recorded claim."""

    def setUp(self):
        self.h = Harness()
        os.environ["WEAVE_WORKFLOW_STATE"] = str(self.h.store.root)
        self.h.policy = policy()  # the CLI reads the live policy; use its M0 for the fixture
        self.h.publisher = Publisher(self.h.store, self.h.gh, REPO, ["quaat"])
        self.wt = Path(tempfile.mkdtemp()) / "wt"
        self.wt.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        def git(*a):
            return subprocess.run(["git", *a], cwd=self.wt, env=env, capture_output=True, text=True, check=True).stdout.strip()
        git("init", "-q"); (self.wt / "README.md").write_text("x\n"); git("add", "-A"); git("commit", "-q", "-m", "base")
        self.base = git("rev-parse", "HEAD")
        (self.wt / "README.md").write_text("y\n"); git("commit", "-qam", "change")
        self.h.publish("CLAIMED", 10, claim_expires_at="2026-10-28T08:00:00Z", coordinator_host="t", work_type="implementation")
        self.h.publish("DOCS_IMPACT", 10, docs_impact=[{"path": "README.md", "reason": "r", "status": "required"}])
        plan = self.h.plan_event(10)
        packet = {"run_id": plan["run_id"], "attempt": 1, "worktree": str(self.wt), "base_sha": self.base, "checks": []}
        self.packet_path = self.h.store.run_dir(plan["run_id"]) / "packet-10-a1.json"
        self.packet_path.write_text(json.dumps(packet))
        from tools.weave_workflow.model import digest
        self.h.store.append({"type": "packet", "issue": 10, "run_id": plan["run_id"], "attempt": 1,
                             "path": str(self.packet_path), "digest": digest(self.packet_path.read_text())})
        self.fixture = Path(self.h.tmp) / "snap.json"
        self.fixture.write_text(json.dumps(snapshot_to_dict(self.h.snap)))

    def tearDown(self):
        del os.environ["WEAVE_WORKFLOW_STATE"]
        shutil.rmtree(self.wt.parent, ignore_errors=True)
        self.h.close()

    def test_empty_packet_cannot_yield_pass(self):
        rc, out = run_cli(["--fixture", str(self.fixture), "verify", "10", "--json"])
        self.assertGreaterEqual(len(out["checks"]), 1)  # derived checks are always added
        self.assertEqual(out["result"], "FAIL")      # the derived audit cannot run in this foreign tree
        self.assertTrue(out["published"]["dry_run"])

    def test_tampered_packet_is_rejected(self):
        self.packet_path.write_text(self.packet_path.read_text().replace('"checks": []', '"checks": [{"name": "x", "cwd": ".", "argv": ["true"]}]'))
        with self.assertRaises(SystemExit):
            run_cli(["--fixture", str(self.fixture), "verify", "10", "--json"])

    def test_docs_audit_publication_uses_claim_base_and_impact(self):
        with redirect_stdout(io.StringIO()):
            rc = main(["--fixture", str(self.fixture), "docs-audit", "--publish", "10", "--base", "HEAD"])
        self.assertEqual(rc, 2)  # a base other than the claim's is refused
        shortened = Path(self.h.tmp) / "impact.json"
        shortened.write_text(json.dumps({"docs_impact": []}))
        with self.assertRaises(SystemExit):
            main(["--fixture", str(self.fixture), "docs-audit", "--publish", "10", "--impact", str(shortened)])


class ReplayTests(unittest.TestCase):
    """F-004: an ambiguous write followed by a failed lookup is never re-posted blindly."""

    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.close()

    def test_ambiguous_write_then_failed_lookup_then_restart(self):
        from tools.weave_workflow.publisher import DeliveryPaused
        self.h.gh.fail_next = ["post_comment:ambiguous", "snapshot:unavailable"]
        with self.assertRaises(DeliveryPaused):
            self.h.publish("PROGRESS", 10)
        self.assertEqual(len(self.h.snap.issues[10].comments), 1)  # the write landed
        self.h.gh.fail_next = ["snapshot:unavailable"]
        restarted = Publisher(Store(self.h.store.root), self.h.gh, REPO, ["quaat"])
        with self.assertRaises(DeliveryPaused):
            restarted.flush()  # lookup fails again: pause, do not post
        self.assertEqual(len(self.h.snap.issues[10].comments), 1)
        self.assertEqual(restarted.flush(), 1)  # lookup succeeds: recorded, not re-posted
        self.assertEqual(len(self.h.snap.issues[10].comments), 1)
        self.assertEqual(len(authenticated_events(self.h.store, self.h.snap, ["quaat"], 10)[0]), 1)


class DerivedChecksTests(unittest.TestCase):
    """F-002 (round 3): derived checks cover every CI step for the touched components."""

    def test_derived_checks_cover_ci(self):
        from tools.weave_workflow.cli import derive_checks
        from .support import ROOT
        checks = derive_checks(ROOT, ["inventory-proof/x.py", "agent-kit/scripts/weave.py",
                                      "specification/docs/chapters/status.rst", "tools/weave_workflow/cli.py"])
        commands = [" ".join(c["argv"]) + " @" + c["cwd"] for c in checks]
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        expected = {
            "unittest discover -s tests @inventory-proof": "python -m unittest discover -s tests",
            "demo.py @inventory-proof": "python demo.py",
            "durable.py @inventory-proof": "python durable.py",
            "weave.py doctor @agent-kit": "weave.py doctor",
            "unittest discover -s tests @agent-kit": "-m unittest discover -s tests -v",
            "weave.py examples @agent-kit": "weave.py examples",
            "weave.py test @agent-kit": "weave.py test",
            "unittest discover -s tests @agent-kit/demos/": "for demo in demos/*/",
            "make validate-offline @specification": "make validate-offline",
            "make singlehtml text @specification": "make singlehtml text",
            "audit_html.py _build/singlehtml @specification": "audit_html.py _build/singlehtml",
            "tools/weave_workflow/tests": "tools/weave_workflow/tests",
            "tools.weave_workflow docs-audit": "tools.weave_workflow docs-audit",
            "tools.weave_workflow docs-map": "tools.weave_workflow docs-map",
        }
        for needle, ci_text in expected.items():
            with self.subTest(needle):
                self.assertIn(ci_text, ci)  # the step exists in CI ...
                self.assertTrue(any(needle.split(" @")[0] in c and ("@" not in needle or needle.split(" @")[1] in c)
                                    for c in commands), commands)  # ... and is derived
        demos = sorted(p.name for p in (ROOT / "agent-kit/demos").glob("*/") if (p / "tests").is_dir())
        self.assertEqual(sorted(c["cwd"].split("/")[-1] for c in checks if c["name"].startswith("agent-kit demo ")), demos)


class ReviewPacketTests(unittest.TestCase):
    """F-005: the packet carries dependency and gate evidence; results render for PR mirroring."""

    def test_render_result_marks_relay(self):
        from tools.weave_workflow.review import render_result
        text = render_result({"verdict": "PASS", "summary": "ok", "criteria": [{"id": "AC-1", "status": "satisfied", "evidence": "e"}],
                              "findings": [], "limitations": []}, {"cli": "codex exec", "version": "v", "session": "s"})
        self.assertIn("not a GitHub review approval", text)
        self.assertIn("| AC-1 | satisfied | e |", text)


if __name__ == "__main__":
    unittest.main()
