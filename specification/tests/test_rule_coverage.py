# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Positive and negative tests for scripts/rule_coverage.py."""
from pathlib import Path
import contextlib
import copy
import io
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
from rule_coverage import PAGE, CoverageError, load, main, render, validate  # noqa: E402


class RuleCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules, cls.manifest, cls.coverage = load()

    def mutated(self):
        return copy.deepcopy(self.coverage)

    def rejects(self, coverage, fragment, rules=None):
        with self.assertRaises(CoverageError) as raised:
            validate(rules or self.rules, self.manifest, coverage)
        self.assertIn(fragment, str(raised.exception))

    def test_committed_map_covers_every_rule_and_page_is_current(self):
        rows = validate(self.rules, self.manifest, self.coverage)
        self.assertEqual([r["rule"] for r in rows], sorted(self.rules))
        self.assertEqual((ROOT / PAGE).read_text(encoding="utf-8"), render(rows))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["--check"]), 0)
        self.assertIn("PASS: rule coverage current", out.getvalue())

    def test_every_pending_rule_has_a_reason(self):
        for row in validate(self.rules, self.manifest, self.coverage):
            if row["pending"] is not None:
                self.assertTrue(row["pending"]["reason"].strip(), row["rule"])

    def test_rule_without_entry_is_rejected(self):
        coverage = self.mutated()
        del coverage["rules"]["SYN-04"]
        self.rejects(coverage, "No coverage entry for SYN-04")

    def test_rule_with_nothing_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["SYN-04"] = {"tests": []}
        self.rejects(coverage, "SYN-04 has no conformance case, no test and no pending entry")

    def test_conformance_case_alone_is_enough(self):
        coverage = self.mutated()
        coverage["rules"]["N0-SEAL-1"] = {"tests": []}
        rows = {r["rule"]: r for r in validate(self.rules, self.manifest, coverage)}
        self.assertTrue(rows["N0-SEAL-1"]["cases"])
        self.assertIsNone(rows["N0-SEAL-1"]["pending"])

    def test_unknown_rule_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["SYN-99"] = {"tests": []}
        self.rejects(coverage, "unknown rule IDs: SYN-99")

    def test_missing_test_method_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["SYN-04"]["tests"][0]["test"] = "tests/test_rule_cases.py::RuleCases::test_absent"
        self.rejects(coverage, "Test not found")

    def test_missing_test_file_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["SYN-04"]["tests"][0]["test"] = "tests/absent.py::RuleCases::test_x"
        self.rejects(coverage, "Test file does not exist")

    def test_code_not_asserted_by_test_is_rejected(self):
        coverage = self.mutated()
        entry = next(t for t in coverage["rules"]["SYN-04"]["tests"] if t.get("code"))
        entry["code"] = "E999"
        self.rejects(coverage, "does not assert E999")

    def test_code_on_positive_test_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["SYN-04"]["tests"][0]["code"] = "E100"
        self.rejects(coverage, "a code belongs to a negative test")

    def test_invalid_polarity_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["SYN-04"]["tests"][0]["polarity"] = "both"
        self.rejects(coverage, "polarity must be positive or negative")

    def test_invented_issue_reference_form_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["D0-AWAIT-1"]["pending"]["issue"] = "TBD"
        self.rejects(coverage, "pending issue must be quaat/weave#N or null")

    def test_pending_without_reason_is_rejected(self):
        coverage = self.mutated()
        coverage["rules"]["D0-AWAIT-1"]["pending"]["reason"] = " "
        self.rejects(coverage, "nonempty 'reason'")

    def test_unknown_format_is_rejected(self):
        coverage = self.mutated()
        coverage["format"] = "weave-rule-coverage-v2"
        self.rejects(coverage, "Unsupported coverage format")

    def test_stale_page_is_detected(self):
        rows = validate(self.rules, self.manifest, self.coverage)
        coverage = self.mutated()
        coverage["rules"]["SYN-04"]["tests"].pop()
        self.assertNotEqual(render(rows), render(validate(self.rules, self.manifest, coverage)))


if __name__ == "__main__":
    unittest.main()
