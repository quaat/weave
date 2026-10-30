# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""The grammar audit (quaat/weave#9): probes, the discrepancy table and the Rust differential.

``scripts/grammar_audit.py`` compares the generated Lark parser with the reference
checker on the corpus and on syntax probes, and, when the ``weave-syntax`` binary can
be built or is named, with the grammar-driven Rust parser. These tests keep the
grammar chapter's discrepancy table equal to the audited probes and check that a
missing Rust toolchain is reported as not established, never as agreement.
"""
from pathlib import Path
import os
import re
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import grammar_audit  # noqa: E402


def table_rows() -> list[tuple[str, str, str]]:
    text = (ROOT / "docs/chapters/grammar.rst").read_text(encoding="utf-8")
    section = text.split("Reference parser discrepancies\n", 1)[1].split("\n\n\n", 1)[0]
    rows = re.findall(r"(?m)^   \* - (S[DA]-\d+)\n     - .+(?:\n       .+)*\n     - (\w+)\n     - (\w+)$", section)
    return [tuple(row) for row in rows]


class GrammarAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = grammar_audit.parser()[0]
        cls.net = grammar_audit.parse_net((ROOT / "examples/nets/Inventory.weave").read_text(encoding="utf-8"))

    def test_discrepancy_table_lists_every_probe_with_its_verdicts(self):
        documented = [(pid, ref, ebnf) for pid, _, _, ref, ebnf, _ in grammar_audit.PROBES]
        self.assertEqual(table_rows(), documented)
        self.assertTrue(any(ref != ebnf for _, ref, ebnf in documented))
        self.assertTrue(any(ref == ebnf for _, ref, ebnf in documented))

    def test_probes_have_their_documented_verdicts(self):
        for pid, start, source, want_ref, want_ebnf, _ in grammar_audit.PROBES:
            with self.subTest(pid):
                self.assertEqual(grammar_audit.probe_reference(source, start, self.net), want_ref)
                self.assertEqual(grammar_audit.syntax(self.parser, source, start)[0], want_ebnf)

    def test_layout_faults_map_to_e001_and_words_end_at_boundaries(self):
        skipped = (ROOT / "examples/invalid/skipped_level.weave").read_text(encoding="utf-8")
        self.assertEqual(grammar_audit.syntax(self.parser, skipped, "flow-file"), ("REJECT", "E001"))
        unsupported = (ROOT / "examples/invalid/unsupported_if.weave").read_text(encoding="utf-8")
        self.assertEqual(grammar_audit.syntax(self.parser, unsupported, "flow-file"), ("REJECT", "E200"))
        for glued in ("flowf():\n    return\n", "flow f():\n    letx = g()\n    return\n"):
            self.assertEqual(grammar_audit.syntax(self.parser, glued, "flow-file")[0], "REJECT", glued)
        net = "net N(s: Nat):\n    transition t:\n        take 1abc\n"
        self.assertEqual(grammar_audit.syntax(self.parser, net, "n0-file"), ("REJECT", "E003"))
        self.assertEqual(grammar_audit.syntax(self.parser, "flow f():\r\n    return\r\n", "flow-file")[0], "ACCEPT")
        self.assertEqual(grammar_audit.syntax(self.parser, "flow f():\r    return\n", "flow-file")[0], "REJECT")

    def test_rust_comparison_without_cargo_is_not_established(self):
        env = {k: v for k, v in os.environ.items() if k != "WEAVE_SYNTAX_BIN"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(grammar_audit.shutil, "which", return_value=None):
            result = grammar_audit.rust_differential([("x", "flow-file", "flow f():\n    return\n", "ACCEPT", None)])
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["compared"], 0)
        self.assertIn("not established", result["note"])
        self.assertNotIn("agreements", result)

    def test_a_named_binary_must_exist(self):
        with mock.patch.dict(os.environ, {"WEAVE_SYNTAX_BIN": str(ROOT / "no-such-binary")}):
            with self.assertRaises(FileNotFoundError):
                grammar_audit.rust_differential([])

    @unittest.skipIf(os.name == "nt", "the stand-in binary is a POSIX shell script")
    def test_a_disagreeing_rust_verdict_fails_the_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "weave-syntax"
            fake.write_text("#!/bin/sh\ncat >/dev/null\nexit 0\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with mock.patch.dict(os.environ, {"WEAVE_SYNTAX_BIN": str(fake)}):
                agree = grammar_audit.rust_differential([("ok", "flow-file", "", "ACCEPT", None)])
                self.assertEqual((agree["status"], agree["compared"], agree["agreements"]), ("compared", 1, 1))
                with self.assertRaises(AssertionError):
                    grammar_audit.rust_differential([("bad", "flow-file", "", "REJECT", "E200")])


if __name__ == "__main__":
    unittest.main()
