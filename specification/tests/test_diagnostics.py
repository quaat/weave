# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Diagnostic codes, their rules and source spans (quaat/weave#6).

* Every code the pinned prototype, the P0 implementations (quaat/weave#10) or
  the agent kit can emit is in ``diagnostics.json``; the codes are derived from
  the sources, and a test shows that an unmapped code fails.
* One fixture per specification code checks the code, its principal rule and
  its primary span (P0 codes through the P0 reference evaluator; modules-1 codes
  through the modules corpus, ``tests/test_modules.py`` and
  ``scripts/modules_conformance.py``); E203 and E204 also check their related spans. Each
  diagnostic is validated against the ``weave-diagnostic-v1`` schema with the
  repository's evidence reader (standard library only).
* The ``weave-check`` directive's helper returns the same documents.
"""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "reference" / "prototype"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(REPO))
from checker import CheckError, check_flow, explore_order, parse_net, prove  # noqa: E402
from coloured import Unfolding, explore_colours, parse_coloured, prove_colours  # noqa: E402
from diagnostic_map import (MODULES_RUNNER, P0_REFERENCE, PROTOTYPE, emitted_codes, kit_sources,  # noqa: E402
                            load_map, rust_codes, unmapped)
import p0_reference  # noqa: E402
from refresh_reference_pages import check_diagnostic_map  # noqa: E402
from spec_checks import as_diagnostic, check_example_diagnostic  # noqa: E402
from evidence.weave_evidence.documents import assess  # noqa: E402

EXAMPLES = ROOT / "examples"
N0 = (EXAMPLES / "nets/Inventory.weave").read_text(encoding="utf-8")
N1 = (EXAMPLES / "nets/Inventory.coloured.weave").read_text(encoding="utf-8")
MAP = load_map()
RULES = json.loads((ROOT / "rules.json").read_text(encoding="utf-8"))


def flow(source):
    return "flow", source, lambda: check_flow(parse_net(N0), source)


def net(source, max_states=10000):
    def run():
        candidate = parse_net(source)
        prove(candidate)
        explore_order(candidate, max_states)
    return "net", source, run


def coloured(source, action="prove"):
    def run():
        candidate = parse_coloured(source)
        prove_colours(candidate) if action == "prove" else explore_colours(candidate, **({"max_states": 1} if action == "budget" else {}))
    return "net", source, run


def disabled_firing():
    candidate = parse_coloured(N1)
    unfolding = Unfolding(candidate)
    reserve = unfolding.select("reserve", unfolding.colours[0])
    marking = unfolding.fire(unfolding.initial, reserve)
    return "net", N1, lambda: unfolding.fire(marking, reserve)


def replace(text, old, new):
    assert old in text, old
    return text.replace(old, new, 1)


CROSS_SELL = replace(N1, "transition sell[t, o]:\n        take 1 paid[t, o]\n        take 1 registrations[t, o]",
                     "transition sell[t, o]:\n        take 1 paid[t, o]\n        take 1 registrations[t, other]")
DUPLICATE_TAG = """flow f(result: ChargeOutcome[t, o]):
    match result:
        Ok(paid):
            await Inventory.sell(paid)
            return
        Ok(again):
            return
        Err(unpaid):
            await Inventory.release(unpaid)
            return
        Unknown(uncertain):
            await Inventory.handoff(uncertain)
            return
"""

# code: (fixture, principal rule, (line, exact text of the primary span),
#        {role: (line, text)} for the related spans of ownership codes)
FIXTURES = {
    "E001": (flow("flow f():\n\treturn\n"), "LEX-REQ-1", (2, "return"), None),
    "E002": (flow("flow f(amount: Money | Text):\n    return\n"), "SYN-07", (1, "flow f(amount: Money | Text):"), None),
    "E003": (flow(DUPLICATE_TAG), "SYN-04", (6, "Ok(again):"), None),
    "E100": (net(replace(N0, "linear Paid[t, o] at paid issuer charge_ok", "linear Paid[t, o] at paid issuer charge_err")),
             "SYN-08", (21, "linear Paid[t, o] at paid issuer charge_err cancel cancel_paid"), None),
    "E101": (net(N0.rstrip() + "\n\n    transition steal:\n        take 1 held\n        put 1 sold\n"),
             "N0-SEAL-1", (len(N0.rstrip().splitlines()) + 2, "transition steal:"), None),
    "E110": (net(replace(N0, "registrations - escrow - inflight", "registrations * escrow - inflight")),
             "SYN-13", (44, "registrations * escrow - inflight - paid - unpaid - uncertain - recovery_queue - manual == 0"), None),
    "E111": (net(replace(N0, "recovery_queue + manual + sold == stock", "recovery_queue + manual + sold == stock + 1")),
             "SYN-13", (41, "available + held + escrow + inflight + paid + unpaid + uncertain + recovery_queue + manual + sold == stock + 1"), None),
    "E112": (net(replace(N0, "take 1 unpaid\n        take 1 registrations\n        put 1 available",
                         "take 1 unpaid\n        take 1 registrations\n        put 2 available")),
             "SYN-13", (41, "available + held + escrow + inflight + paid + unpaid + uncertain + recovery_queue + manual + sold == stock"), None),
    "E200": (flow("flow f():\n    if ready:\n        return\n"), "CONF-REQ-1", (2, "if ready:"), None),
    "E201": (flow("flow f(tenant: TenantId, order: OrderId):\n    let hold = await Inventory.reserve(tenant)\n    return\n"),
             "F0-CALL-1", (2, "let hold = await Inventory.reserve(tenant)"), None),
    "E202": (flow("flow f(tenant: TenantId, order: OrderId):\n    await Inventory.reserve(tenant, order)\n    return\n"),
             "F0-UNITCALL-1", (2, "await Inventory.reserve(tenant, order)"), None),
    "E203": (flow("flow f(hold: Hold[t, o]):\n    let a = await Inventory.arm(hold)\n    let b = await Inventory.arm(hold)\n    return\n"),
             "F0-CALL-2", (3, "let b = await Inventory.arm(hold)"), {"binding": (1, "hold"), "moved": (2, "hold")}),
    "E204": (flow("flow f(result: ChargeOutcome[t, o], extra: Paid[u, v]) -> ChargeOutcome[t, o]:\n"
                  "    let paid = result?\n    await Inventory.sell(extra)\n    return Ok(paid)\n"),
             "F0-RETURN-1", (2, "let paid = result?"), {"binding": (1, "extra"), "propagation": (2, "?")}),
    "E205": (flow("flow f(tenant: TenantId, order: OrderId):\n    let hold = Hold(tenant, order)\n    return\n"),
             "F0-CALL-1", (2, "let hold = Hold(tenant, order)"), None),
    "E206": (flow("flow f(escrow: Escrow[t, o]):\n    let x = await Inventory.dispatch(escrow)\n    return\n"),
             "F0-CALL-1", (2, "let x = await Inventory.dispatch(escrow)"), None),
    "E207": (flow("flow f():\n    let hold = await Inventory.reserve(tenant, order)\n    return\n"),
             "F0-CALL-1", (2, "let hold = await Inventory.reserve(tenant, order)"), None),
    "E208": (flow("flow f(hold: Hold[t, o]):\n    await Inventory.sell(hold)\n    return\n"),
             "F0-CALL-2", (2, "await Inventory.sell(hold)"), None),
    "E209": (flow("flow f(tenant: TenantId, order: OrderId, other: OrderId, amount: Money, escrow: Escrow[tenant, other]):\n"
                  "    let r = await Payments.charge(tenant, order, amount, escrow)\n    return\n"),
             "F0-CALL-2", (2, "let r = await Payments.charge(tenant, order, amount, escrow)"), None),
    "E210": (flow("flow f():\n    return\n    return\n"), "SYN-12", (2, "return"), None),
    "E211": (flow("flow f(hold: Hold[t, o]):\n    let hold = await Inventory.arm(hold)\n    return\n"),
             "F0-BIND-1", (2, "let hold = await Inventory.arm(hold)"), None),
    "E212": (flow("flow f(hold: Hold[t, o]):\n    let escrow = Inventory.arm(hold)\n    return\n"),
             "SYN-14", (2, "let escrow = Inventory.arm(hold)"), None),
    "E213": (flow("flow f(hold: Hold[t, o]):\n    match hold:\n        Ok(x):\n            return\n"),
             "F0-MATCH-1", (2, "match hold:"), None),
    "E214": (flow("flow f(result: ChargeOutcome[t, o]):\n    match result:\n        Ok(paid):\n"
                  "            await Inventory.sell(paid)\n            return\n"),
             "F0-MATCH-1", (2, "match result:"), None),
    "E215": (flow("flow f(hold: Hold[t, o]):\n    let escrow = await Inventory.arm(hold)\n"),
             "SYN-12", (2, "let escrow = await Inventory.arm(hold)"), None),
    "E216": (flow("flow f(hold: Hold[t]):\n    return\n"), "F0-SIGNATURE-1", (1, "flow f(hold: Hold[t]):"), None),
    "E217": (flow("flow f(hold: Hold[t, o]) -> Escrow[t, o]:\n    return hold\n"), "SYN-10", (2, "return hold"), None),
    "E218": (flow("flow a():\n    await b()\n    return\nflow b():\n    await a()\n    return\n"),
             "F0-SIGNATURE-1", (1, "flow a():"), None),
    "E219": (flow("flow f(paid: Paid[t, o]) -> CheckoutOutcome[t, o]:\n    return Maybe(paid)\n"),
             "F0-TAGRETURN-1", (2, "return Maybe(paid)"), None),
    "E300": (net(replace(N0, "        place_bound 1\n", "")), "SYN-03", (46, "check payment_ordering for one_order:"), None),
    "E320": (net((EXAMPLES / "nets/unsafe_paid_release.weave").read_text(encoding="utf-8")),
             "N0-ORDER-1", (46, "check payment_ordering for one_order:"), None),
    "E321": (net(N0, max_states=1), "N0-ORDER-1", (46, "check payment_ordering for one_order:"), None),
    "E400": (coloured(replace(N1, "read 1 registrations[t, o]", "read 1 registrations")),
             "N1-COLOUR-1", (99, "transition dispatch[t, o]:"), None),
    "E411": (coloured(replace(N1, "registrations[t, o] - escrow[t, o]", "registrations[t, o] + registrations - escrow[t, o]")),
             "N1-FAMILY-1", (59, "invariant registration_balance[t, o]:"), None),
    "E412": (coloured(CROSS_SELL), "N1-FAMILY-2", (124, "transition sell[t, o]:"), None),
    "E420": (coloured((EXAMPLES / "nets/cross_order_read.weave").read_text(encoding="utf-8"), "explore"),
             "N1-ORDER-1", (99, "transition dispatch[t, o]:"), None),
    "E421": (disabled_firing(), "N1-FIRE-1", (87, "transition reserve[t, o]:"), None),
    "E422": (coloured(N1, "budget"), "N1-ORDER-1", (65, "check payment_ordering for orders 2:"), None),
}


# P0 code: (source, run request or None, principal rule, (line, exact text of the primary span)).
# A run request is (entry, args, budgets).
P0_BUDGETS = (EXAMPLES / "pure/valid/budgets.weave").read_text(encoding="utf-8")
P0_FIXTURES = {
    "E500": ("fn f(x: Int) -> Bool:\n    return 0 < x < 3\n", None, "P0-FILE-1", (2, "<")),
    "E501": ("fn f() -> Int:\n    return 1\n\nfn f() -> Int:\n    return 2\n", None, "P0-DECL-1", (4, "f")),
    "E502": ("record R:\n    a: Int\n    a: Bool\n", None, "P0-DECL-2", (3, "a")),
    "E503": ("record T:\n    kids: List[T]\n", None, "P0-DECL-3", (1, "T")),
    "E504": ("fn peek(hold: Hold[t, o]) -> Int:\n    return 0\n", None, "P0-TYPE-1", (1, "Hold[t, o]")),
    "E505": ("fn f(x: Int) -> Int:\n    return y + x\n", None, "P0-NAME-1", (2, "y")),
    "E506": ("fn f(x: Int) -> Int:\n    let x = 1\n    return x\n", None, "P0-NAME-2", (2, "x")),
    "E507": ("fn f(x: Int) -> Int:\n    return f(x, x)\n", None, "P0-CALL-1", (2, "f(x, x)")),
    "E508": ("record R:\n    a: Int\n    b: Int\n\nfn f(x: Int) -> R:\n    return R(a: x)\n", None, "P0-RECORD-1",
             (6, "R(a: x)")),
    "E509": ("record R:\n    a: Int\n\nfn f(r: R) -> Int:\n    return r.b\n", None, "P0-RECORD-2", (5, "b")),
    "E510": ("fn f(flag: Bool) -> Int:\n    return flag + 1\n", None, "P0-TYPE-2", (2, "flag")),
    "E511": ("fn f() -> Int:\n    return length([])\n", None, "P0-TYPE-3", (2, "[]")),
    "E512": ("fn pay(amount: Int) -> Int:\n    return Payments.charge(amount)\n", None, "P0-EFFECT-1",
             (2, "Payments.charge(amount)")),
    "E513": ("fn f(n: Int) -> Int:\n    let h = await Inventory.reserve(n)\n    return n\n", None, "P0-EFFECT-2",
             (2, "await Inventory.reserve(n)")),
    "E514": ("fn f(n: Int) -> Int:\n    fork:\n        let a = n\n    return n\n", None, "P0-FORK-1", (2, "fork")),
    "E515": ("fn f(x: Int) -> Int:\n    if x < 0:\n        return 0\n    return x\n", None, "P0-PATH-1", (2, "if")),
    "E516": ("fn a(n: Int) -> Int:\n    return b(n)\n\nfn b(n: Int) -> Int:\n    return a(n)\n", None, "P0-REC-1",
             (2, "b(n)")),
    "E520": ("fn q(a: Int, d: Int) -> Int:\n    return 1 + div(a, d)\n", ("q", [1, 0], None), "P0-ARITH-2",
             (2, "div(a, d)")),
    "E521": ("fn h(xs: List[Int]) -> Int:\n    return head(xs)\n", ("h", [[]], None), "P0-LIST-1", (2, "head(xs)")),
    "E530": (P0_BUDGETS, ("spin", [0], {"fuel": 10}), "P0-BUDGET-2", (5, "spin(n + 1)")),
    "E531": (P0_BUDGETS, ("depth", [100], {"depth": 5}), "P0-BUDGET-3", (11, "depth(n - 1)")),
    "E532": (P0_BUDGETS, ("doubling", [100, 1], {"int_bits": 8}), "P0-BUDGET-4", (17, "acc * 2")),
    "E540": (P0_BUDGETS, ("identity", ["1"], None), "P0-RUN-1", (25, "identity")),
}


# modules-1 code: the modules corpus case that requires it, whose code, file and
# line scripts/modules_conformance.py checks (and the whole weave-diagnostic-v1
# document through the Rust binary); E603 needs a symbolic link out of the root,
# which tests/test_modules.py::Resolution creates.
MODULES = json.loads((EXAMPLES / "modules/manifest.json").read_text(encoding="utf-8"))
MODULE_FIXTURES = {c["expect"]: c["id"] for c in MODULES["cases"] if c["expect"].startswith("E6")}
MODULE_FIXTURES["E603"] = "tests/test_modules.py::Resolution::test_links_may_not_leave_the_root"


def module_codes() -> set[str]:
    """modules-1 codes emitted by the Rust crates, the kit runner and the corpus runner."""
    found = emitted_codes(MODULES_RUNNER + kit_sources()) | rust_codes()
    return {c for c in found if c.startswith("E6")}


def p0_diagnostic(code):
    source, request, *_ = P0_FIXTURES[code]
    try:
        program = p0_reference.check(source)
        entry, args, budgets = request
        report = p0_reference.run(program, entry, args, budgets)
        diagnostic = report["diagnostics"][0]
    except p0_reference.Diagnostic as d:
        diagnostic = d
    return source, diagnostic.document(f"{code}.weave")


def span_text(source, span):
    """The text a single-line span covers."""
    assert span["start"]["line"] == span["end"]["line"], span
    return source.splitlines()[span["start"]["line"] - 1][span["start"]["column"] - 1:span["end"]["column"] - 1]


class DiagnosticMap(unittest.TestCase):
    def test_every_emitted_code_is_mapped(self):
        self.assertEqual(unmapped(PROTOTYPE + kit_sources(), MAP), [])

    def test_mapped_specification_codes_are_the_prototype_p0_and_module_codes(self):
        prototype = {c for c in emitted_codes(PROTOTYPE)}
        modules = module_codes()
        p0 = (emitted_codes(P0_REFERENCE) | rust_codes()) - modules
        spec = {c for c, e in MAP.items() if e["category"] == "specification"}
        self.assertEqual(spec, prototype | p0 | modules)
        # The two P0 implementations emit the same P0 codes, all in the E5xx range.
        self.assertEqual(emitted_codes(P0_REFERENCE) - {"E001"}, rust_codes() - modules - {"E001", "E003", "E200"})
        self.assertTrue(all(c.startswith("E5") for c in p0 - {"E001", "E003", "E200"}))
        # modules-1 codes are E600 to E619, each with a MOD-* principal rule.
        self.assertTrue(modules)
        self.assertTrue(all(600 <= int(c[1:]) <= 619 for c in modules))
        self.assertTrue(all(MAP[c]["rule"].startswith("MOD-") for c in modules))
        # The P0 reference implements P0 only: it emits no modules-1 code.
        self.assertFalse(emitted_codes(P0_REFERENCE) & modules)

    def test_p0_sources_are_mapped(self):
        self.assertEqual(unmapped(P0_REFERENCE, MAP), [])
        self.assertEqual(sorted(rust_codes() - set(MAP)), [])
        with tempfile.TemporaryDirectory() as tmp:
            crate = Path(tmp) / "weave-x/src"
            crate.mkdir(parents=True)
            (crate / "lib.rs").write_text('const C: &str = "E599";\n', encoding="utf-8")
            self.assertEqual(rust_codes(Path(tmp)) - set(MAP), {"E599"})

    def test_unmapped_code_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "checker.py"
            source.write_text('raise CheckError("E999", "new rule")\nd = {"code": "NEW_TOOL_CODE"}\n', encoding="utf-8")
            self.assertEqual(unmapped([source], MAP), ["E999", "NEW_TOOL_CODE"])
        reduced = {c: e for c, e in MAP.items() if c != "E204"}
        self.assertEqual(unmapped(PROTOTYPE, reduced), ["E204"])

    def test_each_code_has_one_principal_rule_from_the_right_source(self):
        check_diagnostic_map(MAP, RULES)
        for code, entry in MAP.items():
            with self.subTest(code=code):
                if entry["category"] == "specification":
                    self.assertIn(entry["rule"], RULES)
                elif entry["category"] == "kit-extension":
                    self.assertRegex(entry["rule"], r"^KIT-PURE-[A-Z]+-\d+$")
                else:
                    self.assertIsNone(entry["rule"])

    def test_map_checks_reject_bad_entries(self):
        bad = [
            {"E204": dict(MAP["E204"], rule=None)},
            {"E204": dict(MAP["E204"], rule="F0-NOPE-1")},
            {"E204": dict(MAP["E204"], secondary_rules=["F0-RETURN-1"])},
            {"E204": dict(MAP["E204"], category="other")},
            {"TOOL_ERROR": dict(MAP["TOOL_ERROR"], rule="F0-RETURN-1")},
        ]
        for codes in bad:
            with self.subTest(codes=codes), self.assertRaises(ValueError):
                check_diagnostic_map(codes, RULES)

    def test_kit_copy_is_identical(self):
        copy = REPO / "agent-kit/.agents/skills/weave/assets/diagnostics.json"
        self.assertEqual(copy.read_bytes(), (ROOT / "diagnostics.json").read_bytes())


class DiagnosticPerCode(unittest.TestCase):
    def diagnostic(self, code):
        (stage, source, action), *_ = FIXTURES[code]
        with self.assertRaises(CheckError) as raised:
            action()
        self.assertEqual(raised.exception.code, code, raised.exception.message)
        document = as_diagnostic(raised.exception, f"{code}.weave", source, stage)
        result = assess(document)
        self.assertTrue(result.accepted, result.errors)
        return source, document

    def test_every_specification_code_has_a_fixture(self):
        self.assertEqual(set(FIXTURES) | set(P0_FIXTURES) | set(MODULE_FIXTURES),
                         {c for c, e in MAP.items() if e["category"] == "specification"})
        self.assertFalse(set(FIXTURES) & set(P0_FIXTURES))
        self.assertFalse((set(FIXTURES) | set(P0_FIXTURES)) & set(MODULE_FIXTURES))

    def test_module_fixtures_are_located_cases(self):
        cases = {c["id"]: c for c in MODULES["cases"]}
        for code, case_id in MODULE_FIXTURES.items():
            with self.subTest(code=code):
                if case_id.startswith("tests/"):
                    continue
                case = cases[case_id]
                self.assertEqual(case["expect"], code)
                self.assertIn("line", case)
                self.assertIn(MAP[code]["rule"], case["rules"], case_id)

    def test_p0_code_rule_and_span_for_every_code(self):
        for code, (_, _, rule, primary) in P0_FIXTURES.items():
            with self.subTest(code=code):
                source, document = p0_diagnostic(code)
                result = assess(document)
                self.assertTrue(result.accepted, result.errors)
                self.assertEqual((document["code"], document["rule"]), (code, rule))
                self.assertEqual(document["secondary_rules"], MAP[code]["secondary_rules"])
                self.assertEqual(document["category"], "specification")
                self.assertEqual(document["span"]["start"]["line"], primary[0])
                self.assertEqual(span_text(source, document["span"]), primary[1])

    def test_code_rule_and_span_for_every_code(self):
        for code, (_, rule, primary, related) in FIXTURES.items():
            with self.subTest(code=code):
                source, document = self.diagnostic(code)
                self.assertEqual(document["code"], code)
                self.assertEqual(document["rule"], rule)
                self.assertEqual(document["secondary_rules"], MAP[code]["secondary_rules"])
                self.assertEqual(document["span"]["file"], f"{code}.weave")
                self.assertEqual(document["span"]["start"]["line"], primary[0])
                self.assertEqual(span_text(source, document["span"]), primary[1])
                roles = MAP[code].get("related_roles", {})
                found = {r["role"] for r in document["related"]}
                self.assertLessEqual(found, set(roles))
                self.assertLessEqual({r for r, when in roles.items() if when == "always"}, found)
                for role, (line, text) in (related or {}).items():
                    spans = [r["span"] for r in document["related"] if r["role"] == role]
                    self.assertTrue(spans, role)
                    self.assertEqual(spans[0]["start"]["line"], line)
                    self.assertEqual(span_text(source, spans[0]), text)

    def test_diagnostic_without_a_line_spans_the_whole_source(self):
        source = "# No flow is declared here.\n# Second comment line.\n"
        with self.assertRaises(CheckError) as raised:
            check_flow(parse_net(N0), source)
        self.assertEqual((raised.exception.code, raised.exception.line), ("E200", 0))
        document = as_diagnostic(raised.exception, "empty.weave", source, "flow")
        self.assertTrue(assess(document).accepted)
        self.assertEqual((document["span"]["start"], document["span"]["end"]),
                         ({"line": 1, "column": 1}, {"line": 2, "column": 23}))

    def test_ownership_codes_have_related_spans(self):
        self.assertEqual({c for c, e in MAP.items() if e.get("related_roles")}, {"E203", "E204", "E604"})
        # An import cycle (modules-1) always lists its imports.
        self.assertEqual(MAP["E604"]["related_roles"], {"import": "always"})
        self.assertTrue(all(c.get("related") for c in MODULES["cases"] if c["expect"] == "E604"))
        self.assertEqual(MAP["E203"]["related_roles"], {"binding": "always", "moved": "always"})
        self.assertEqual(MAP["E204"]["related_roles"]["binding"], "always")
        self.assertNotEqual(MAP["E204"]["related_roles"]["propagation"], "always")
        for code in ("E203", "E204"):
            with self.subTest(code=code):
                self.assertIsNotNone(FIXTURES[code][3])
                _, document = self.diagnostic(code)
                self.assertTrue(document["related"])

    def related(self, source):
        with self.assertRaises(CheckError) as raised:
            check_flow(parse_net(N0), source)
        document = as_diagnostic(raised.exception, "f.weave", source, "flow")
        self.assertTrue(assess(document).accepted)
        return raised.exception.code, {r["role"]: (r["span"]["start"]["line"], span_text(source, r["span"]))
                                       for r in document["related"]}

    def test_every_e203_path_has_binding_and_moved(self):
        call_twice = ("flow f(h: Hold[t, o]):\n    await helper(h, h)\n    return\n"
                      "flow helper(a: Hold[t, o], b: Hold[t, o]):\n    return\n")
        reused_return = "flow f(h: Hold[t, o]) -> Escrow[t, o]:\n    let e = await Inventory.arm(h)\n    return h\n"
        reused_match = ("flow f(r: ChargeOutcome[t, o]):\n    let p = r?\n    match r:\n        Ok(x):\n            return\n")
        callee_named_h = ("flow f(h: Hold[t, o]):\n    await h(h, h)\n    return\n"
                          "flow h(a: Hold[t, o], b: Hold[t, o]):\n    return\n")
        for source, moved in ((call_twice, (2, "h")), (reused_return, (2, "h")), (reused_match, (2, "r")),
                              (callee_named_h, (2, "h"))):
            with self.subTest(source=source):
                code, roles = self.related(source)
                self.assertEqual(code, "E203")
                self.assertEqual(roles["moved"], moved)
                self.assertEqual(roles["binding"][0], 1)
        # The callee `h` is at columns 11-12; the moved span is the first argument at 13-14.
        with self.assertRaises(CheckError) as raised:
            check_flow(parse_net(N0), callee_named_h)
        moved = [r.span for r in raised.exception.related if r.role == "moved"][0]
        self.assertEqual((moved.line, moved.column, moved.end_column), (2, 13, 14))

    def test_spans_skip_earlier_names_spelled_like_the_handle(self):
        # A flow named like its parameter: the binding span is the parameter, not the flow name.
        code, roles = self.related("flow h(h: Hold[t, o]):\n    return\n")
        self.assertEqual(code, "E204")
        with self.assertRaises(CheckError) as raised:
            check_flow(parse_net(N0), "flow h(h: Hold[t, o]):\n    return\n")
        binding = raised.exception.related[0].span
        self.assertEqual((binding.line, binding.column, binding.end_column), (1, 8, 9))
        # A handle spelled like a field of the called operation's qualified name is not matched there.
        source = ("flow f(arm: Hold[t, o]):\n    let e = await Inventory.arm(arm)\n"
                  "    let x = await Inventory.arm(arm)\n    return\n")
        with self.assertRaises(CheckError) as raised:
            check_flow(parse_net(N0), source)
        self.assertEqual(raised.exception.code, "E203")
        moved = [r.span for r in raised.exception.related if r.role == "moved"][0]
        self.assertEqual((moved.line, moved.column, moved.end_column), (2, 33, 36))

    def test_e204_at_ordinary_return_has_no_propagation_span(self):
        code, roles = self.related("flow f(h: Hold[t, o]):\n    return\n")
        self.assertEqual(code, "E204")
        self.assertEqual(roles, {"binding": (1, "h")})

    def test_weave_check_helper_returns_valid_diagnostics(self):
        source = (EXAMPLES / "invalid/early_return_leak.weave").read_text(encoding="utf-8")
        result, document = check_example_diagnostic(source, label="examples/invalid/early_return_leak.weave")
        self.assertEqual(result, "E204")
        self.assertTrue(assess(document).accepted)
        self.assertEqual((document["rule"], document["span"]["file"]), ("F0-RETURN-1", "examples/invalid/early_return_leak.weave"))
        self.assertEqual(span_text(source, document["span"]), "let paid = result?")
        self.assertEqual(check_example_diagnostic((EXAMPLES / "valid/checkout.weave").read_text(encoding="utf-8")), ("ACCEPT", None))
        # A wrapped body maps spans back to the displayed snippet.
        result, document = check_example_diagnostic("let hold = Hold(tenant, order)\n", "F0/N0", "await-body")
        self.assertEqual(result, "E205")
        self.assertEqual((document["span"]["start"], document["span"]["end"]),
                         ({"line": 1, "column": 1}, {"line": 1, "column": 31}))

    def test_invalid_document_is_refused(self):
        _, document = self.diagnostic("E204")
        self.assertFalse(assess(dict(document, rule=None)).accepted)
        self.assertFalse(assess(dict(document, format="weave-diagnostic-v2")).accepted)


if __name__ == "__main__":
    unittest.main()
