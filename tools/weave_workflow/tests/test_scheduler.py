"""Scenarios 1 and 2: ordering, dependencies, predecessors, exceptions, exit gates, eligibility."""
import unittest

from tools.weave_workflow.model import milestone_key, milestone_order
from tools.weave_workflow.scheduler import build_graph, milestone_gate, plan

from .support import mini_policy, mini_snapshot


def complete(snap, *numbers):
    for n in numbers:
        snap.issues[n].state, snap.issues[n].state_reason = "closed", "completed"
        if snap.project:
            snap.project.items[n].status = "Done"


GATE = lambda key: {"kind": "GATE_EVALUATED", "gate": f"milestone-exit:{key}", "result": "PASS"}  # noqa: E731


class OrderingTests(unittest.TestCase):
    def test_numeric_milestone_order(self):
        keys = sorted(["M10", "M2", "M1", "M0"], key=milestone_order)
        self.assertEqual(keys, ["M0", "M1", "M2", "M10"])
        self.assertEqual(milestone_key("M10 Composition"), "M10")
        self.assertIsNone(milestone_key("Backlog"))

    def test_lowest_unfinished_milestone_and_documented_sequence(self):
        p = plan(mini_snapshot(), mini_policy())
        self.assertEqual(p.current, "M0")
        # The epic lists #11 before #10; #12 is a decision task but still eligible for preparation.
        self.assertEqual(p.next.issue, 11)
        self.assertEqual([c.issue for c in sorted(p.candidates, key=lambda c: c.sequence) if c.eligible][:3], [11, 10, 12])
        self.assertEqual(next(c for c in p.candidates if c.issue == 12).work_type, "decision-preparation")

    def test_issue_number_is_final_tie_breaker(self):
        snap = mini_snapshot()
        snap.issues[100].body = "Depends on: Start\n\n## Work items\n"
        self.assertEqual(plan(snap, mini_policy()).next.issue, 10)


class DependencyTests(unittest.TestCase):
    def test_prose_dependency_has_provenance_and_bare_mentions_do_not_block(self):
        snap = mini_snapshot()
        snap.issues[20].body += "\nSee also #10 for context.\n"
        g = build_graph(snap, mini_policy())
        self.assertIn((21, 20), g.edges)
        self.assertIn("Depends on", g.edges[(21, 20)].provenance[0])
        self.assertNotIn((20, 10), g.edges)
        self.assertIn(10, g.contextual[20])

    def test_cycle_detected_and_tasks_ineligible(self):
        snap = mini_snapshot()
        snap.issues[10].blocked_by = [11]
        snap.issues[11].blocked_by = [10]
        p = plan(snap, mini_policy())
        self.assertTrue(any("cycle" in f for f in p.graph.findings))
        for n in (10, 11):
            c = next(c for c in p.candidates if c.issue == n)
            self.assertFalse(c.eligible)
            self.assertIn("participates in a dependency cycle", c.reasons)
        self.assertEqual(p.next.issue, 12)  # an independent task is not blocked

    def test_contradictory_dependency_on_later_milestone(self):
        snap = mini_snapshot()
        snap.issues[10].blocked_by = [30]
        p = plan(snap, mini_policy())
        self.assertTrue(any("contradictory" in f for f in p.graph.findings))
        self.assertFalse(next(c for c in p.candidates if c.issue == 10).eligible)

    def test_closed_as_not_planned_prerequisite_blocks(self):
        snap, pol = mini_snapshot(), mini_policy()
        complete(snap, 10, 11, 12, 100)
        p0 = plan(snap, pol, [GATE("M0")])
        self.assertEqual(p0.current, "M1")
        snap.issues[20].state, snap.issues[20].state_reason = "closed", "not_planned"
        c = next(c for c in plan(snap, pol, [GATE("M0")]).candidates if c.issue == 21)
        self.assertFalse(c.eligible)
        self.assertTrue(any("closed as not planned" in r for r in c.reasons))

    def test_epic_prose_disagreeing_with_policy_is_reported(self):
        snap = mini_snapshot()
        snap.issues[101].body = snap.issues[101].body.replace("Depends on: M0", "Depends on: M0 and M10")
        self.assertTrue(any("epic states predecessors" in f for f in build_graph(snap, mini_policy()).findings))


