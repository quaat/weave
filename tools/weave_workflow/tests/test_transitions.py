"""Scenarios 3, 4 and 8: the full lifecycle, rejection paths, stale or invalid reviews, and merge rules."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tools.weave_workflow import review
from tools.weave_workflow.model import requirements_digest
from tools.weave_workflow.transitions import Transitioner, evaluate

from .support import BASE, HEAD, Harness, integration, policy

N = 10


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.tr = Transitioner(self.h.store, self.h.gh, self.h.publisher, self.h.snap.project, self.h.policy, dry_run=False)

    def tearDown(self):
        self.h.close()

    def go(self, to, **kw):
        kw.setdefault("head", HEAD)
        kw.setdefault("clean", True)
        view = self.h.view(N, **kw)
        return self.tr.execute(view, to, self.h.ctx(N))

    def test_valid_path_to_done_with_integration(self):
        self.h.ready_for_review(N)
        self.assertTrue(self.go("In Progress", packet_valid=True, exclusive=True, worktree="/wt")["applied"])
        req = self.h.request_review(N)
        self.assertTrue(self.go("In Review")["applied"])
        self.assertIn("agent:review-requested", self.h.snap.issues[N].labels)
        self.h.review_result(N, req, "PASS")
        refused = self.go("Done")
        self.assertFalse(refused["applied"])
        self.assertIn("no integration evidence (merged PR)", refused["gate"]["reasons"])
        done = self.go("Done", integration=integration())
        self.assertTrue(done["applied"], done)
        self.assertEqual(self.h.snap.project.items[N].status, "Done")
        self.assertNotIn("agent:review-requested", self.h.snap.issues[N].labels)

    def test_review_rejection_returns_to_in_progress(self):
        self.h.ready_for_review(N)
        self.go("In Progress", packet_valid=True, exclusive=True, worktree="/wt")
        req = self.h.request_review(N)
        self.go("In Review")
        res = self.h.review_result(N, req, "REQUEST_CHANGES")
        self.assertFalse(self.go("Done", integration=integration())["applied"])
        self.assertFalse(self.go("In Progress")["applied"])  # needs the recorded change request
        self.h.publish("CHANGES_REQUESTED", N, finding_ids=["F-1"], causation_id=res["event_id"])
        back = self.go("In Progress")
        self.assertTrue(back["applied"], back)
        self.assertIn("agent:changes-requested", self.h.snap.issues[N].labels)

    def test_claim_gate_requires_records_lock_and_worktree(self):
        g = evaluate(self.h.view(N), "In Progress")
        self.assertFalse(g.passed)
        for reason in ("complete task packet", "exclusive coordinator claim", "CLAIMED", "DOCS_IMPACT", "PLAN", "worktree"):
            self.assertTrue(any(reason in r for r in g.reasons), reason)

    def test_disallowed_transition(self):
        self.assertFalse(evaluate(self.h.view(N), "Done").passed)
        self.assertIn("not permitted", evaluate(self.h.view(N), "Done").reasons[0])


class DoneGateTests(unittest.TestCase):
    """Nothing but a fresh PASS for the exact candidate, plus integration, reaches Done."""

    def setUp(self):
        self.h = Harness()
        self.h.ready_for_review(N)
        self.h.snap.project.items[N].status = "In Review"
        self.req = self.h.request_review(N)

    def tearDown(self):
        self.h.close()

    def gate(self, **kw):
        kw.setdefault("head", HEAD)
        kw.setdefault("integration", integration())
        return evaluate(self.h.view(N, **kw), "Done")

    def test_pass_for_exact_candidate_passes(self):
        self.h.review_result(N, self.req, "PASS")
        self.assertTrue(self.gate().passed, self.gate().reasons)

    def test_stale_head(self):
        self.h.review_result(N, self.req, "PASS")
        g = self.gate(head="d" * 40)
        self.assertFalse(g.passed)
        self.assertTrue(any("exact candidate head" in r for r in g.reasons))

    def test_changed_requirements(self):
        self.h.review_result(N, self.req, "PASS")
        self.h.snap.issues[N].body += "- [ ] A new criterion\n"
        self.assertTrue(any("requirements" in r for r in self.gate().reasons))

    def test_ticked_checkbox_is_not_a_requirement_change(self):
        before = requirements_digest(self.h.snap.issues[N])
        self.h.snap.issues[N].body = self.h.snap.issues[N].body.replace("- [ ] First", "- [x] First")
        self.assertEqual(requirements_digest(self.h.snap.issues[N]), before)

    def test_missing_review_result(self):
        self.assertIn("no independent review result for the exact candidate head", self.gate().reasons)

    def test_superseded_by_new_request(self):
        self.h.review_result(N, self.req, "PASS")
        self.h.request_review(N, rnd=2)
        self.assertTrue(any("supersedes" in r or "latest review request" in r for r in self.gate().reasons))

    def test_unresolved_findings_block(self):
        res = self.h.review_result(N, self.req, "PASS")
        self.h.publish("CHANGES_REQUESTED", N, finding_ids=["F-1", "F-2"], causation_id=res["event_id"])
        self.h.publish("FINDING_DISPOSITION", N, finding_id="F-1", disposition="fixed", evidence="commit abc")
        self.assertIn("findings without disposition: ['F-2']", self.gate().reasons)

    def test_maintainer_acceptance_needs_recorded_decision(self):
        res = self.h.review_result(N, self.req, "PASS")
        self.h.publish("CHANGES_REQUESTED", N, finding_ids=["F-1"], causation_id=res["event_id"])
        self.h.publish("FINDING_DISPOSITION", N, finding_id="F-1", disposition="accepted_by_maintainer", evidence="said so")
        self.assertTrue(any("without a recorded maintainer decision" in r for r in self.gate().reasons))

    def test_exhausted_review_budget(self):
        for rnd in (2, 3, 4):
            self.req = self.h.request_review(N, rnd=rnd)
        self.h.review_result(N, self.req, "PASS")
        self.assertTrue(any("budget exhausted" in r for r in self.gate().reasons))

    def second_attempt(self, rounds: int) -> dict:
        """Release attempt 1 (one round, from setUp), claim again and run `rounds` review rounds."""
        self.h.publish("RELEASED", N, reason="returned for rework")
        self.h.attempt = 2
        self.h.ready_for_review(N)
        for rnd in range(1, rounds + 1):
            self.req = self.h.request_review(N, rnd=rnd)
        return self.h.review_result(N, self.req, "PASS")

    def test_review_budget_counts_the_current_attempt_only(self):
        self.second_attempt(3)  # 1 + 3 rounds overall, 3 in the current attempt
        g = self.gate()
        self.assertTrue(g.passed, g.reasons)

    def test_review_budget_exhausted_within_the_current_attempt(self):
        self.second_attempt(4)
        self.assertIn("review budget exhausted (4 > 3 rounds); maintainer decision required", self.gate().reasons)

    def test_approved_but_unmerged_stays_in_review(self):
        self.h.review_result(N, self.req, "PASS")
        g = self.gate(integration=integration(merged=False))
        self.assertFalse(g.passed)
        self.assertTrue(any("agent:ready-to-merge" in r for r in g.reasons))

    def test_required_human_reviews_and_checks_cannot_be_bypassed(self):
        self.h.review_result(N, self.req, "PASS")
        self.assertIn("required human reviews not satisfied", self.gate(integration=integration(required_reviews_passed=False)).reasons)
        self.assertIn("required checks did not pass on the merged head", self.gate(integration=integration(checks_passed=False)).reasons)

    def test_merge_commit_match_alone_is_insufficient(self):
        self.h.review_result(N, self.req, "PASS")
        g = self.gate(integration=integration(tree_matches_candidate=False))
        self.assertIn("integrated tree differs from the reviewed candidate tree", g.reasons)
        g = self.gate(integration=integration(pr_head_sha="e" * 40))
        self.assertIn("merged PR head differs from the reviewed candidate", g.reasons)

    def test_decision_task_needs_maintainer_decision(self):
        h = Harness()
        try:
            h.ready_for_review(12)
            h.snap.project.items[12].status = "In Review"
            req = h.request_review(12)
            h.review_result(12, req, "PASS")
            g = evaluate(h.view(12, head=HEAD, integration=integration()), "Done")
            self.assertTrue(any("maintainer decision" in r for r in g.reasons))
        finally:
            h.close()


class InReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.h.snap.project.items[N].status = "In Progress"

    def tearDown(self):
        self.h.close()

    def test_failing_docs_audit_blocks_and_labels(self):
        self.h.ready_for_review(N)
        self.h.publish("DOCS_AUDIT_RESULT", N, head_sha=HEAD, result="FAIL", error_count=2, scope="change")
        self.h.request_review(N)
        tr = Transitioner(self.h.store, self.h.gh, self.h.publisher, self.h.snap.project, self.h.policy, dry_run=False)
        out = tr.execute(self.h.view(N, head=HEAD, clean=True), "In Review", self.h.ctx(N))
        self.assertFalse(out["applied"])
        self.assertTrue(out["gate"]["docs_stale"])
        self.assertIn("agent:docs-stale", self.h.snap.issues[N].labels)
        self.assertEqual(self.h.snap.project.items[N].status, "In Progress")

    def test_unmapped_criterion_and_dirty_tree_block(self):
        self.h.ready_for_review(N)
        self.h.request_review(N)
        self.h.snap.issues[N].body += "- [ ] Third criterion\n"
        g = evaluate(self.h.view(N, head=HEAD, clean=False), "In Review")
        self.assertIn("candidate worktree is not clean", g.reasons)
        self.assertTrue(any("requirements changed" in r for r in g.reasons))

    def test_missing_hooks_do_not_disable_gates(self):
        # Gates are evaluated by the controller alone; with no evidence at all nothing passes.
        g = evaluate(self.h.view(N, head=HEAD, clean=True), "In Review")
        self.assertFalse(g.passed)
        self.assertGreaterEqual(len(g.reasons), 5)


def fake_codex(tmp: Path, behaviour: str) -> str:
    """A stand-in `codex` executable for review adapter tests."""
    script = tmp / "codex"
    script.write_text(f"""#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli fake"); sys.exit(0)
