# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Rule-level positive and negative cases against the pinned reference checker.

Each test names the rule IDs it exercises. ``tests/rule-coverage.json`` records
the mapping, and ``scripts/rule_coverage.py`` publishes it. The tests use the
unchanged prototype in ``reference/prototype/``; they observe its behaviour and
do not define Weave semantics. A test asserts a diagnostic code only where the
code's meaning in the diagnostics chapter describes the failure; otherwise it
asserts rejection alone.
"""
from pathlib import Path
import json
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "reference" / "prototype"))
from checker import CheckError, check_flow, explore_order, parse_net, prove  # noqa: E402
from coloured import parse_coloured  # noqa: E402

EXAMPLES = ROOT / "examples"
N0 = (EXAMPLES / "nets/Inventory.weave").read_text(encoding="utf-8")
N1 = (EXAMPLES / "nets/Inventory.coloured.weave").read_text(encoding="utf-8")
LEASE = (EXAMPLES / "nets/Lease.weave").read_text(encoding="utf-8")
CHECKOUT = (EXAMPLES / "valid/checkout.weave").read_text(encoding="utf-8")
N1_CHECK = re.search(r"    check payment_ordering for orders 2:\n(?:        .*\n)+", N1).group(0)
N0_CHECK = re.search(r"    check payment_ordering for one_order:\n(?:        .*\n)+", N0).group(0)


class RuleCases(unittest.TestCase):
    def setUp(self):
        self.net = parse_net(N0)

    def code(self, action):
        with self.assertRaises(CheckError) as raised:
            action()
        return raised.exception.code

    # CONF-CASE-1: the normative corpus, in both directions.
    def manifest_cases(self, accepted):
        manifest = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            if (case["expect"] == "ACCEPT") == accepted:
                yield case

    def run_case(self, case):
        source = (EXAMPLES / case["file"]).read_text(encoding="utf-8")
        try:
            if case["kind"] == "flow":
                check_flow(self.net, source)
            else:
                text = N0.rstrip() + "\n\n" + source if case["kind"] == "net_append" else source
                candidate = parse_net(text)
                prove(candidate)
                explore_order(candidate)
        except CheckError as error:
            return error.code
        return "ACCEPT"

    def test_conformance_accept_cases_are_accepted(self):
        cases = list(self.manifest_cases(True))
        self.assertTrue(cases)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(self.run_case(case), "ACCEPT")

    def test_conformance_reject_cases_report_required_code(self):
        cases = list(self.manifest_cases(False))
        self.assertTrue(cases)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(self.run_case(case), case["expect"])

    # Positive structure: N0-DECL-1..5, N0-SEAL-1, SYN-01, SYN-03..05, SYN-08, SYN-09.
    def test_reference_nets_are_accepted(self):
        prove(parse_net(N0))
        prove(parse_net(LEASE))
        parse_coloured(N1)

    # LEX-REQ-1
    def test_four_space_indentation_is_accepted(self):
        self.assertEqual(check_flow(self.net, CHECKOUT), ["checkout"])

    def test_tabs_are_rejected(self):
        self.assertEqual(self.code(lambda: check_flow(self.net, CHECKOUT.replace("    let hold", "\tlet hold", 1))), "E001")
        self.assertEqual(self.code(lambda: check_flow(self.net, "#\tcomment\n" + CHECKOUT)), "E001")

    def test_indentation_other_than_four_spaces_is_rejected(self):
        self.assertEqual(self.code(lambda: check_flow(self.net, CHECKOUT.replace("\n    let hold", "\n  let hold", 1))), "E001")

    # LEX-REQ-2
    def test_contextual_words_are_identifiers(self):
        self.assertIn("    transition dispatch:\n", N0)
        self.assertIn("        dispatch dispatch\n", N0)
        self.assertIn("dispatch", parse_net(N0).transitions)

    # SYN-01
    def test_net_file_with_two_nets_is_rejected(self):
        self.assertEqual(self.code(lambda: parse_net(N0 + "\n" + LEASE)), "E003")

    def test_flow_in_net_file_is_rejected(self):
        self.assertEqual(self.code(lambda: parse_net(N0 + "\nflow extra():\n    return\n")), "E003")

    # SYN-02
    def test_n0_net_without_check_block_is_accepted(self):
        self.assertNotIn("    check ", LEASE)
        prove(parse_net(LEASE))

    def test_ordering_without_check_block_is_not_established(self):
        self.assertEqual(self.code(lambda: explore_order(parse_net(LEASE))), "E300")

    def test_two_n0_check_blocks_are_rejected(self):
        second = N0_CHECK.replace("payment_ordering", "second_ordering")
        self.assertEqual(self.code(lambda: parse_net(N0.replace(N0_CHECK, N0_CHECK + "\n" + second))), "E300")

    def test_n1_needs_exactly_one_check_block(self):
        self.assertEqual(self.code(lambda: parse_coloured(N1.replace(N1_CHECK, ""))), "E400")
        second = N1_CHECK.replace("payment_ordering", "second_ordering")
        self.assertEqual(self.code(lambda: parse_coloured(N1.replace(N1_CHECK, N1_CHECK + "\n" + second))), "E400")

    # SYN-03
    def test_check_block_without_properties_is_rejected(self):
        self.assertEqual(self.code(lambda: parse_net(re.sub(r"        property .*\n", "", N0))), "E300")

    def test_n1_check_block_without_token_correlation_is_rejected(self):
        text = N1.replace("        property token_identity: tokens match firing\n", "")
        self.assertEqual(self.code(lambda: parse_coloured(text)), "E400")

    # SYN-04
    def test_duplicate_net_names_are_rejected(self):
        place = "    place leased = 0 owner activation\n"
        self.assertEqual(self.code(lambda: parse_net(LEASE.replace(place, place + place))), "E003")
        extra = "    transition acquire:\n        take 1 free\n        put 1 leased\n"
        self.assertEqual(self.code(lambda: parse_net(LEASE + extra)), "E003")

    def test_net_without_invariants_is_rejected(self):
        text = LEASE.replace("    invariant slot:\n        free + leased == 1\n", "")
        self.assertEqual(self.code(lambda: parse_net(text)), "E100")

    def test_n1_transition_without_colour_is_rejected(self):
        text = N1.rstrip() + "\n    transition idle:\n        take 1 available\n        put 1 available\n"
        self.assertEqual(self.code(lambda: parse_coloured(text)), "E400")

    # SYN-05
    def test_nonpositive_arc_count_is_rejected(self):
        text = LEASE.replace("transition release:\n        take 1 leased", "transition release:\n        take 0 leased")
        self.assertEqual(self.code(lambda: parse_net(text)), "E003")

    def test_duplicate_arc_is_rejected(self):
        text = LEASE.replace("transition release:\n        take 1 leased", "transition release:\n        take 1 leased\n        take 1 leased")
        self.assertEqual(self.code(lambda: parse_net(text)), "E003")

    def test_negative_initial_count_is_rejected(self):
        self.assertEqual(self.code(lambda: parse_net(LEASE.replace("place free = 1", "place free = -1"))), "E003")

    # SYN-06
    def test_indexed_or_unit_scalar_parameter_is_rejected(self):
        indexed = CHECKOUT.replace("amount: Money)", "amount: Money[tenant])")
        unit = CHECKOUT.replace("amount: Money)", "amount: Money, nothing: Unit)")
        self.assertEqual(self.code(lambda: check_flow(self.net, indexed)), "E216")
        self.assertEqual(self.code(lambda: check_flow(self.net, unit)), "E216")

    # SYN-08
    def test_activation_place_without_resource_is_rejected(self):
        place = "    place leased = 0 owner activation\n"
        text = LEASE.replace(place, place + "    place spare = 0 owner activation\n")
        self.assertEqual(self.code(lambda: parse_net(text)), "E100")

    # SYN-09
    def test_duplicate_foreign_clause_is_rejected(self):
        text = N0.replace("        dispatch dispatch\n", "        dispatch dispatch\n        dispatch dispatch\n")
        self.assertEqual(self.code(lambda: parse_net(text)), "E003")

    # N0-DECL-2
    def test_cancellation_cannot_read(self):
        text = N0.replace("transition cancel_held:\n", "transition cancel_held:\n        read 1 registrations\n")
        self.assertEqual(self.code(lambda: parse_net(text)), "E100")

    # SYN-10
    def test_return_identifier_is_a_binding_not_a_constructor(self):
        source = "flow f(tenant: TenantId, order: OrderId) -> CheckoutOutcome[tenant, order]:\n    return Ok\n"
        self.assertEqual(self.code(lambda: check_flow(self.net, source)), "E207")

    # SYN-11
    def test_duplicate_enum_case_is_rejected(self):
        case = "        Unknown(Uncertain[t, o])\n"
        self.assertEqual(self.code(lambda: parse_net(N0.replace(case, case + case, 1))), "E003")

    def test_duplicate_match_tag_is_rejected(self):
        branch = "        Unknown(uncertain):\n            await Inventory.handoff(uncertain)\n            return\n"
        extra = "        Unknown(again):\n            await Inventory.handoff(again)\n            return\n"
        # The reference checker reports E003 here; the diagnostics chapter gives E003
        # for net declarations and E214 for extra match cases (quaat/weave#76), so only
        # rejection is asserted.
        self.code(lambda: check_flow(self.net, CHECKOUT.replace(branch, branch + extra)))

    # SYN-12 and F0-BIND-1
    def test_statement_after_return_is_rejected(self):
        source = "flow f(hold: Hold[t, o]) -> Hold[t, o]:\n    return hold\n    return hold\n"
        self.assertEqual(self.code(lambda: check_flow(self.net, source)), "E210")

    def test_statement_after_terminal_match_is_rejected(self):
        self.assertEqual(self.code(lambda: check_flow(self.net, CHECKOUT + "    return\n")), "E213")

    def test_path_without_termination_is_rejected(self):
        source = "flow f(unpaid: Unpaid[t, o]):\n    await Inventory.release(unpaid)\n"
        self.assertEqual(self.code(lambda: check_flow(self.net, source)), "E215")
        self.assertEqual(check_flow(self.net, source + "    return\n"), ["f"])

    def test_shadowing_is_rejected(self):
        source = "flow f(tenant: TenantId, order: OrderId):\n    let tenant = await Inventory.reserve(tenant, order)\n    return\n"
        self.assertEqual(self.code(lambda: check_flow(self.net, source)), "E211")

    # SYN-13
    def test_invariant_with_undeclared_name_is_rejected(self):
        text = LEASE.replace("free + leased == 1", "free + leased + ghost == 1")
        self.assertEqual(self.code(lambda: prove(parse_net(text))), "E110")

    # SYN-14
    def test_operation_without_await_is_rejected(self):
        source = CHECKOUT.replace("let hold = await Inventory.reserve", "let hold = Inventory.reserve")
        self.assertEqual(self.code(lambda: check_flow(self.net, source)), "E212")


if __name__ == "__main__":
    unittest.main()