class GateTests(unittest.TestCase):
    def test_closed_milestone_object_is_not_a_passed_gate(self):
        snap, pol = mini_snapshot(), mini_policy()
        snap.milestones[0].state = "closed"
        p = plan(snap, pol)
        self.assertEqual(p.current, "M0")
        self.assertFalse(any(c.issue in (20, 21) for c in p.candidates))

    def test_exit_gate_requires_tasks_epic_and_recorded_evaluation(self):
        snap, pol = mini_snapshot(), mini_policy()
        complete(snap, 10, 11, 12)
        g = milestone_gate(snap, pol, "M0", [])
        self.assertFalse(g.passed)
        self.assertTrue(any("epic #100" in r for r in g.reasons))
        complete(snap, 100)
        self.assertFalse(milestone_gate(snap, pol, "M0", []).passed)
        self.assertTrue(milestone_gate(snap, pol, "M0", [GATE("M0")]).passed)

    def test_closed_but_not_done_on_board_fails_gate(self):
        snap, pol = mini_snapshot(), mini_policy()
        complete(snap, 10, 11, 12, 100)
        snap.project.items[11].status = "In Review"
        g = milestone_gate(snap, pol, "M0", [GATE("M0")])
        self.assertFalse(g.passed)
        self.assertTrue(any("#11 closed but board status" in r for r in g.reasons))

    def test_not_planned_task_fails_gate(self):
        snap, pol = mini_snapshot(), mini_policy()
        complete(snap, 10, 12, 100)
        snap.issues[11].state, snap.issues[11].state_reason = "closed", "not_planned"
        self.assertTrue(any("not planned" in r for r in milestone_gate(snap, pol, "M0", [GATE("M0")]).reasons))

    def test_cross_milestone_requirement_scheduled_once_and_gates_later_milestone(self):
        snap, pol = mini_snapshot(), mini_policy()
        complete(snap, 10, 11, 12, 100)
        p = plan(snap, pol, [GATE("M0")])
        self.assertEqual([c.issue for c in p.candidates if c.issue == 21], [21])
        complete(snap, 20, 30, 31, 101, 110)
        gate = milestone_gate(snap, pol, "M10", [GATE("M10")])
        self.assertFalse(gate.passed)
        self.assertTrue(any("#21" in r for r in gate.reasons))


class EligibilityTests(unittest.TestCase):
    def test_missing_milestone_is_unscheduled_and_deferred_excluded(self):
        p = plan(mini_snapshot(), mini_policy())
        self.assertEqual(p.unscheduled, [40])
        self.assertEqual(p.deferred, [41])
        self.assertFalse(any(c.issue in (40, 41) for c in p.candidates))

    def test_missing_criteria_is_ineligible(self):
        snap = mini_snapshot()
        snap.issues[11].body = "## Scope\nSomething vague.\n"
        c = next(c for c in plan(snap, mini_policy()).candidates if c.issue == 11)
        self.assertFalse(c.eligible)
        self.assertIn("no actionable acceptance criteria", c.reasons)

    def test_epics_are_not_tasks(self):
        self.assertFalse(any(c.issue == 100 for c in plan(mini_snapshot(), mini_policy()).candidates))

    def test_labels_and_board_status_exclude(self):
        snap = mini_snapshot()
        snap.issues[11].labels.append("agent:needs-human")
        snap.project.items[10].status = "In Review"
        p = plan(snap, mini_policy())
        self.assertEqual(p.next.issue, 12)

    def test_active_slot_must_be_resumed_first(self):
        snap = mini_snapshot()
        snap.project.items[10].status = "In Progress"
        p = plan(snap, mini_policy())
        self.assertIsNone(p.next)
        self.assertIn("resume it", p.stop_reason)

    def test_nothing_eligible_stops_cleanly(self):
        snap = mini_snapshot()
        for n in (10, 11, 12):
            snap.issues[n].labels.append("agent:blocked")
        p = plan(snap, mini_policy())
        self.assertIsNone(p.next)
        self.assertIn("no eligible task in M0", p.stop_reason)

    def test_unreadable_board_makes_selection_provisional(self):
        p = plan(mini_snapshot(with_project=False), mini_policy())
        self.assertIsNone(p.next)
        self.assertEqual(p.provisional_next.issue, 11)
        self.assertIn("project board unreadable", p.stop_reason)


class EarlyStartTests(unittest.TestCase):
    def test_exception_inactive_by_default(self):
        c = next(c for c in plan(mini_snapshot(), mini_policy()).candidates if c.issue == 31)
        self.assertFalse(c.eligible)
        self.assertIn("inactive", c.reasons[0])

    def test_active_exception_is_narrow_and_waives_nothing(self):
        pol = mini_policy()
        pol["early_start_exceptions_active"] = True
        p = plan(mini_snapshot(), pol)
        c = next(c for c in p.candidates if c.issue == 31)
        self.assertTrue(c.eligible)
        self.assertIn("no dependency or exit gate is waived", c.notes[0])
        self.assertEqual(p.next.issue, 11)  # in-milestone work still comes first
        self.assertFalse(any(c.issue == 30 for c in p.candidates))


if __name__ == "__main__":
    unittest.main()