out = args[args.index("-o") + 1]
prompt = sys.stdin.read()
packet = json.loads(prompt.split("Review packet (JSON):", 1)[1])
print(json.dumps({{"type": "thread.started", "thread_id": "fake-session"}}))
leak = [k for k in ("GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK") if k in os.environ]
behaviour = {behaviour!r}
if behaviour == "timeout":
    time.sleep(5)
if behaviour == "crash":
    sys.exit(3)
if behaviour == "silent":
    sys.exit(0)
if behaviour == "prose":
    open(out, "w").write("Looks good to me, pass!"); sys.exit(0)
result = {{"schema_version": 1, "run_id": packet["run_id"], "attempt": packet["attempt"],
          "request_id": packet["request_id"], "base_sha": packet["base_sha"], "head_sha": packet["head_sha"],
          "requirements_digest": packet["requirements_digest"], "verdict": "PASS",
          "criteria": [{{"id": c["id"], "status": "satisfied", "evidence": "ok"}}
                       for c in packet["acceptance_criteria"] + packet["documentation_criteria"]],
          "findings": [], "checks_run": [], "limitations": leak, "summary": "fine"}}
if behaviour == "wrong-head":
    result["head_sha"] = "f" * 40
if behaviour == "inconsistent":
    result["criteria"][0]["status"] = "not_satisfied"
