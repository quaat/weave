import unittest
from pathlib import Path

from checker import (CheckError, check_flow, explore_order, lower_flow_source,
                     parse_net, proof_text, prove)
from simulate import simulate
from test_composition import authorize

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "Inventory.weave").read_text()
FLOW = (ROOT / "examples/checkout_propagating.weave").read_text()


class RejectionAndPropagation(unittest.TestCase):
    def setUp(self):
        self.net = parse_net(SOURCE)

    def error(self, code, action):
        with self.assertRaises(CheckError) as raised:
            action()
        self.assertEqual(raised.exception.code, code, raised.exception.message)
        return raised.exception

    def mutation(self, name, authorized=False):
        source = SOURCE + "\n" + (ROOT / f"mutations/{name}.weave").read_text()
        if authorized:
            place = "inflight" if name == "leak" else "recovery_queue"
            source = authorize(source, name, place, "registrations")
        return source

    def test_inflight_theft_fails_structurally(self):
        e = self.error("E101", lambda: parse_net(self.mutation("leak")))
        self.assertIn("sealed runtime state inflight", e.message)

    def test_recovery_theft_fails_structurally(self):
        self.error("E101", lambda: parse_net(self.mutation("manual_leak")))

    def test_authorized_inflight_leak_fails_ordering(self):
        net = parse_net(self.mutation("leak", True))
        prove(net)
        e = self.error("E320", lambda: explore_order(net))
        self.assertIn("dispatched_release_requires_rejection", e.message)
        self.assertIn("reserve -> arm -> dispatch -> leak", e.message)
        self.assertIn("rejected_evidence=false", e.message)

    def test_authorized_recovery_leak_fails_ordering(self):
        net = parse_net(self.mutation("manual_leak", True))
        prove(net)
        e = self.error("E320", lambda: explore_order(net))
        self.assertIn("cancel_inflight -> manual_leak", e.message)

    def test_manual_state_is_sealed_too(self):
        source = self.mutation("manual_leak").replace("transition manual_leak:\n        take 1 recovery_queue", "transition manual_leak:\n        take 1 manual")
        self.error("E101", lambda: parse_net(source))
        source = authorize(source, "manual_leak", "manual", "registrations")
        self.error("E320", lambda: explore_order(parse_net(source)))

    def test_omitting_consumer_list_does_not_reopen_place(self):
        source = SOURCE.replace("    runtime_state inflight consumers charge_ok, charge_err, charge_unknown, cancel_inflight\n", "")
        self.error("E100", lambda: parse_net(source))

    def test_runtime_registration_itself_is_sealed(self):
        source = SOURCE + "\n    transition steal_registration:\n        take 1 registrations\n"
        self.error("E101", lambda: parse_net(source))

    def test_consumer_list_rejects_unknown_transition(self):
        self.error("E100", lambda: parse_net(authorize(SOURCE, "missing", "manual")))

    def test_consumer_list_rejects_nonconsumer(self):
        self.error("E100", lambda: parse_net(authorize(SOURCE, "reserve", "manual")))

    def test_consumer_list_rejects_duplicate(self):
        self.error("E100", lambda: parse_net(authorize(SOURCE, "charge_ok", "inflight")))

    def test_cannot_hide_dispatch_observation(self):
        self.error("E300", lambda: parse_net(SOURCE.replace("observe dispatch dispatch", "observe dispatch adapter_dequeue")))

    def test_missing_charge_rejection_guard_is_detected(self):
        source = SOURCE.replace("        guard authoritative_final_rejection\n", "", 1)
        e = self.error("E320", lambda: explore_order(parse_net(source)))
        self.assertIn("unpaid_state_requires_rejection", e.message)

    def test_missing_recovery_rejection_guard_is_detected(self):
        source = SOURCE.replace("put 1 available\n        guard authoritative_final_rejection", "put 1 available")
        self.error("E320", lambda: explore_order(parse_net(source)))

    def test_missing_manual_rejection_guard_is_detected(self):
        source = SOURCE.replace("        guard operator_supplied_final_rejection\n", "")
        self.error("E320", lambda: explore_order(parse_net(source)))

    def test_rejection_guard_on_other_transition_is_insufficient(self):
        source = SOURCE.replace("        guard authoritative_final_rejection\n", "", 1)
        source = source.replace("        guard operation_is_dispatchable\n", "        guard operation_is_dispatchable\n        guard authoritative_final_rejection\n")
        self.error("E320", lambda: explore_order(parse_net(source)))

    def test_paid_guard_cannot_authorize_error_outcome(self):
        source = SOURCE.replace("        guard authoritative_final_rejection\n", "        guard authoritative_paid_evidence\n", 1)
        self.error("E320", lambda: explore_order(parse_net(source)))

    def test_both_witnesses_do_not_erase_prior_paid_evidence(self):
        source = SOURCE.replace("        guard authoritative_final_rejection\n", "        guard authoritative_final_rejection\n        guard authoritative_paid_evidence\n", 1)
        e = self.error("E320", lambda: explore_order(parse_net(source)))
        self.assertIn("paid_never_available", e.message)
        self.assertIn("paid_evidence=true, rejected_evidence=true", e.message)

    def test_early_cancel_needs_no_rejection(self):
        result = explore_order(self.net)
        self.assertIn("cancel_held", result["fired_transitions"])
        self.assertIn("cancel_escrow", result["fired_transitions"])

    def test_escalation_budget_is_explicitly_unestablished(self):
        source = SOURCE.replace("        guard recovery_budget_exhausted\n", "")
        net = parse_net(source)
        explore_order(net)
        text = proof_text(net, prove(net))
        self.assertIn("escalation budgets", text)
        self.assertIn("provider truthfulness/consistency", text)

    def test_undeclared_fast_escalation_is_now_sealed(self):
        source = SOURCE + "\n    transition fast_escalate:\n        take 1 recovery_queue\n        put 1 manual\n"
        self.error("E101", lambda: parse_net(source))
        explore_order(parse_net(authorize(source, "fast_escalate", "recovery_queue")))

    def test_question_lowering_and_source_both_check(self):
        names = check_flow(self.net, FLOW)
        self.assertEqual(names, ["checkout_propagating", "place_order", "pay_with"])
        lowered = lower_flow_source(FLOW)
        self.assertNotIn("?", lowered)
        self.assertEqual(check_flow(self.net, lowered), names)
        self.assertEqual(lower_flow_source(lowered), lowered)

    def test_unknown_stays_registered_at_both_return_boundaries(self):
        run = simulate(self.net, FLOW, "checkout_propagating", "Unknown")
        returns = [e for e in run["events"] if e["kind"] == "RETURN" and e["tag"] == "Unknown"]
        self.assertEqual([e["name"] for e in returns], ["pay_with", "place_order"])
        for event in returns:
            self.assertEqual(event["marking"]["uncertain"], 1)
            self.assertEqual(event["marking"]["registrations"], 1)
            self.assertEqual(event["marking"]["available"], 0)
        self.assertEqual(run["marking"]["recovery_queue"], 1)
        self.assertEqual(run["marking"]["registrations"], 1)
        net_steps = [e["name"] for e in run["events"] if e["kind"] == "NET"]
        self.assertEqual(net_steps, ["reserve", "arm", "dispatch", "charge_unknown", "handoff"])

    def test_unhandled_unknown_return_preserves_registration(self):
        run = simulate(self.net, FLOW, "place_order", "Unknown")
        self.assertEqual(run["return_tag"], "Unknown")
        self.assertEqual(run["marking"]["uncertain"], 1)
        self.assertEqual(run["marking"]["registrations"], 1)

    def test_ok_commits_sale_and_closes_registration(self):
        run = simulate(self.net, FLOW, "checkout_propagating", "Ok")
        self.assertEqual(run["marking"]["sold"], 1)
        self.assertEqual(run["marking"]["registrations"], 0)
        self.assertEqual(run["marking"]["available"], 0)

    def test_error_releases_only_after_rejection(self):
        run = simulate(self.net, FLOW, "checkout_propagating", "Err")
        self.assertEqual(run["marking"]["available"], 1)
        self.assertEqual(run["marking"]["registrations"], 0)
        net_steps = [e["name"] for e in run["events"] if e["kind"] == "NET"]
        self.assertEqual(net_steps, ["reserve", "arm", "dispatch", "charge_err", "release"])

    def test_question_cannot_abandon_other_handle_on_early_return(self):
        source = FLOW.replace("    let paid = (await Payments.charge", "    let extra = await Inventory.reserve(tenant, order)\n    let paid = (await Payments.charge")
        # Consuming extra later on the success branch does not cover early exits.
        source = source.replace("    return Ok(paid)", "    let spare = await Inventory.arm(extra)\n    return Ok(paid)")
        e = self.error("E204", lambda: check_flow(self.net, source))
        self.assertTrue("spare" in e.message or "extra" in e.message)

    def test_question_residual_path_rejects_handle_even_if_success_handles_it(self):
        source = """flow leak(result: ChargeOutcome[t, o], extra: Paid[u, v]) -> ChargeOutcome[t, o]:
    let paid = result?
    await Inventory.sell(extra)
    return Ok(paid)
"""
        e = self.error("E204", lambda: check_flow(self.net, source))
        self.assertIn("extra", e.message)
        self.assertEqual(e.line, 2)
        # Primary span: the `?` statement; related spans: where `extra` was bound and the `?` itself.
        self.assertEqual((e.span.line, e.span.column, e.span.end_line, e.span.end_column), (2, 5, 2, 23))
        related = {(r.role, r.span.line, r.span.column, r.span.end_column) for r in e.related}
        self.assertEqual(related, {("binding", 1, 40, 45), ("propagation", 2, 22, 23)})
        self.assertEqual(e.details["outstanding"], [{"name": "extra", "type": "Paid[u, v]"}])

    def test_question_in_unit_flow_cannot_erase_unknown(self):
        source = "flow wrong(result: ChargeOutcome[t, o]):\n    let paid = result?\n    await Inventory.sell(paid)\n    return\n"
        self.error("E219", lambda: check_flow(self.net, source))

    def test_question_moves_its_operand(self):
        source = "flow wrong(result: ChargeOutcome[t, o]) -> ChargeOutcome[t, o]:\n    let paid = result?\n    return result\n"
        e = self.error("E203", lambda: check_flow(self.net, source))
        self.assertEqual((e.span.line, e.span.column, e.span.end_column), (3, 5, 18))
        related = [(r.role, r.span.line, r.span.column, r.span.end_column) for r in e.related]
        self.assertEqual(related, [("binding", 1, 12, 18), ("moved", 2, 16, 22)])

    def test_unknown_payload_identity_cannot_be_widened(self):
        source = FLOW.replace("-> CheckoutOutcome[tenant, order]", "-> CheckoutOutcome[order, tenant]")
        self.error("E217", lambda: check_flow(self.net, source))

    def test_question_residual_types_must_match(self):
        source = SOURCE.replace("enum CheckoutOutcome[t, o]:\n        Ok(Unit)\n        Err(Unpaid[t, o])\n        Unknown(Uncertain[t, o])", "enum CheckoutOutcome[t, o]:\n        Ok(Unit)\n        Err(Unpaid[t, o])\n        Unknown(Paid[t, o])")
        helpers = "flow place_order" + FLOW.split("flow place_order", 1)[1]
        self.error("E217", lambda: check_flow(parse_net(source), helpers))

    def test_unknown_cannot_be_constructed_without_payload(self):
        self.error("E217", lambda: check_flow(self.net, "flow fake(tenant: TenantId, order: OrderId) -> ChargeOutcome[tenant, order]:\n    return Unknown()\n"))

    def test_unknown_cannot_wrap_paid(self):
        self.error("E217", lambda: check_flow(self.net, "flow fake(paid: Paid[t, o]) -> ChargeOutcome[t, o]:\n    return Unknown(paid)\n"))

    def test_match_cannot_discard_linear_payload(self):
        source = FLOW.replace("Unknown(uncertain):", "Unknown():").replace("            await Inventory.handoff(uncertain)\n", "")
        self.error("E202", lambda: check_flow(self.net, source))

    def test_fresh_lowering_names_avoid_user_bindings(self):
        source = FLOW.replace("amount: Money", "_try_1: Money").replace(", amount", ", _try_1")
        check_flow(self.net, source)

    def test_question_inside_helper_cannot_hide_recursion(self):
        source = "flow recurse(result: ChargeOutcome[t, o]) -> ChargeOutcome[t, o]:\n    let paid = (await recurse(result))?\n    return Ok(paid)\n"
        self.error("E218", lambda: check_flow(self.net, source))


if __name__ == "__main__":
    unittest.main()
