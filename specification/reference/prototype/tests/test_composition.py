import subprocess
import re
import sys
import tempfile
import unittest
from pathlib import Path

from checker import CheckError, check_flow, explore_order, parse_net, prove

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "Inventory.weave").read_text()
COMPOSED = (ROOT / "examples/checkout_composed.weave").read_text()


def authorize(source, transition, *places):
    for place in places:
        source = re.sub(rf"(    runtime_state {place} consumers [^\n]+)", rf"\g<1>, {transition}", source)
    return source


class CompositionChecks(unittest.TestCase):
    def setUp(self):
        self.net = parse_net(SOURCE)

    def error(self, code, action):
        with self.assertRaises(CheckError) as raised:
            action()
        self.assertEqual(raised.exception.code, code, raised.exception.message)
        return raised.exception

    def mutated(self, name):
        return SOURCE + "\n" + (ROOT / f"mutations/{name}.weave").read_text()

    def test_skim_cannot_steal_hold(self):
        e = self.error("E101", lambda: parse_net(self.mutated("skim")))
        self.assertIn("skim cannot consume sealed Hold", e.message)

    def test_lose_paid_cannot_steal_paid(self):
        self.error("E101", lambda: parse_net(self.mutated("lose_paid")))

    def test_bogus_sell_cannot_race_dispatch(self):
        e = self.error("E101", lambda: parse_net(self.mutated("bogus_sell")))
        self.assertIn("cancel_escrow, dispatch", e.message)

    def test_quick_recover_preserves_counts_but_violates_ordering(self):
        self.error("E101", lambda: parse_net(self.mutated("quick_recover")))
        net = parse_net(authorize(self.mutated("quick_recover"), "quick_recover", "recovery_queue", "registrations"))
        self.assertEqual(len(prove(net)["invariants"]), 2)
        e = self.error("E320", lambda: explore_order(net))
        self.assertIn("sold_requires_paid", e.message)
        self.assertIn("reserve -> arm -> dispatch -> cancel_inflight -> quick_recover", e.message)

    def test_exporting_bogus_sell_does_not_establish_safety(self):
        text = self.mutated("bogus_sell") + "\n    api bogus(h: Escrow[t, o]) -> Unit via bogus_sell\n"
        text = authorize(text, "bogus_sell", "registrations")
        net = parse_net(text)
        prove(net)
        e = self.error("E320", lambda: explore_order(net))
        self.assertIn("reserve -> arm -> bogus_sell", e.message)

    def test_private_read_cannot_borrow_linear_handle(self):
        text = SOURCE + "\n    transition peek:\n        read 1 held\n"
        self.error("E101", lambda: parse_net(text))

    def test_single_order_exhausts_graph_and_reaches_every_transition(self):
        result = explore_order(self.net)
        self.assertTrue(result["complete"])
        self.assertEqual(result["states"], 20)
        self.assertEqual(result["edges"], 43)
        self.assertEqual(set(result["fired_transitions"]), set(self.net.transitions))
        self.assertEqual(result["unreached_transitions"], [])
        self.assertTrue(all(p["premise_states"] > 0 for p in result["properties"]))

    def test_corrupt_declared_cancel_cannot_release_paid(self):
        net = parse_net(SOURCE.replace("transition cancel_paid:\n        take 1 paid\n        take 1 registrations\n        put 1 sold", "transition cancel_paid:\n        take 1 paid\n        take 1 registrations\n        put 1 available"))
        prove(net)
        e = self.error("E320", lambda: explore_order(net))
        self.assertIn("dispatched_release_requires_rejection", e.message)
        self.assertIn("charge_ok -> cancel_paid", e.message)

    def test_corrupt_declared_sell_cannot_release_paid(self):
        net = parse_net(SOURCE.replace("transition sell:\n        take 1 paid\n        take 1 registrations\n        put 1 sold", "transition sell:\n        take 1 paid\n        take 1 registrations\n        put 1 available"))
        prove(net)
        self.error("E320", lambda: explore_order(net))

    def test_missing_payment_guard_is_detected(self):
        net = parse_net(SOURCE.replace("        guard authoritative_paid_evidence\n", "", 1))
        prove(net)
        e = self.error("E320", lambda: explore_order(net))
        self.assertIn("paid_state_requires_paid", e.message)

    def test_missing_recovery_guard_is_detected(self):
        text = SOURCE.replace("put 1 sold\n        guard authoritative_paid_evidence", "put 1 sold")
        net = parse_net(text)
        prove(net)
        e = self.error("E320", lambda: explore_order(net))
        self.assertIn("recover_paid", e.message)

    def test_missing_manual_guard_is_detected(self):
        net = parse_net(SOURCE.replace("        guard operator_supplied_paid_evidence\n", ""))
        self.error("E320", lambda: explore_order(net))

    def test_evidence_guard_on_different_transition_is_insufficient(self):
        text = SOURCE.replace("        guard authoritative_paid_evidence\n", "", 1)
        text = text.replace("guard operation_is_dispatchable\n", "guard operation_is_dispatchable\n        guard authoritative_paid_evidence\n")
        net = parse_net(text)
        self.error("E320", lambda: explore_order(net))

    def test_guard_classification_is_explicit(self):
        text = SOURCE.replace("guard authoritative_paid_evidence\n", "guard mystery_evidence\n", 1)
        self.error("E300", lambda: parse_net(text))

    def test_bounded_search_never_silently_prunes(self):
        text = SOURCE.replace("take 1 charge_requests", "take 1 charge_requests\n        put 2 charge_requests")
        net = parse_net(text)
        prove(net)
        e = self.error("E321", lambda: explore_order(net))
        self.assertIn("place_bound=1 exceeded", e.message)

    def test_state_budget_is_not_a_success(self):
        e = self.error("E321", lambda: explore_order(self.net, max_states=1))
        self.assertIn("NOT ESTABLISHED", e.message)

    def test_read_arcs_participate_in_enabling(self):
        text = SOURCE + "\n    place absent = 0 owner runtime\n    transition impossible_sale:\n        read 1 absent\n        take 1 recovery_queue\n        take 1 registrations\n        put 1 sold\n"
        text += "    runtime_state absent terminal\n"
        text = authorize(text, "impossible_sale", "recovery_queue", "registrations")
        result = explore_order(parse_net(text))
        self.assertIn("impossible_sale", result["unreached_transitions"])

    def test_property_references_are_validated(self):
        self.error("E300", lambda: parse_net(SOURCE.replace("marked sold requires", "marked missing requires")))

    def test_duplicate_check_clause_is_rejected(self):
        self.error("E003", lambda: parse_net(SOURCE.replace("place_bound 1", "place_bound 1\n        place_bound 1")))

    def test_composed_checkout_moves_handles_and_outcomes(self):
        self.assertEqual(check_flow(self.net, COMPOSED), ["checkout_composed", "pay_with", "arm_hold", "settle"])

    def test_caller_cannot_reuse_transferred_hold(self):
        text = COMPOSED.replace("    await settle(result)", "    let stolen = await Inventory.arm(hold)\n    await settle(result)")
        self.error("E203", lambda: check_flow(self.net, text))

    def test_helper_cannot_drop_received_hold(self):
        text = "flow discard(hold: Hold[t, o]):\n    return\n"
        self.error("E204", lambda: check_flow(self.net, text))

    def test_helper_cannot_reuse_moved_hold(self):
        text = COMPOSED.replace("    return escrow", "    let other = await Inventory.arm(hold)\n    return escrow")
        self.error("E203", lambda: check_flow(self.net, text))

    def test_helper_wrong_identity_is_rejected(self):
        text = COMPOSED.replace("amount: Money):", "amount: Money, other: OrderId):", 1).replace("pay_with(tenant, order, amount, hold)", "pay_with(tenant, other, amount, hold)", 1)
        self.error("E209", lambda: check_flow(self.net, text))

    def test_helper_cannot_return_wrong_protocol_state(self):
        text = "flow wrong(hold: Hold[t, o]) -> Escrow[t, o]:\n    return hold\n"
        self.error("E217", lambda: check_flow(self.net, text))

    def test_return_preserves_symbolic_identity(self):
        text = "flow swapped(hold: Hold[t, o]) -> Hold[o, t]:\n    return hold\n"
        self.error("E217", lambda: check_flow(self.net, text))

    def test_returned_enum_cannot_be_discarded(self):
        text = COMPOSED.replace("let result = await pay_with", "await pay_with", 1)
        self.error("E202", lambda: check_flow(self.net, text))

    def test_return_does_not_hide_a_second_live_handle(self):
        text = "flow leak(a: Hold[t, o], b: Hold[u, v]) -> Hold[t, o]:\n    return a\n"
        self.error("E204", lambda: check_flow(self.net, text))

    def test_moved_handle_cannot_be_returned(self):
        text = "flow reuse(h: Hold[t, o]) -> Hold[t, o]:\n    let escrow = await Inventory.arm(h)\n    return h\n"
        self.error("E203", lambda: check_flow(self.net, text))

    def test_dropped_helper_result_is_rejected(self):
        text = COMPOSED.replace("let escrow = await arm_hold(hold)", "await arm_hold(hold)")
        self.error("E202", lambda: check_flow(self.net, text))

    def test_unknown_cannot_drop_at_helper_boundary(self):
        text = COMPOSED.replace("            await Inventory.handoff(uncertain)\n", "")
        self.error("E204", lambda: check_flow(self.net, text))

    def test_nonexhaustive_helper_match_is_rejected(self):
        text = COMPOSED.split("        Unknown(uncertain):")[0]
        self.error("E214", lambda: check_flow(self.net, text))

    def test_two_parameter_alias_is_rejected(self):
        text = "flow duplicate(hold: Hold[t, o]):\n    await consume(hold, hold)\n    return\n\nflow consume(a: Hold[t, o], b: Hold[t, o]):\n    return\n"
        self.error("E203", lambda: check_flow(self.net, text))

    def test_mutual_recursion_is_rejected(self):
        text = "flow a(h: Hold[t, o]) -> Hold[t, o]:\n    let x = await b(h)\n    return x\n\nflow b(h: Hold[t, o]) -> Hold[t, o]:\n    let x = await a(h)\n    return x\n"
        self.error("E218", lambda: check_flow(self.net, text))

    def test_unbound_result_index_is_rejected(self):
        text = "flow wrong(h: Hold[t, o]) -> Hold[t, missing]:\n    return h\n"
        self.error("E216", lambda: check_flow(self.net, text))

    def test_unused_helper_is_checked(self):
        text = COMPOSED + "\nflow unused(h: Paid[t, o]):\n    await Inventory.release(h)\n    return\n"
        self.error("E208", lambda: check_flow(self.net, text))

    def test_cli_composed_analysis_fails_before_success_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.weave"
            path.write_text(authorize(self.mutated("quick_recover"), "quick_recover", "recovery_queue", "registrations"))
            result = subprocess.run([sys.executable, str(ROOT / "checker.py"), "analyze", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("E320", result.stderr)

    def test_cli_checks_net_ordering_before_a_valid_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.weave"
            path.write_text(authorize(self.mutated("quick_recover"), "quick_recover", "recovery_queue", "registrations"))
            result = subprocess.run([sys.executable, str(ROOT / "checker.py"), "check", str(path), str(ROOT / "examples/checkout_composed.weave")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("E320", result.stderr)


if __name__ == "__main__":
    unittest.main()