open(out, "w").write(json.dumps(result))
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


class ReviewAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pol = policy()
        self.pol["review"]["timeout_seconds"] = 2
        self.packet = review.build_packet(
            run_id="run-test-0001", attempt=1, request_id="ev-request-0001", issue_url="u", milestone="M0",
            criteria=[{"id": "AC-1", "text": "x"}], requirements_digest="sha256:" + "0" * 64, base_sha=BASE,
            head_sha=HEAD, dependency_evidence=[], decisions=[], checks=[], ci_links=[], limitations=[],
            docs_impact=[], docs_changed=[], docs_audit={"result": "PASS"}, local_findings=[], review_round=1,
            previous_findings=[])
        self.request = {"run_id": "run-test-0001", "attempt": 1, "event_id": "ev-request-0001",
                        "head_sha": HEAD, "base_sha": BASE, "requirements_digest": "sha256:" + "0" * 64}

    def run_review(self, behaviour):
        os.environ["GH_TOKEN"] = "ghp_shouldnotleak"
        try:
            return review.run_codex(self.packet, self.tmp, self.tmp / "out", self.pol, codex=fake_codex(self.tmp, behaviour))
        finally:
            del os.environ["GH_TOKEN"]

    def accept(self, result, head=HEAD, base=BASE, req=None):
        return review.accept(result, request=self.request, current_head=head, current_base=base,
                             requirements_now=req or self.request["requirements_digest"],
                             criteria_ids=["AC-1"], doc_criteria_ids=["DOC-1", "DOC-2"])

    def test_valid_review_accepted_with_provenance_and_scrubbed_env(self):
        run = self.run_review("pass")
        self.assertEqual(run.provenance["session"], "fake-session")
        self.assertEqual(run.result["limitations"], [])  # no credential variables reached the reviewer
        self.assertEqual(self.accept(run.result)["verdict"], "PASS")

    def test_invalid_or_missing_output_is_not_a_verdict(self):
        for behaviour in ("crash", "silent", "prose", "timeout"):
            with self.subTest(behaviour=behaviour), self.assertRaises(review.ReviewRejected):
                self.run_review(behaviour)

    def test_identity_and_drift_mismatches_rejected(self):
        with self.assertRaises(review.ReviewRejected):
            self.accept(self.run_review("wrong-head").result)
        good = self.run_review("pass").result
        with self.assertRaises(review.ReviewRejected):
            self.accept(good, head="d" * 40)
        with self.assertRaises(review.ReviewRejected):
            self.accept(good, base="d" * 40)
        with self.assertRaises(review.ReviewRejected):
            self.accept(good, req="sha256:" + "9" * 64)

    def test_inconsistent_pass_rejected(self):
        with self.assertRaises(review.ReviewRejected):
            self.accept(self.run_review("inconsistent").result)

    def test_schema_violation_rejected(self):
        bad = dict(self.run_review("pass").result)
        bad["approved"] = True
        with self.assertRaises(review.ReviewRejected):
            self.accept(bad)


if __name__ == "__main__":
    unittest.main()
