# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""AC-3: existing evidence files are wrapped and the originals are unchanged.
AC-4: every envelope records source and dependency hashes that recompute."""
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from evidence.weave_evidence import __main__ as cli
from evidence.weave_evidence import __version__
from evidence.weave_evidence.documents import RESULT_LABELS, assess, canonical_bytes, verify_hashes
from evidence.weave_evidence.traces import ConversionError
from evidence.weave_evidence.wrap import WRAPPERS, wrap, wrap_all

from .support import ALL_FILES, ISSUE_FILES, ROOT, repo_copy

SCRIPTED = "SCRIPTED / passed scenario"
EXPECTED_LABELS = {
    "inventory-proof/proof.json": {"PROVED": 2},
    "inventory-proof/ordering.json": {"CHECKED WITHIN BOUNDS": 9},
    "inventory-proof/colour-proof.json": {"PROVED": 5},
    "inventory-proof/colour-check.json": {"CHECKED WITHIN BOUNDS": 11},
    "inventory-proof/scenarios.json": {SCRIPTED: 3},
    "inventory-proof/durable-scenarios.json": {SCRIPTED: 6},
    "specification/validation/report.json": {"CHECKED flow": 8, "VIOLATED": 2, SCRIPTED: 3},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer_get(document, pointer: str):
    for part in pointer.split("/")[1:]:
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


class WrapRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {rel: sha(ROOT / rel) for rel in ALL_FILES}
        cls.results = {r.path: r for r in wrap_all(ROOT)}

    def test_every_named_file_has_a_wrapper(self):
        self.assertEqual(sorted(WRAPPERS), sorted(ALL_FILES))
        for rel in ISSUE_FILES:
            self.assertTrue(self.results[rel].envelopes, rel)

    def test_every_envelope_and_trace_is_accepted(self):
        for rel, result in self.results.items():
            for document in result.envelopes + result.traces:
                outcome = assess(document)
                self.assertTrue(outcome.accepted, (rel, outcome.errors))

    def test_claim_labels_per_file(self):
        for rel, expected in EXPECTED_LABELS.items():
            self.assertEqual(Counter(e["claim_label"] for e in self.results[rel].envelopes), Counter(expected), rel)
        for result in self.results.values():
            for env in result.envelopes:
                self.assertIn(env["claim_label"], RESULT_LABELS)
                self.assertIsNone(env["runtime_status"], "the existing files record no runtime status")

    def test_labels_copied_from_original_status_fields(self):
        for rel in ("inventory-proof/proof.json", "inventory-proof/ordering.json", "inventory-proof/colour-proof.json"):
            original = json.loads((ROOT / rel).read_text())
            for env in self.results[rel].envelopes:
                entry = pointer_get(original, env["claim"]["pointer"])
                self.assertEqual(env["claim_label"], entry["status"])
                self.assertEqual(env["claim"]["name"], entry["name"])

    def test_each_claim_pointer_resolves_in_the_wrapped_file(self):
        for rel, result in self.results.items():
            original = json.loads((ROOT / rel).read_text())
            for env in result.envelopes:
                self.assertEqual(env["wrapped"]["path"], rel)
                pointer_get(original, env["claim"]["pointer"])

    def test_report_parts_without_a_label_are_listed_not_wrapped(self):
        report = self.results["specification/validation/report.json"]
        self.assertEqual([p for p, _ in report.not_wrapped],
                         [f"/cases/{i}" for i in range(8, 25)] + ["/reference_integrity", "/lease", "/n0", "/n1"])
        for rel, result in self.results.items():
            if rel != "specification/validation/report.json":
                self.assertEqual(result.not_wrapped, [], rel)

    def test_application_unknown_is_never_an_evidence_label(self):
        simulations = self.results["inventory-proof/scenarios.json"]
        unknown = [e for e in simulations.envelopes if e["claim"]["detail"]["scripted_outcome"] == "Unknown"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["claim_label"], SCRIPTED)
        self.assertEqual([t["outcome"] for t in simulations.traces], ["Ok", "Err", "Unknown"])
        durable = self.results["inventory-proof/durable-scenarios.json"]
        states = {r["state"] for t in durable.traces for r in t["context"]["results"]}
        self.assertIn("Unknown", states)
        self.assertEqual({e["claim_label"] for e in durable.envelopes}, {SCRIPTED})

    def test_bounds_and_completeness_recorded_for_bounded_claims(self):
        ordering = self.results["inventory-proof/ordering.json"].envelopes[0]
        self.assertEqual(ordering["bounds"]["max_states"], 10000)
        self.assertEqual(ordering["completeness"], {"complete": True, "states": 20, "edges": 43, "unreached_transitions": []})
        self.assertEqual(len(ordering["assumptions"]), 4)
        colour = self.results["inventory-proof/colour-check.json"].envelopes[0]
        self.assertEqual((colour["completeness"]["states"], colour["completeness"]["edges"]), (841, 3712))
        self.assertEqual(colour["bounds"]["orders"], 2)

    def test_originals_are_unchanged(self):
        self.assertEqual({rel: sha(ROOT / rel) for rel in ALL_FILES}, self.before)
        if shutil.which("git") and (ROOT / ".git").exists():
            subprocess.run(["git", "diff", "--exit-code", "--quiet", "--", *ALL_FILES], cwd=ROOT, check=True)

    # ------------------------------------------------------------- AC-4

    def test_every_envelope_records_source_and_dependency_hashes_that_recompute(self):
        for rel, result in self.results.items():
            for env in result.envelopes:
                self.assertTrue(env["sources"], rel)
                self.assertTrue(env["dependencies"], rel)
                self.assertEqual(env["wrapped"]["sha256"], sha(ROOT / rel))
                for entry in env["sources"] + env["dependencies"]:
                    self.assertEqual(entry["sha256"], sha(ROOT / entry["path"]), entry["path"])
                self.assertEqual(verify_hashes(env, ROOT), [])

    def test_embedded_source_hash_matches_the_recorded_source(self):
        for rel in ("inventory-proof/proof.json", "inventory-proof/ordering.json",
                    "inventory-proof/colour-proof.json", "inventory-proof/colour-check.json"):
            original = json.loads((ROOT / rel).read_text())
            for env in self.results[rel].envelopes:
                self.assertEqual([s["sha256"] for s in env["sources"]], [original["source_sha256"]])

    def test_trace_hashes_recompute(self):
        for result in self.results.values():
            hashes = {hashlib.sha256(canonical_bytes(t)).hexdigest() for t in result.traces}
            linked = {e["trace"]["sha256"] for e in result.envelopes if e["trace"]}
            self.assertEqual(linked, hashes)

    def test_tool_versions_and_supported_profiles_recorded_separately(self):
        for result in self.results.values():
            for env in result.envelopes:
                tools = {t["name"]: t for t in env["tools"]}
                self.assertEqual(tools["evidence/weave_evidence"]["version"], __version__)
                for name, tool in tools.items():
                    if name.endswith("prototype/checker.py") or name == "inventory-proof/checker.py":
                        self.assertEqual(tool["version"], "3", "working copy matches the pinned snapshot")
                        self.assertEqual(tool["supported_profiles"], ["F0", "N0"])
                self.assertNotIn("supported_profiles", env["profiles"][0])
        durable = self.results["inventory-proof/durable-scenarios.json"].envelopes[0]
        self.assertEqual([p["name"] for p in durable["profiles"]], ["R0"])
        self.assertIn("R0", {p for t in durable["tools"] for p in t["supported_profiles"]})


class TamperTests(unittest.TestCase):
    """Wrapping and verification in a temporary copy; the repository files are not touched."""

    def setUp(self):
        self.root = repo_copy()
        self.addCleanup(shutil.rmtree, self.root)

    def edit_json(self, rel, change):
        path = self.root / rel
        document = json.loads(path.read_text())
        change(document)
        path.write_text(json.dumps(document))

    def test_changed_dependency_or_source_is_detected(self):
        env = wrap(self.root, "inventory-proof/proof.json").envelopes[0]
        self.assertEqual(verify_hashes(env, self.root), [])
        with open(self.root / "inventory-proof/demo.py", "a") as handle:
            handle.write("\n# changed\n")
        self.assertEqual(verify_hashes(env, self.root), ["dependencies: inventory-proof/demo.py does not hash to the recorded sha256"])
        (self.root / "inventory-proof/Inventory.weave").unlink()
        self.assertIn("sources: inventory-proof/Inventory.weave is missing", verify_hashes(env, self.root))

    def test_changed_wrapped_file_is_detected(self):
        env = wrap(self.root, "inventory-proof/scenarios.json").envelopes[0]
        with open(self.root / "inventory-proof/scenarios.json", "a") as handle:
            handle.write(" ")
        self.assertEqual(verify_hashes(env, self.root), ["wrapped: inventory-proof/scenarios.json does not hash to the recorded sha256"])

    def test_source_that_does_not_match_the_embedded_hash_is_refused(self):
        with open(self.root / "inventory-proof/Inventory.weave", "a") as handle:
            handle.write("\n")
        for rel in ("inventory-proof/proof.json", "inventory-proof/ordering.json"):
            with self.assertRaisesRegex(ConversionError, "source_sha256 does not match"):
                wrap(self.root, rel)

    def test_unexpected_status_values_are_refused(self):
        cases = [
            ("inventory-proof/proof.json", lambda d: d["invariants"][0].update(status="NOT PROVED")),
            ("inventory-proof/ordering.json", lambda d: d["properties"][0].update(status="PASSED")),
            ("inventory-proof/colour-proof.json", lambda d: d["families"][0].update(status="CHECKED")),
            ("inventory-proof/durable-scenarios.json", lambda d: d[0].update(status="FAILED")),
        ]
        for rel, change in cases:
            with self.subTest(rel=rel):
                self.edit_json(rel, change)
                with self.assertRaisesRegex(ConversionError, "status"):
                    wrap(self.root, rel)

    def test_incomplete_exploration_is_not_established(self):
        self.edit_json("inventory-proof/colour-check.json", lambda d: d.update(complete=False))
        result = wrap(self.root, "inventory-proof/colour-check.json")
        self.assertEqual({e["claim_label"] for e in result.envelopes}, {"NOT ESTABLISHED"})
        self.assertTrue(all(assess(e).accepted for e in result.envelopes))

    def test_modified_prototype_module_has_no_version(self):
        with open(self.root / "inventory-proof/checker.py", "a") as handle:
            handle.write("\n")
        env = wrap(self.root, "inventory-proof/proof.json").envelopes[0]
        tools = {t["name"]: t for t in env["tools"]}
        self.assertIsNone(tools["inventory-proof/checker.py"]["version"])
        self.assertEqual(tools["inventory-proof/demo.py"]["version"], "3")

    def test_unknown_file_has_no_wrapper(self):
        with self.assertRaisesRegex(ConversionError, "no wrapper"):
            wrap(self.root, "agent-kit/demos/tiny_shop/artifacts/scenarios.json")


class CommandLineWrapTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out)

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            return cli.main(list(argv)), buffer.getvalue()

    def test_wrap_then_verify(self):
        code, out = self.run_cli("wrap", "--out", str(self.out))
        self.assertEqual(code, 0, out)
        envelopes = sorted((self.out / "envelopes").glob("*.json"))
        self.assertEqual(len(envelopes), sum(sum(c.values()) for c in EXPECTED_LABELS.values()))
        code, out = self.run_cli("validate", *map(str, envelopes), *map(str, (self.out / "traces").glob("*.json")))
        self.assertEqual(code, 0, out)
        code, out = self.run_cli("verify", *map(str, envelopes))
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("hashes recompute"), len(envelopes))

    def test_verify_detects_a_changed_trace(self):
        self.assertEqual(self.run_cli("wrap", "--out", str(self.out), "inventory-proof/scenarios.json")[0], 0)
        trace = sorted((self.out / "traces").glob("*.json"))[0]
        document = json.loads(trace.read_text())
        document["outcome"] = "Err" if document["outcome"] != "Err" else "Ok"
        trace.write_bytes(canonical_bytes(document))
        code, out = self.run_cli("verify", *map(str, (self.out / "envelopes").glob("*.json")))
        self.assertEqual(code, 1)
        self.assertIn("does not hash to the recorded sha256", out)


if __name__ == "__main__":
    unittest.main()
