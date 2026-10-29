# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Every envelope records the conditions its label carries, and every file its producer uses.

Assumptions: for each wrapper and label, the expected conditions are listed here,
independently of conditions.py, as (file, section, phrase) taken from the cited
specification lines or producer docstring. Each phrase must occur in that section
and in an assumption of every envelope of that kind that cites the same section.

Dependencies: each producer is run on a copy of the repository under an audit hook
(trace_reads.py); the files it opens for reading, including imported modules, must
equal the envelope's sources plus dependencies.
"""
import ast
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from evidence.weave_evidence.conditions import CONDITIONS
from evidence.weave_evidence.wrap import wrap_all

from .support import ROOT, repo_copy

V = "specification/docs/chapters/verification.rst"
S = "specification/docs/chapters/security.rst"
R = "specification/docs/chapters/runtime.rst"
ST = "specification/docs/chapters/status.rst"
SEC_MODEL = "SEC-MODEL-1 — Trusted specifications and artifacts"
SEC_EVIDENCE = "SEC-EVIDENCE-1 — Authentication and correlation"
TRUSTED = "Proof artifacts and trusted components"

# security.rst SEC-MODEL-1 lines 60-61; verification.rst lines 171-173.
TRUST = [
    (S, SEC_MODEL, "parser/model translation, and the Python checker are trusted components"),
    (V, TRUSTED, "source-to-model translation, and execution runtime remain trusted components"),
    (V, TRUSTED, "No soundness, progress, termination, or compiler-refinement theorem has been machine-checked here"),
]
# verification.rst lines 115-119; security.rst line 27.
GUARDS = [
    (V, "Safety properties", "Other guards are abstract nondeterministic enablers"),
    (V, "Safety properties", "Witnesses never reset"),
    (V, "Safety properties", "Provider consistency is an explicit external assumption"),
    (S, SEC_EVIDENCE, "The current analyser assumes guard truthfulness and correlation"),
]
INVARIANT = [  # verification.rst lines 44-46 and 54-56
    (V, "Aggregate invariants", "every finite firing sequence and every nonnegative initial stock under the net model"),
    (V, "Aggregate invariants", "an invariant is not a reachability proof, a correlation proof, or evidence that payment guards are truthful"),
]
SIMULATION = [  # verification.rst line 24; runtime.rst lines 9-15; simulate.py docstring
    (V, "Result vocabulary", "A selected concrete execution or injected crash case satisfied assertions"),
    (R, "Two execution paths", "Neither is a general production runtime"),
    (R, "Two execution paths", "stock is one, and at most one foreign operation is allowed per scenario"),
    (R, "Two execution paths", "It does not drain the adapter request queue"),
]
REQUIRED = {
    ("inventory-proof/proof.json", "/invariants/"): [
        (V, "Result vocabulary", "Exact integer invariant obligations discharged for the parsed transition system"),
        *INVARIANT,
        (V, TRUSTED, "It shares the parser and expression reader; it is not an independent proof assistant"),
        ("inventory-proof/checker.py", "module docstring", "PROVED labels apply only to exact integer linear invariants"),
        ("inventory-proof/verify_certificate.py", "module docstring", "The parser, Python integer semantics, and the standard place-invariant induction rule are trusted"),
        *TRUST,
    ],
    ("inventory-proof/ordering.json", "/properties/"): [
        (V, "Result vocabulary", "Complete finite exploration at explicit colours, stock, token bounds, state budget, and guard abstraction"),
        (V, "One-order model: N0", "N0 fixes stock to one, allows at most one admission"),
        (V, "One-order model: N0", "N0 does not prove arbitrary admission uniqueness"),
        *GUARDS,
        ("inventory-proof/checker.py", "explore_order docstring", "their false branch is stuttering"),
        (V, "Coloured model: N1", "A property whose premise never occurs may hold vacuously"),
        *TRUST,
    ],
    ("inventory-proof/colour-proof.json", "/aggregate/"): [
        (V, "Result vocabulary", "Exact integer invariant obligations discharged for the parsed transition system"),
        *INVARIANT,
        (V, "Aggregate invariants", "In N1, a bare indexed-place name in an aggregate expression denotes its total over colours"),
        (V, TRUSTED, "has no independent formal verifier in this snapshot"),
        ("inventory-proof/coloured.py", "module docstring", "variable-only inscriptions, no arbitrary ML expressions"),
        *TRUST,
    ],
    ("inventory-proof/colour-proof.json", "/families/"): [
        (V, "Result vocabulary", "Exact integer invariant obligations discharged for the parsed transition system"),
        (V, "Invariant families", "restricted variable-only inscription fragment"),
        (V, "Invariant families", "richer colour expressions are not implemented"),
        (V, "Invariant families", "require the separate token-correlation check"),
        (V, TRUSTED, "has no independent formal verifier in this snapshot"),
        *TRUST,
    ],
    ("inventory-proof/colour-check.json", "/properties/"): [
        (V, "Result vocabulary", "Complete finite exploration at explicit colours, stock, token bounds, state budget, and guard abstraction"),
        (V, "Coloured model: N1", "one tenant with ``orders N`` distinct orders"),
        (V, "Coloured model: N1", "Each indexed cell is bounded by ``place_bound``"),
        (V, "Coloured model: N1", "It does not establish an arbitrary-order cutoff theorem"),
        *GUARDS,
        (V, "Coloured model: N1", "A property whose premise never occurs may hold vacuously"),
        *TRUST,
    ],
    ("inventory-proof/scenarios.json", "/"): [
        *SIMULATION,
        ("inventory-proof/simulate.py", "module docstring", "It is not a durable runtime, provider adapter, or proof of compiler/runtime refinement"),
        *TRUST,
    ],
    ("inventory-proof/durable-scenarios.json", "/"): [
        (V, "Result vocabulary", "A selected concrete execution or injected crash case satisfied assertions"),
        (R, "Two execution paths", "Neither is a general production runtime"),
        (R, "Two execution paths", "It does not execute an arbitrary F0 continuation"),
        (R, "Evidence and duplicate handling", "does not establish a real provider's retention or authentication behaviour"),
        (R, "Limits", "The recovery policy uses a concrete two-attempt budget"),
        (R, "Limits", "They do not prove behaviour under physical power loss"),
        (R, "Limits", "Liveness and general durable scheduling remain unestablished"),
        (S, SEC_EVIDENCE, "R0 checks scripted receipt identity but does not implement webhook signature verification"),
        ("inventory-proof/durable.py", "module docstring", "No real payment, network, or service is contacted"),
        *TRUST,
    ],
    ("specification/validation/report.json", "/cases/"): [
        (V, "Result vocabulary", "F0 type, identity, move, return, and exhaustiveness checks passed"),
        (ST, "Scope", "Accepting an F0 program does not establish that every operation is enabled"),
        *TRUST,
    ],
    ("specification/validation/report.json", "/counterexamples/0"): [
        (V, "Result vocabulary", "A modeled counterexample was found"),
        (V, "One-order model: N0", "a violating trace MUST report E320"),
        (V, "One-order model: N0", "N0 fixes stock to one, allows at most one admission"),
        (V, "Safety properties", "Other guards are abstract nondeterministic enablers"),
        *TRUST,
    ],
    ("specification/validation/report.json", "/counterexamples/1"): [
        (V, "Result vocabulary", "A modeled counterexample was found"),
        (V, "Coloured model: N1", "one tenant with ``orders N`` distinct orders"),
        (V, "Coloured model: N1", "Correlation is checked for all enabled modes"),
        (V, "Safety properties", "Other guards are abstract nondeterministic enablers"),
        *TRUST,
    ],
    ("specification/validation/report.json", "/scenarios/"): [
        *SIMULATION,
        ("specification/reference/prototype/simulate.py", "module docstring", "It is not a durable runtime, provider adapter, or proof of compiler/runtime refinement"),
        *TRUST,
    ],
}


def normal(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def section_text(path: str, section: str) -> str:
    """The text of a reStructuredText section, or a module or function docstring."""
    source = (ROOT / path).read_text(encoding="utf-8")
    if section.endswith("docstring"):
        tree = ast.parse(source)
        if section == "module docstring":
            return normal(ast.get_docstring(tree))
        name = section.split()[0]
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
        return normal(ast.get_docstring(node))
    lines = source.splitlines()
    underline = re.compile(r"^([=\-~^])\1{2,}$")
    starts = [i for i in range(len(lines) - 1) if lines[i].strip() and underline.match(lines[i + 1])]
    index = [i for i in starts if lines[i].strip() == section]
    if len(index) != 1:
        raise AssertionError(f"{path}: section {section!r} found {len(index)} times")
    following = [i for i in starts if i > index[0]]
    end = following[0] if following else len(lines)
    return normal("\n".join(lines[index[0] + 2:end]))


class QuotationTests(unittest.TestCase):
    def test_every_condition_is_quoted_verbatim_from_its_cited_section(self):
        for key, (path, section, quote) in CONDITIONS.items():
            with self.subTest(key=key):
                self.assertIn(normal(quote), section_text(path, section))

    def test_every_required_phrase_occurs_in_its_cited_section(self):
        for phrases in REQUIRED.values():
            for path, section, phrase in phrases:
                with self.subTest(path=path, phrase=phrase):
                    self.assertIn(normal(phrase), section_text(path, section))


class RequiredAssumptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {r.path: r for r in wrap_all(ROOT)}

    def envelopes(self, rel, prefix):
        found = [e for e in self.results[rel].envelopes if e["claim"]["pointer"].startswith(prefix)]
        self.assertTrue(found, (rel, prefix))
        return found

    def check(self, rel, prefix):
        for envelope in self.envelopes(rel, prefix):
            for path, section, phrase in REQUIRED[(rel, prefix)]:
                citation = f"[{path}, {section}]"
                matches = [a for a in envelope["assumptions"] if a.endswith(citation) and normal(phrase) in normal(a)]
                self.assertTrue(matches, f"{rel}{envelope['claim']['pointer']}: no assumption quoting {phrase!r} {citation}")

    def test_place_invariant_envelopes(self):
        self.check("inventory-proof/proof.json", "/invariants/")

    def test_one_order_envelopes(self):
        self.check("inventory-proof/ordering.json", "/properties/")
        original = json.loads((ROOT / "inventory-proof/ordering.json").read_text())["assumptions"]
        for envelope in self.envelopes("inventory-proof/ordering.json", "/properties/"):
            self.assertEqual(envelope["assumptions"][:len(original)], original)

    def test_colour_invariant_envelopes(self):
        self.check("inventory-proof/colour-proof.json", "/aggregate/")
        self.check("inventory-proof/colour-proof.json", "/families/")

    def test_colour_exploration_envelopes(self):
        self.check("inventory-proof/colour-check.json", "/properties/")

    def test_simulation_envelopes(self):
        self.check("inventory-proof/scenarios.json", "/")

    def test_crash_case_envelopes(self):
        self.check("inventory-proof/durable-scenarios.json", "/")

    def test_specification_report_envelopes(self):
        for rel, prefix in REQUIRED:
            if rel == "specification/validation/report.json":
                self.check(rel, prefix)

    def test_every_envelope_has_a_scope(self):
        for result in self.results.values():
            for envelope in result.envelopes:
                self.assertTrue(envelope["scope"], (result.path, envelope["claim"]["pointer"]))


class ProducerDependencyTests(unittest.TestCase):
    """The files each producer opens, observed by running it, equal sources plus dependencies."""

    @classmethod
    def setUpClass(cls):
        cls.root = repo_copy()
        cls.results = {r.path: r for r in wrap_all(ROOT)}
        cls.observed = {}
        for script in ("inventory-proof/demo.py", "specification/scripts/validate.py"):
            run = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("trace_reads.py")), str(cls.root), script],
                                 capture_output=True, text=True, timeout=300)
            if run.returncode != 0:
                raise AssertionError(f"{script} failed under the tracer:\n{run.stderr}")
            cls.observed[script] = set(json.loads(run.stdout.strip().splitlines()[-1]))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def recorded(self, envelope) -> set:
        return {f["path"] for f in envelope["sources"] + envelope["dependencies"]}

    def check(self, rel, script, extra=lambda envelope: set()):
        observed = self.observed[script]
        self.assertIn(script, observed)
        for envelope in self.results[rel].envelopes:
            with self.subTest(rel=rel, pointer=envelope["claim"]["pointer"]):
                self.assertEqual(self.recorded(envelope), observed | extra(envelope))

    def test_place_invariant_dependencies(self):
        self.check("inventory-proof/proof.json", "inventory-proof/demo.py")

    def test_one_order_dependencies(self):
        self.check("inventory-proof/ordering.json", "inventory-proof/demo.py")

    def test_colour_invariant_dependencies(self):
        self.check("inventory-proof/colour-proof.json", "inventory-proof/demo.py")

    def test_colour_exploration_dependencies(self):
        self.check("inventory-proof/colour-check.json", "inventory-proof/demo.py")

    def test_simulation_dependencies(self):
        self.check("inventory-proof/scenarios.json", "inventory-proof/demo.py")

    def test_crash_case_dependencies(self):
        self.check("inventory-proof/durable-scenarios.json", "inventory-proof/demo.py")

    def test_specification_report_dependencies(self):
        # A VIOLATED envelope also depends on the counterexample text it reads its trace from,
        # which validate.py writes rather than reads.
        self.check("specification/validation/report.json", "specification/scripts/validate.py",
                   lambda e: {e["claim"]["detail"]["counterexample"]} if e["claim_label"] == "VIOLATED" else set())

    def test_named_omissions_are_now_dependencies(self):
        proof = self.results["inventory-proof/proof.json"].envelopes[0]
        self.assertIn("inventory-proof/verify_certificate.py", self.recorded(proof))
        report = self.results["specification/validation/report.json"].envelopes[0]
        self.assertIn("specification/PROVENANCE.json", self.recorded(report))


if __name__ == "__main__":
    unittest.main()
