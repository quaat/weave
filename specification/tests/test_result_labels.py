# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Result labels in tool output (quaat/weave#8): the policy in verification.rst and its lint.

The seven labels of the Result vocabulary table are the closed set of result labels;
CHECKED pure (quaat/weave#10) joined the six that the evidence envelope schema and the
agent kit's label lint use. The specification's own evidence,
``validation/report.json``, is wrapped in envelopes and linted: each envelope carries
exactly one claim, at ``claim_label``, with one of the six labels. The agent kit's
``tests/test_result_labels.py`` runs the same lint on every runner command.
"""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
CHAPTERS = ROOT / "docs/chapters"
KIT_SCRIPTS = REPO / "agent-kit/.agents/skills/weave/scripts"
HAVE_KIT = (KIT_SCRIPTS / "weave_labels.py").is_file()
HAVE_EVIDENCE = (REPO / "evidence/weave_evidence/wrap.py").is_file()
sys.dont_write_bytecode = True
for path in (REPO, KIT_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def chapter(name: str) -> str:
    return (CHAPTERS / f"{name}.rst").read_text(encoding="utf-8")


def table_labels() -> tuple:
    table = chapter("verification").split("Result vocabulary", 1)[1].split("Result labels in tool output", 1)[0]
    return tuple(m for m in re.findall(r"(?m)^   \* - (.+)$", table) if m != "Label")


def policy() -> str:
    text = chapter("verification").split("Result labels in tool output\n", 1)[1]
    return " ".join(text.split("Aggregate invariants\n", 1)[0].split())


class LabelPolicyTests(unittest.TestCase):
    def test_table_has_exactly_seven_labels(self):
        self.assertEqual(table_labels(), ("PROVED", "CHECKED WITHIN BOUNDS", "CHECKED flow", "CHECKED pure",
                                          "SCRIPTED / passed scenario", "VIOLATED", "NOT ESTABLISHED"))

    def test_policy_section_states_each_rule(self):
        text = policy()
        for phrase in ("A label attaches to an individual claim",
                       "Runtime status is not evidence.",
                       "``waiting``, ``timed out`` or ``completed``",
                       "It is never equated with NOT ESTABLISHED, which is an evidence result",
                       "Prototype console lines are raw tool output.",
                       "``PASSED``, ``RECHECKED``, bare ``CHECKED`` lines and ``NOT PROVED``"):
            self.assertIn(phrase, text)

    def test_policy_is_cross_referenced(self):
        for name in ("stability", "design-history"):
            text = chapter(name)
            with self.subTest(name):
                self.assertTrue("chapters/verification:Result labels in tool output" in text
                                or ":doc:`verification`" in text, name)
        self.assertIn(":ref:`chapters/verification:Result labels in tool output`", chapter("stability"))
        self.assertIn("quaat/weave#8", chapter("design-history"))

    @unittest.skipUnless(HAVE_KIT and HAVE_EVIDENCE, "the agent kit and evidence package are not next to the specification")
    def test_lint_and_schema_use_the_table(self):
        from weave_labels import RESULT_LABELS, RUNTIME_STATUSES
        from evidence.weave_evidence import documents, schema
        self.assertEqual(RESULT_LABELS, table_labels())
        envelope = schema.load(documents.SCHEMA_FILES[documents.ENVELOPE])
        # weave-evidence-envelope-v1 predates CHECKED pure (quaat/weave#10); wrapping a P0 claim
        # in an envelope needs the next envelope version.
        self.assertEqual(tuple(envelope["properties"]["claim_label"]["enum"]),
                         tuple(label for label in table_labels() if label != "CHECKED pure"))
        self.assertEqual(tuple(envelope["properties"]["runtime_status"]["enum"]), RUNTIME_STATUSES + (None,))


@unittest.skipUnless(HAVE_KIT and HAVE_EVIDENCE, "the agent kit and evidence package are not next to the specification")
class ReportEnvelopeLintTests(unittest.TestCase):
    """The specification's validation report, wrapped, names its claims only with the six labels."""

    @classmethod
    def setUpClass(cls):
        from evidence.weave_evidence.wrap import wrap
        cls.envelopes = wrap(REPO, "specification/validation/report.json").envelopes

    def test_each_envelope_has_one_claim_with_a_label(self):
        from weave_labels import json_claims, lint_json
        self.assertTrue(self.envelopes)
        for envelope in self.envelopes:
            with self.subTest(envelope["claim"]["pointer"]):
                self.assertEqual(lint_json(envelope), [])
                self.assertEqual([p for p, _ in json_claims(envelope)], ["/claim_label"])

    def test_lint_fails_on_other_labels(self):
        from weave_labels import lint_json, lint_text
        envelope = self.envelopes[0]
        for change in ({"claim_label": "PASSED"}, {"claim_label": "NOT PROVED"}, {"claim_label": "CHECKED"},
                       {"runtime_status": "Unknown"}, {"status": "PROVED"}, {"check": "CHECKED"},
                       {"claim": dict(envelope["claim"], statement="PASSED")}):
            with self.subTest(change=change):
                self.assertEqual(len(lint_json(dict(envelope, **change))), 1)
        for line in ("PASSED 6 crash scenarios", "NOT PROVED stock_conservation", "CHECKED checkout_propagating:"):
            with self.subTest(line=line):
                self.assertEqual(len(lint_text(line)), 1)
        self.assertEqual(lint_text("CHECKED flow valid/checkout.weave: checkout"), [])


if __name__ == "__main__":
    unittest.main()
