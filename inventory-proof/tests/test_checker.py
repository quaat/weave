import hashlib
import unittest
from pathlib import Path

from checker import CheckError, check_flow, parse_net, prove
from verify_certificate import verify

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "Inventory.weave").read_text()
GOOD = (ROOT / "examples/checkout.weave").read_text()


class InventoryChecks(unittest.TestCase):
    def setUp(self):
        self.net = parse_net(SOURCE)

    def error(self, code, action):
        with self.assertRaises(CheckError) as raised:
            action()
        self.assertEqual(raised.exception.code, code, raised.exception.message)
        return raised.exception

    def test_symbolic_conservation_and_registration(self):
        result = prove(self.net)
        self.assertEqual(len(result["invariants"]), 2)
        self.assertEqual(result["invariants"][0]["initial_actual"], [1, 0])
        self.assertEqual(result["invariants"][1]["initial_actual"], [0, 0])
        for invariant in result["invariants"]:
            self.assertEqual(invariant["transition_residuals"], [0] * 21)

    def test_certificate_recheck(self):
        self.assertEqual(verify(SOURCE, prove(self.net)), 2)

    def test_recheck_rejects_changed_source(self):
        with self.assertRaises(ValueError):
            verify(SOURCE + "\n# change\n", prove(self.net))

    def test_recheck_rejects_tampered_matrix(self):
        certificate = prove(self.net)
        certificate["incidence"][0][0] += 1
        with self.assertRaises(ValueError):
            verify(SOURCE, certificate)

    def test_recheck_rejects_zero_weight_forgery(self):
        certificate = prove(self.net)
        certificate["invariants"][0]["weights"] = [0] * len(self.net.places)
        with self.assertRaises(ValueError):
            verify(SOURCE, certificate)

    def test_recheck_rejects_missing_invariant(self):
        certificate = prove(self.net)
        certificate["invariants"].pop()
        with self.assertRaises(ValueError):
            verify(SOURCE, certificate)

    def test_recheck_rejects_undeclared_invariant_quantity(self):
        certificate = prove(self.net)
        altered = SOURCE.replace("available + held + escrow +", "mystery + available + held + escrow +")
        certificate["source_sha256"] = hashlib.sha256(altered.encode()).hexdigest()
        certificate["invariants"][0]["expression"] = certificate["invariants"][0]["expression"].replace("available +", "mystery + available +", 1)
        with self.assertRaises(ValueError):
            verify(altered, certificate)

    def test_extra_stock_is_rejected(self):
        broken = SOURCE.replace("transition release:\n        take 1 unpaid\n        take 1 registrations\n        put 1 available", "transition release:\n        take 1 unpaid\n        take 1 registrations\n        put 2 available")
        error = self.error("E112", lambda: prove(parse_net(broken)))
        self.assertIn("release", error.message)
        self.assertIn("+1", error.message)

    def test_missing_registration_cleanup_is_rejected(self):
        broken = SOURCE.replace("transition cancel_unpaid:\n        take 1 unpaid\n        take 1 registrations", "transition cancel_unpaid:\n        take 1 unpaid")
        self.error("E100", lambda: parse_net(broken))
        # Updating the consumer declaration does not rescue broken accounting.
        broken = broken.replace(", cancel_unpaid\n", "\n")
        error = self.error("E112", lambda: prove(parse_net(broken)))
        self.assertIn("registration_balance", error.message)

    def test_creation_transition_is_rejected(self):
        broken = SOURCE + "\n    transition counterfeit:\n        put 1 available\n"
        self.error("E112", lambda: prove(parse_net(broken)))

    def test_bad_initial_marking_is_rejected(self):
        broken = SOURCE.replace("place sold = 0", "place sold = 1")
        self.error("E111", lambda: prove(parse_net(broken)))

    def test_nonlinear_invariant_is_rejected(self):
        broken = SOURCE.replace("available + held + escrow +", "available * held + escrow +")
        self.error("E110", lambda: prove(parse_net(broken)))

    def test_unrecognized_syntax_is_not_ignored(self):
        broken = SOURCE.replace("put 1 sold", "reset sold", 1)
        self.error("E003", lambda: parse_net(broken))

    def test_escrow_cannot_have_another_issuer(self):
        broken = SOURCE + "\n    transition forge:\n        take 1 held\n        put 1 escrow\n        put 1 registrations\n"
        self.error("E100", lambda: parse_net(broken))

    def test_issuing_escrow_requires_registration(self):
        broken = SOURCE.replace("        put 1 escrow\n        put 1 registrations", "        put 1 escrow")
        self.error("E100", lambda: parse_net(broken))

    def test_dispatch_requires_recovery_read(self):
        broken = SOURCE.replace("        read 1 registrations\n", "")
        self.error("E100", lambda: parse_net(broken))

    def test_cancel_cannot_wait_on_external_evidence(self):
        broken = SOURCE.replace("transition cancel_held:\n", "transition cancel_held:\n        guard external_reply\n")
        self.error("E100", lambda: parse_net(broken))

    def test_api_cannot_omit_consumed_resource(self):
        broken = SOURCE.replace("api arm(h: Hold[t, o]) -> Escrow[t, o]", "api arm(tenant: TenantId, order: OrderId) -> Escrow[tenant, order]")
        self.error("E100", lambda: parse_net(broken))

    def test_key_source_must_match_escrow_identity(self):
        broken = SOURCE.replace("keyed by tenant, order", "keyed by tenant, amount")
        self.error("E100", lambda: parse_net(broken))

    def test_foreign_outcomes_are_exhaustive(self):
        broken = SOURCE.replace("        outcome Unknown via charge_unknown\n", "")
        self.error("E100", lambda: parse_net(broken))

    def test_valid_checkout(self):
        self.assertEqual(check_flow(self.net, GOOD), ["checkout"])

    def test_direct_charge_missing_permit(self):
        bad = (ROOT / "examples/direct_charge.weave").read_text()
        self.error("E201", lambda: check_flow(self.net, bad))

    def test_sealed_constructor(self):
        bad = (ROOT / "examples/forge_escrow.weave").read_text()
        self.error("E205", lambda: check_flow(self.net, bad))

    def test_normal_drop_is_not_a_cancel(self):
        bad = (ROOT / "examples/drop_hold.weave").read_text()
        self.error("E204", lambda: check_flow(self.net, bad))

    def test_order_identity_must_match(self):
        bad = (ROOT / "examples/wrong_order.weave").read_text()
        self.error("E209", lambda: check_flow(self.net, bad))

    def test_tenant_identity_must_match(self):
        bad = GOOD.replace("amount: Money):", "amount: Money, other: TenantId):").replace("Payments.charge(tenant, order", "Payments.charge(other, order")
        self.error("E209", lambda: check_flow(self.net, bad))

    def test_handle_cannot_be_reused(self):
        bad = GOOD.replace("    let result =", "    let second = await Inventory.arm(hold)\n    let result =")
        e = self.error("E203", lambda: check_flow(self.net, bad))
        self.assertEqual([r.role for r in e.related], ["binding", "moved"])
        self.assertEqual([r.span.line for r in e.related], [GOOD.splitlines().index("    let hold = await Inventory.reserve(tenant, order)") + 1, e.line - 1])

    def test_paid_handle_cannot_be_released(self):
        bad = GOOD.replace("Inventory.sell(paid)", "Inventory.release(paid)")
        self.error("E208", lambda: check_flow(self.net, bad))

    def test_outcome_cannot_be_discarded(self):
        bad = GOOD.replace("let result = await Payments.charge", "await Payments.charge")
        self.error("E202", lambda: check_flow(self.net, bad))

    def test_missing_unknown_branch_is_rejected(self):
        bad = GOOD.split("        Unknown(uncertain):")[0]
        self.error("E214", lambda: check_flow(self.net, bad))

    def test_private_dispatch_cannot_be_called(self):
        bad = GOOD.replace("Payments.charge(tenant, order, amount, escrow)", "Inventory.dispatch(escrow)")
        self.error("E206", lambda: check_flow(self.net, bad))

    def test_no_open_union_types(self):
        bad = GOOD.replace("amount: Money", "amount: Money | Text")
        e = self.error("E002", lambda: check_flow(self.net, bad))
        # The type parser has no line of its own; the error is placed on the flow header.
        self.assertEqual(e.line, 1)
        self.assertEqual((e.span.line, e.span.column), (1, 1))

    def test_every_stock_place_is_bounded_by_stock(self):
        certificate = prove(self.net)
        vector = certificate["invariants"][0]["weights"]
        self.assertEqual(sum(vector), 10)
        self.assertTrue(all(weight in (0, 1) for weight in vector))
        # Nonnegative markings plus this equality give each included place <= stock.


if __name__ == "__main__":
    unittest.main()
