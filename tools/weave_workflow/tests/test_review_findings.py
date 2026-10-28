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

from tools.weave_workflow import events
from tools.weave_workflow.cli import main, relay_problems
from tools.weave_workflow.integration import integration_evidence
from tools.weave_workflow.model import PullRequest, snapshot_to_dict
from tools.weave_workflow.publisher import Publisher, authenticated_events
from tools.weave_workflow.state import Store

from .support import REPO, Harness, mini_snapshot, policy


def run_cli(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, json.loads(buf.getvalue())


class ClaimSlotTests(unittest.TestCase):
    """F-001: the claim command enforces the planner's stop reason, not only candidate eligibility."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WEAVE_WORKFLOW_STATE"] = str(self.tmp / "state")

    def tearDown(self):
        del os.environ["WEAVE_WORKFLOW_STATE"]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fixture(self, snap) -> str:
        path = self.tmp / "snap.json"
        path.write_text(json.dumps(snapshot_to_dict(snap)))
        return str(path)

    def test_claim_refused_while_slot_occupied(self):
        snap = mini_snapshot()  # its "M0 Start" milestone is the live policy's current milestone M0
        rc, out = run_cli(["--fixture", self.fixture(snap), "claim", "10", "--json"])
        self.assertEqual(rc, 0, out)  # dry run accepted while the slot is free
        snap.project.items[10].status = "In Progress"
        rc, out = run_cli(["--fixture", self.fixture(snap), "claim", "11", "--json"])
        self.assertEqual(rc, 2)
        self.assertFalse(out["claimable"])
        self.assertIn("resume it", out["reasons"][0])

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

    def snap_with(self, merge_sha, checks=(("ci", "SUCCESS"),), merged_by="quaat"):
        snap = mini_snapshot()
        snap.pulls = [PullRequest(5, "merged", True, "agent/10-task", self.head, "main", "0" * 40, merge_sha, [10],
                                  list(checks), None, merged_by)]
        return snap

    def test_clean_merge_is_accepted(self):
        self.git("merge", "-q", "--no-ff", "-m", "merge", "agent/10-task")
        merge = self.git("rev-parse", "HEAD")
        ev = integration_evidence(self.repo, self.snap_with(merge), policy(), 10, self.head, "main")
        self.assertTrue(ev["merged"] and ev["checks_passed"] and ev["merge_in_base"])
        self.assertTrue(ev["tree_matches_candidate"])
        self.assertTrue(ev["required_reviews_passed"])

    def test_altered_merge_failed_checks_and_foreign_merger_are_detected(self):
        self.git("merge", "-q", "--no-ff", "--no-commit", "agent/10-task")
        (self.repo / "b.txt").write_text("changed during merge\n")
        self.git("add", "-A"); self.git("commit", "-q", "-m", "merge with edits")
        merge = self.git("rev-parse", "HEAD")
        ev = integration_evidence(self.repo, self.snap_with(merge, checks=(("ci", "FAILURE"),), merged_by="someone"),
                                  policy(), 10, self.head, "main")
        self.assertFalse(ev["tree_matches_candidate"])
        self.assertFalse(ev["checks_passed"])
        self.assertFalse(ev["required_reviews_passed"])

    def test_merge_not_in_base(self):
        self.git("switch", "-q", "-c", "elsewhere")
        self.git("merge", "-q", "--no-ff", "-m", "merge", "agent/10-task")
        merge = self.git("rev-parse", "HEAD")
        ev = integration_evidence(self.repo, self.snap_with(merge), policy(), 10, self.head, "main")
        self.assertFalse(ev["merge_in_base"])

    def test_no_pr_means_no_evidence(self):
        self.assertIsNone(integration_evidence(self.repo, mini_snapshot(), policy(), 10, self.head, "main"))


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
