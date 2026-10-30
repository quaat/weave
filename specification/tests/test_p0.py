# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""P0 rules (docs/chapters/pure.rst) against the P0 reference evaluator, and the differential.

Each test names the rule IDs it exercises; ``tests/rule-coverage.json`` records the
mapping. A negative test asserts the code the chapter requires. The reference is
written from the chapter; ``scripts/p0_differential.py`` compares it with the Rust
``weave`` command, and the tests below check that a missing Rust toolchain is
reported as not established, never as agreement.
"""
from pathlib import Path
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import p0_reference as ref  # noqa: E402
import p0_differential  # noqa: E402

EXAMPLES = ROOT / "examples"


def code(source):
    try:
        ref.check(source)
        return "ACCEPT"
    except ref.Diagnostic as d:
        return d.code


def spanned(source):
    """(code, rule, text under the primary span) of the first diagnostic."""
    try:
        ref.check(source)
    except ref.Diagnostic as d:
        doc = d.document("t.weave")
        sl, sc, el, ec = d.span
        lines = source.split("\n")
        text = lines[sl - 1][sc - 1:ec - 1] if sl == el else None
        return doc["code"], doc["rule"], text
    raise AssertionError("accepted")


def run(source, entry, args, **budgets):
    program = ref.check(source)
    try:
        return ref.run(program, entry, args, budgets)
    except ref.Diagnostic as d:
        return {"code": d.code}


def outcome(report):
    if "code" in report:
        return report["code"]
    return report["diagnostics"][0].code if report["diagnostics"] else report["value"]


def fn(body, sig="(x: Int) -> Int", prefix=""):
    return f"{prefix}fn f{sig}:\n    " + body.replace("\n", "\n    ") + "\n"


class Static(unittest.TestCase):
    # P0-FILE-1
    def test_file_syntax(self):
        self.assertEqual(code(fn("return x")), "ACCEPT")
        self.assertEqual(code(fn("return 1 < x < 3", "(x: Int) -> Bool")), "E500")
        self.assertEqual(spanned(fn("return wait Payments.charge(x)")), ("E500", "P0-FILE-1", "wait"))
        self.assertEqual(code("flow f():\n    return\n"), "E500")
        self.assertEqual(code(fn("return 007")), "E500")
        self.assertEqual(code(fn("return xé")), "E500")
        self.assertEqual(code(fn("\treturn x")), "E001")

    # P0-DECL-1
    def test_top_level_names(self):
        self.assertEqual(code("record R:\n    a: Int\n\nfn r(x: R) -> Int:\n    return x.a\n"), "ACCEPT")
        self.assertEqual(code(fn("return 1") + fn("return 2")), "E501")
        for name in ("head", "not", "true", "Int"):
            self.assertEqual(code(f"fn {name}() -> Int:\n    return 1\n"), "E501")

    # P0-DECL-2, P0-DECL-3
    def test_records(self):
        self.assertEqual(code("record P:\n    a: Int\n\nrecord Q:\n    ps: List[P]\n"), "ACCEPT")
        self.assertEqual(code("record P:\n    a: Int\n    a: Bool\n"), "E502")
        self.assertEqual(code("record T:\n    kids: List[T]\n"), "E503")
        self.assertEqual(code("record A:\n    b: B\n\nrecord B:\n    a: A\n"), "E503")

    # P0-DECL-4
    def test_signatures_first_and_unused_bodies(self):
        self.assertEqual(code("fn a() -> P:\n    return b(1)\n\nfn b(x: Int) -> P:\n    return P(v: x)\n\nrecord P:\n    v: Int\n"),
                         "ACCEPT")
        self.assertEqual(code("fn used() -> Int:\n    return 1\n\nfn unused() -> Int:\n    return true\n"), "E510")

    # P0-TYPE-1
    def test_types_and_handles(self):
        self.assertEqual(code(fn("return []", "(xs: List[List[Bool]]) -> List[Int]")), "ACCEPT")
        self.assertEqual(spanned(fn("return 0", "(hold: Hold[t, o]) -> Int")), ("E504", "P0-TYPE-1", "Hold[t, o]"))
        for bad in ("Nat", "Unit", "List", "List[Int, Int]", "Int[x]", "Escrow[t, o]"):
            self.assertEqual(code(fn("return 0", f"(x: {bad}) -> Int")), "E504", bad)

    # P0-NAME-1
    def test_names_in_values(self):
        self.assertEqual(code(fn("let y = x\nreturn y", "(x: Int) -> Int")), "ACCEPT")
        self.assertEqual(code(fn("return y")), "E505")
        self.assertEqual(code(fn("return f")), "E505")
        self.assertEqual(code(fn("return Inventory.stock")), "E505")

    # P0-NAME-2
    def test_no_shadowing(self):
        self.assertEqual(code(fn("if x > 0:\n    let y = 1\n    return y\nelse:\n    let y = 2\n    return y")), "ACCEPT")
        self.assertEqual(code(fn("let x = 1\nreturn x")), "E506")
        self.assertEqual(code(fn("return x", "(x: Int, x: Int) -> Int")), "E506")
        self.assertEqual(code(fn("let length = 1\nreturn x")), "E506")

    # P0-TYPE-2
    def test_type_mismatch(self):
        self.assertEqual(code(fn("return b == (x != 0) and -x < x * 2", "(b: Bool, x: Int) -> Bool")), "ACCEPT")
        self.assertEqual(code(fn("return b + 1", "(b: Bool) -> Int")), "E510")
        self.assertEqual(code(fn("return [1] == [1]", "(b: Bool) -> Bool")), "E510")
        self.assertEqual(code(fn("if x:\n    return 1\nelse:\n    return 2")), "E510")

    # P0-TYPE-3
    def test_empty_list_needs_an_expected_type(self):
        self.assertEqual(code(fn("let ys = cons(1, [])\nreturn [[], ys]", "() -> List[List[Int]]")), "ACCEPT")
        self.assertEqual(code(fn("let xs = []\nreturn 0", "() -> Int")), "E511")
        self.assertEqual(code(fn("return length([])", "() -> Int")), "E511")

    # P0-CALL-1
    def test_calls(self):
        g = "fn g(x: Int) -> Int:\n    return x\n\n"
        self.assertEqual(code(g + fn("return g(div(x, 2))")), "ACCEPT")
        self.assertEqual(code(g + fn("return g(1, 2)")), "E507")
        self.assertEqual(code(g + fn("return g(x: 1)")), "E507")
        self.assertEqual(code(g + fn("return nothing(1)")), "E507")
        self.assertEqual(code(g + fn("return x(1)")), "E507")
        self.assertEqual(code("record P:\n    a: Int\n\n" + fn("return P(x)", "(x: Int) -> P")), "E507")

    # P0-RECORD-1, P0-RECORD-2
    def test_record_construction_and_access(self):
        rec = "record R:\n    dest: Int\n    cost: Int\n\n"
        self.assertEqual(code(rec + fn("return R(cost: r.dest, dest: r.cost)", "(r: R) -> R")), "ACCEPT")
        self.assertEqual(code(rec + fn("return R(dest: d)", "(d: Int) -> R")), "E508")
        self.assertEqual(code(rec + fn("return R(dest: d, cost: d, price: d)", "(d: Int) -> R")), "E508")
        self.assertEqual(spanned(rec + fn("return r.price", "(r: R) -> Int")), ("E509", "P0-RECORD-2", "price"))

    # P0-EFFECT-1, P0-EFFECT-2, P0-FORK-1
    def test_purity(self):
        self.assertEqual(spanned(fn("return Payments.charge(x)")),
                         ("E512", "P0-EFFECT-1", "Payments.charge(x)"))
        self.assertEqual(spanned(fn("let h = await Inventory.reserve(x)\nreturn x")),
                         ("E513", "P0-EFFECT-2", "await Inventory.reserve(x)"))
        self.assertEqual(spanned(fn("fork:\n    let a = x\nreturn x")), ("E514", "P0-FORK-1", "fork"))
        self.assertEqual(code(fn("return x + 1")), "ACCEPT")

    # P0-PATH-1
    def test_terminal_blocks(self):
        self.assertEqual(code(fn("let a = 1\nif x > 0:\n    return a\nelse:\n    return 0")), "ACCEPT")
        self.assertEqual(code(fn("if x < 0:\n    return -1\nreturn 1")), "E515")
        self.assertEqual(code(fn("return 1\nreturn 2")), "E515")
        self.assertEqual(code(fn("let y = 1")), "E515")

    # P0-REC-1
    def test_direct_recursion_only(self):
        self.assertEqual(code(fn("if x <= 0:\n    return 0\nelse:\n    return f(x - 1)")), "ACCEPT")
        even_odd = ("fn even(n: Int) -> Bool:\n    return n == 0 or odd(n - 1)\n\n"
                    "fn odd(n: Int) -> Bool:\n    return n != 0 and even(n - 1)\n")
        self.assertEqual(spanned(even_odd), ("E516", "P0-REC-1", "odd(n - 1)"))

    # P0-FILE-1: the nesting limits, the same in both implementations
    def test_nesting_limits(self):
        limit = ref.EXPR_DEPTH_LIMIT
        self.assertEqual((ref.SYNTAX_DEPTH_LIMIT, limit), (300, 256))
        self.assertEqual(code(fn("return " + " + ".join(["x"] * limit))), "ACCEPT")
        for source in (fn("return " + " + ".join(["x"] * (limit + 1))),
                       fn("return " + " or ".join(["true"] * (limit + 1)), "(x: Int) -> Bool"),
                       fn("return " + "-" * limit + "1"),
                       fn("return " + "(" * 42 + "1" + ")" * 42)):
            try:
                ref.check(source)
            except ref.Diagnostic as d:
                self.assertEqual((d.code, d.stage), ("E500", "limit"))
            else:
                self.fail("accepted")
        self.assertEqual(code(fn("return " + "(" * 41 + "1" + ")" * 41)), "ACCEPT")

    def test_negative_budgets_are_usage_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.weave"
            path.write_text(BUDGETS, encoding="utf-8")
            for flag in ("--fuel", "--max-depth", "--int-bits"):
                with self.subTest(flag), mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                    ref.main(["run", str(path), "--entry", "identity", "--args", "[1]", flag, "-1"])
                self.assertEqual(raised.exception.code, 2)

    def test_corpus_check_cases(self):
        manifest = json.loads((EXAMPLES / "pure/manifest.json").read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            if case["kind"] == "check":
                with self.subTest(case["id"]):
                    self.assertEqual(code((EXAMPLES / case["file"]).read_text(encoding="utf-8")), case["expect"])


ARITH = (EXAMPLES / "pure/valid/arithmetic.weave").read_text(encoding="utf-8")
BUDGETS = (EXAMPLES / "pure/valid/budgets.weave").read_text(encoding="utf-8")
SHORT = (EXAMPLES / "pure/valid/short_circuit.weave").read_text(encoding="utf-8")
LISTS = (EXAMPLES / "pure/valid/lists.weave").read_text(encoding="utf-8")


class Dynamic(unittest.TestCase):
    # P0-VALUE-1, P0-ARITH-1, P0-RUN-2
    def test_exact_values(self):
        self.assertEqual(outcome(run(ARITH, "power", [2, 100])), 2 ** 100)
        self.assertEqual(outcome(run(ARITH, "polynomial", [-3])), 26)
        records = (EXAMPLES / "pure/valid/records.weave").read_text(encoding="utf-8")
        self.assertEqual(outcome(run(records, "point", [1, 2])), {"x": 1, "y": 2})

    # P0-ARITH-2
    def test_euclidean_division(self):
        for a in range(-9, 10):
            for d in (-4, -3, -1, 1, 2, 5):
                r = a % abs(d)
                self.assertEqual(a, d * ((a - r) // d) + r)
                self.assertEqual(outcome(run(ARITH, "quotient", [a, d])), (a - r) // d)
                self.assertEqual(outcome(run(ARITH, "remainder", [a, d])), r)
            self.assertEqual(outcome(run(ARITH, "quotient", [a, 0])), "E520")
            self.assertEqual(outcome(run(ARITH, "remainder", [a, 0])), "E520")

    # P0-LIST-1, P0-FAULT-1
    def test_list_primitives_and_faults(self):
        self.assertEqual(outcome(run(LISTS, "reverse", [[1, 2, 3], []])), [3, 2, 1])
        self.assertEqual(outcome(run(LISTS, "first", [[]])), "E521")
        self.assertEqual(outcome(run(LISTS, "rest", [[]])), "E521")
        report = run(LISTS, "first", [[]])
        self.assertEqual(report["outcome"], "fault")
        self.assertIsNone(report["value"])
        self.assertEqual(report["diagnostics"][0].document("x")["rule"], "P0-LIST-1")

    # P0-EVAL-1
    def test_left_to_right(self):
        src = ("record R:\n    a: Int\n    b: Int\n\nfn rec(xs: List[Int]) -> R:\n    return R(b: head(xs), a: div(1, 0))\n\n"
               "fn ab(xs: List[Int]) -> Int:\n    return div(1, 0) + head(xs)\n")
        self.assertEqual(outcome(run(src, "rec", [[]])), "E521")
        self.assertEqual(outcome(run(src, "ab", [[]])), "E520")

    # P0-EVAL-2
    def test_short_circuit(self):
        self.assertEqual(outcome(run(SHORT, "safe_ratio_above", [0, 1])), False)
        self.assertEqual(outcome(run(SHORT, "zero_or_divides", [0])), True)
        self.assertEqual(run(SHORT, "skips_calls", [True, 10 ** 6])["budgets"]["fuel"]["used"], 1)

    # P0-EVAL-3, P0-BUDGET-1, P0-BUDGET-2, P0-BUDGET-3
    def test_fuel_and_depth(self):
        report = run(BUDGETS, "spin", [0], fuel=1000)
        self.assertEqual((report["outcome"], report["exhausted"]), ("exhausted", "fuel"))
        self.assertEqual(report["diagnostics"][0].code, "E530")
        self.assertEqual(report["budgets"]["fuel"], {"limit": 1000, "used": 1000})
        report = run(BUDGETS, "depth", [100], depth=50)
        self.assertEqual(report["diagnostics"][0].code, "E531")
        self.assertEqual(report["budgets"]["fuel"]["used"], 51)
        self.assertEqual(outcome(run(BUDGETS, "identity", [1], fuel=0, depth=0)), "E530")
        self.assertEqual(outcome(run(BUDGETS, "identity", [1], fuel=1, depth=0)), "E531")
        self.assertEqual(outcome(run(BUDGETS, "depth", [20000], depth=30000)), 20000)
        self.assertEqual(set(run(BUDGETS, "identity", [1])["budgets"]), {"fuel", "depth", "int_bits"})

    # P0-BUDGET-4
    def test_integer_size(self):
        self.assertEqual(outcome(run(BUDGETS, "doubling", [100, 1], int_bits=32)), "E532")
        report = run(BUDGETS, "identity", [300], int_bits=8)
        self.assertEqual((outcome(report), report["budgets"]["fuel"]["used"]), ("E532", 0))
        self.assertEqual(outcome(run(BUDGETS, "identity", [255], int_bits=8)), 255)
        self.assertEqual(outcome(run(BUDGETS, "identity", [-256], int_bits=9)), -256)

    # P0-RUN-1
    def test_run_requests(self):
        self.assertEqual(outcome(run(BUDGETS, "identity", ["1"])), "E540")
        self.assertEqual(outcome(run(BUDGETS, "identity", [True])), "E540")
        self.assertEqual(outcome(run(BUDGETS, "identity", [1.5])), "E540")
        self.assertEqual(outcome(run(BUDGETS, "identity", [])), "E540")
        self.assertEqual(outcome(run(BUDGETS, "missing", [])), "E540")
        records = (EXAMPLES / "pure/valid/records.weave").read_text(encoding="utf-8")
        seg = {"start": {"x": 0, "y": 0}, "finish": {"x": 3, "y": 4, "z": 5}}
        self.assertEqual(outcome(run(records, "length_squared", [seg])), "E540")
        dup = json.loads('{"x": 1, "x": 2, "y": 3}', object_pairs_hook=ref.json_object)
        self.assertEqual(outcome(run(records, "mirror", [{"start": dup, "finish": dup}])), "E540")

    def test_corpus_run_cases(self):
        manifest = json.loads((EXAMPLES / "pure/manifest.json").read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            if case["kind"] != "run":
                continue
            with self.subTest(case["id"]):
                source = (EXAMPLES / case["file"]).read_text(encoding="utf-8")
                report = run(source, case["entry"], case["args"], **case.get("budgets", {}))
                got = outcome(report)
                self.assertEqual(got, case["value"] if case["expect"] == "VALUE" else case["expect"])


class Differential(unittest.TestCase):
    def test_without_cargo_the_comparison_is_not_established(self):
        env = {k: v for k, v in os.environ.items() if k != "WEAVE_BIN"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(p0_differential.shutil, "which", return_value=None):
            binary, why = p0_differential.rust_binary()
        self.assertIsNone(binary)
        self.assertIn("cargo is not on PATH", why)

    def test_a_report_without_rust_says_not_established(self):
        report = p0_differential.build_report(None, "cargo is not on PATH", programs=2)
        rust = report["rust_differential"]
        self.assertEqual((rust["status"], rust["compared"]), ("skipped", 0))
        self.assertIn("not established", rust["note"])
        self.assertNotIn("agreements", rust)
        self.assertTrue(all("rust" not in row for row in report["corpus"]["rows"]))
        self.assertEqual(report["generated"]["compared_runs"], 0)

    def test_a_named_binary_must_exist(self):
        with mock.patch.dict(os.environ, {"WEAVE_BIN": str(ROOT / "no-such-binary")}):
            with self.assertRaises(FileNotFoundError):
                p0_differential.rust_binary()

    @unittest.skipIf(os.name == "nt", "the stand-in binary is a POSIX shell script")
    def test_a_disagreeing_rust_result_fails_the_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "weave"
            fake.write_text('#!/bin/sh\ncat >/dev/null\necho \'{"claims": [], "diagnostics": []}\'\n', encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            # The stand-in accepts everything, so the first rejected corpus file disagrees.
            with self.assertRaises(AssertionError):
                p0_differential.corpus(fake)

    def test_unknown_manifest_format_is_refused(self):
        with mock.patch.object(p0_differential, "MANIFEST", ROOT / "examples/manifest.json"):
            with self.assertRaises(ValueError):
                p0_differential.manifest()


if __name__ == "__main__":
    unittest.main()
