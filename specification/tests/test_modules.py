# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""modules-1 (quaat/weave#12): the modules corpus and its runner.

``scripts/modules_conformance.py`` runs ``examples/modules/manifest.json``: the
P0 programs through the Rust ``weave`` command, the ``use net`` flow cases through
its own header resolution and the unchanged reference checker. These tests check
the header rules, that a header keeps every flow diagnostic at its location in the
``--net`` form, the resolution rules, that a missing Rust binary is recorded as not
established (never as agreement) and that a disagreeing binary fails.
"""
from pathlib import Path
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import modules_conformance as mc  # noqa: E402

EXAMPLES = ROOT / "examples"
MANIFEST = json.loads((EXAMPLES / "modules/manifest.json").read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in MANIFEST["cases"]}
HOLD = "flow keep(hold: Hold[t, o]) -> Hold[t, o]:\n    return hold\n"


class Manifest(unittest.TestCase):
    def test_format_is_versioned_and_kept_apart(self):
        self.assertEqual(MANIFEST["format"], "weave-modules-conformance-v1")
        self.assertEqual(MANIFEST["extension"], "modules-1")
        self.assertEqual(json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))["format"],
                         "weave-conformance-v1")
        self.assertEqual(json.loads((EXAMPLES / "pure/manifest.json").read_text(encoding="utf-8"))["format"],
                         "weave-p0-conformance-v1")
        with mock.patch.object(mc, "MANIFEST", EXAMPLES / "pure/manifest.json"):
            with self.assertRaises(ValueError):
                mc.manifest()

    def test_every_module_code_has_a_case_with_a_location(self):
        codes = json.loads((ROOT / "diagnostics.json").read_text(encoding="utf-8"))["codes"]
        module_codes = {c for c, e in codes.items() if c.startswith("E6")}
        self.assertEqual(module_codes, {f"E6{n:02d}" for n in range(11)})
        covered = {c["expect"] for c in MANIFEST["cases"]}
        # E603 needs a symbolic link out of the root, which the corpus does not
        # hold; the Rust, kit and Resolution tests below cover it.
        self.assertEqual(module_codes - covered, {"E603"})
        for case in MANIFEST["cases"]:
            if case["expect"] not in {"ACCEPT", "VALUE", "E540"}:
                with self.subTest(case=case["id"]):
                    self.assertIn("line", case)
            self.assertTrue(case["rules"], case["id"])

    def test_both_directions_are_covered(self):
        positive = [c for c in MANIFEST["cases"] if c["expect"] in {"ACCEPT", "VALUE"}]
        negative = [c for c in MANIFEST["cases"] if c["expect"] not in {"ACCEPT", "VALUE"}]
        self.assertGreaterEqual(len(positive), 8)
        self.assertGreaterEqual(len(negative), 20)


class Header(unittest.TestCase):
    def test_header_and_its_location(self):
        self.assertEqual(mc.header("use net nets.Inventory\n" + HOLD), (1, "nets.Inventory", 9))
        self.assertEqual(mc.header("# c\n\nuse  net  a . b  # x\n" + HOLD), (3, "a.b", 11))
        self.assertIsNone(mc.header(HOLD))
        self.assertIsNone(mc.header(HOLD + "use net nets.Inventory\n"))
        self.assertIsNone(mc.header("    use net a\n" + HOLD))

    def test_malformed_headers_are_e600(self):
        for text in ("use net\n", "use nets.Inventory\n", "use net ..a\n", "use net a.\n", "use net /a\n"):
            with self.subTest(text=text):
                with self.assertRaises(mc.ModuleFailure) as raised:
                    mc.header(text + HOLD)
                self.assertEqual((raised.exception.code, raised.exception.line), ("E600", 1))

    def test_flow_cases_keep_the_locations_of_the_net_form(self):
        for case in (c for c in MANIFEST["cases"] if c["kind"] == "flow"):
            with self.subTest(case=case["id"]):
                result = mc.flow_case(case)
                mc.assert_flow(case, result)
        located = mc.flow_case(CASES["M304"])
        self.assertEqual(located["code"], "E205")
        self.assertEqual(located, located["net_form"] | {"net_form": located["net_form"]})

    def test_a_conflicting_net_is_e610_and_the_same_net_is_accepted(self):
        self.assertEqual(mc.flow_case(CASES["M303"])["code"], "E610")
        self.assertEqual(mc.flow_case(CASES["M302"])["code"], "ACCEPT")
        self.assertEqual(mc.flow_case(dict(CASES["M302"], net="nets/../nets/Inventory.weave"))["code"], "ACCEPT")

    def test_a_wrong_location_fails(self):
        with self.assertRaises(AssertionError):
            mc.assert_flow(dict(CASES["M304"], column=6), mc.flow_case(CASES["M304"]))
        with self.assertRaises(AssertionError):
            mc.assert_flow(CASES["M304"], dict(mc.flow_case(CASES["M304"]), net_form={"code": "E205"}))


class Resolution(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "Nets").mkdir()
        (self.root / "Nets/Inventory.weave").write_text("net N(s: Nat):\n", encoding="utf-8")

    def code(self, dotted):
        with self.assertRaises(mc.ModuleFailure) as raised:
            mc.resolve(self.root, dotted, 1, 9)
        return raised.exception.code

    def test_paths_name_files_exactly(self):
        self.assertEqual(mc.resolve(self.root, "Nets.Inventory", 1, 9), self.root / "Nets/Inventory.weave")
        self.assertEqual(self.code("nets.Inventory"), "E602")
        self.assertEqual(self.code("Nets.inventory"), "E602")
        self.assertEqual(self.code("Nets.Missing"), "E601")
        self.assertEqual(self.code("Nets"), "E601")

    @unittest.skipIf(os.name == "nt", "symbolic links")
    def test_links_may_not_leave_the_root(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "Evil.weave").write_text("net N(s: Nat):\n", encoding="utf-8")
        (self.root / "away").symlink_to(outside)
        (self.root / "Inside.weave").symlink_to(self.root / "Nets/Inventory.weave")
        self.assertEqual(self.code("away.Evil"), "E603")
        self.assertEqual(mc.resolve(self.root, "Inside", 1, 9), self.root / "Inside.weave")


class RustComparison(unittest.TestCase):
    def test_without_a_binary_the_rust_cases_are_not_established(self):
        report = mc.build_report(None, "cargo is not on PATH and WEAVE_BIN is not set")
        self.assertEqual(report["rust"]["status"], "skipped")
        self.assertEqual(report["rust"]["compared"], 0)
        self.assertIn("not established", report["rust"]["note"])
        self.assertNotIn("rows", report["rust"])
        # The flow cases are still checked with the reference checker.
        self.assertEqual(len(report["flow_cases"]), sum(c["kind"] == "flow" for c in MANIFEST["cases"]))

    @unittest.skipIf(os.name == "nt", "the stand-in binary is a POSIX shell script")
    def test_a_disagreeing_binary_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "weave"
            fake.write_text('#!/bin/sh\necho \'{"diagnostics": [], "value": null}\'\n', encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            # Accepting everything disagrees with the first rejected case.
            with self.assertRaises(AssertionError):
                mc.build_report(fake, "WEAVE_BIN")

    def test_rust_rows_check_code_file_line_and_related(self):
        case = CASES["M115"]
        span = lambda f, line: {"file": str(EXAMPLES / f), "start": {"line": line, "column": 6},
                                "end": {"line": line, "column": 7}}
        diagnostic = {"format": "weave-diagnostic-v1", "code": "E604", "category": "specification",
                      "rule": "MOD-CYCLE-1", "secondary_rules": [], "severity": "error", "stage": "module",
                      "message": "cycle", "span": span(case["file"], case["line"]),
                      "related": [{"role": "import", "label": "x", "span": span(f, line)} for f, line in case["related"]],
                      "details": {}}
        row = mc.assert_rust(case, {"diagnostics": [diagnostic]})
        self.assertEqual(row["related"], case["related"])
        wrong = dict(diagnostic, related=diagnostic["related"][:-1])
        with self.assertRaises(AssertionError):
            mc.assert_rust(case, {"diagnostics": [wrong]})
        with self.assertRaises(AssertionError):
            mc.assert_rust(case, {"diagnostics": [dict(diagnostic, code="E516")]})


if __name__ == "__main__":
    unittest.main()
