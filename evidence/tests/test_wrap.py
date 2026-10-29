# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""AC-3: existing evidence files are wrapped and the originals are unchanged.
AC-4: every envelope records source and dependency hashes that recompute."""
import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from evidence.weave_evidence import __main__ as cli
from evidence.weave_evidence import __version__
from evidence.weave_evidence.documents import RESULT_LABELS, assess, canonical_bytes, verify_hashes
from evidence.weave_evidence.traces import ConversionError
from evidence.weave_evidence.wrap import SUPPORTED_PROFILES, WRAPPERS, rederive, wrap, wrap_all

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
        original = json.loads((ROOT / "inventory-proof/ordering.json").read_text())["assumptions"]
        self.assertEqual(ordering["assumptions"][:4], original)
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
                        self.assertEqual(tool["supported_profiles"], ["F0", "N0", "N1"])
                self.assertNotIn("supported_profiles", env["profiles"][0])
        durable = self.results["inventory-proof/durable-scenarios.json"].envelopes[0]
        self.assertEqual([p["name"] for p in durable["profiles"]], ["R0"])
        self.assertIn("R0", {p for t in durable["tools"] for p in t["supported_profiles"]})


def status_reference_table() -> dict[str, list[str]]:
    """Module -> profiles, from the Reference column of the profile table in status.rst."""
    text = (ROOT / "specification/docs/chapters/status.rst").read_text(encoding="utf-8")
    table = text.split("   * - Profile\n", 1)[1].split("\n\n", 1)[0]
    modules: dict[str, list[str]] = {}
    for profile, _coverage, reference in re.findall(r"   \* - (\w+)\n     - (.+)\n     - (.+)", table):
        for module in re.findall(r"``(\w+\.py)``", reference):
            modules.setdefault(module, []).append(profile)
    return modules


class SupportedProfileSourceTests(unittest.TestCase):
    def test_supported_profiles_match_the_status_reference_column(self):
        table = status_reference_table()
        self.assertEqual(table, {"checker.py": ["F0", "N0", "N1"], "coloured.py": ["N1"], "durable.py": ["R0"]})
        self.assertEqual(SUPPORTED_PROFILES, table)


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


class VerifyRederivationTests(unittest.TestCase):
    """Item: verify re-derives each envelope from its original and compares every field."""

    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp())
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            assert cli.main(["wrap", "--out", str(cls.out), "inventory-proof/ordering.json"]) == 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out)

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            return cli.main(list(argv)), buffer.getvalue()

    def tampered(self, change) -> Path:
        source = sorted((self.out / "envelopes").glob("*.json"))[0]
        envelope = json.loads(source.read_text())
        change(envelope)
        self.assertTrue(assess(envelope).accepted, "the tampered envelope is still schema-valid")
        target = source.with_name("tampered.json")
        target.write_bytes(canonical_bytes(envelope))
        self.addCleanup(target.unlink)
        return target

    def test_untampered_envelopes_verify(self):
        envelopes = [p for p in (self.out / "envelopes").glob("*.json") if p.name != "tampered.json"]
        code, out = self.run_cli("verify", *map(str, envelopes))
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("claim re-derives unchanged"), 9)

    def test_tampered_label_fails_verify(self):
        path = self.tampered(lambda e: e.update(claim_label="PROVED", bounds=None, completeness=None))
        code, out = self.run_cli("verify", str(path))
        self.assertEqual(code, 1)
        self.assertIn("claim_label: differs from the envelope re-derived from inventory-proof/ordering.json/properties/0", out)
        self.assertNotIn("verified", out)

    def test_non_label_or_runtime_status_fails_verify(self):
        # quaat/weave#8: verify refuses an envelope whose label is not one of the six, or whose
        # runtime status is an application outcome or a label, before any re-derivation.
        source = sorted((self.out / "envelopes").glob("*.json"))[0]
        for change in ({"claim_label": "PASSED"}, {"claim_label": "NOT PROVED"},
                       {"runtime_status": "Unknown"}, {"runtime_status": "NOT ESTABLISHED"}):
            with self.subTest(change=change):
                envelope = dict(json.loads(source.read_text()), **change)
                target = source.with_name("non-label.json")
                target.write_bytes(canonical_bytes(envelope))
                self.addCleanup(target.unlink)
                code, out = self.run_cli("verify", str(target))
                self.assertEqual(code, 1, out)
                self.assertIn(next(iter(change)), out)
                self.doCleanups()

    def test_every_tampered_claim_field_fails_verify(self):
        changes = {
            "claim_label": lambda e: e.update(claim_label="NOT ESTABLISHED"),
            "scope": lambda e: e.update(scope="All orders."),
            "bounds": lambda e: e["bounds"].update(max_states=99999),
            "completeness": lambda e: e["completeness"].update(states=21),
            "assumptions": lambda e: e["assumptions"].pop(),
            "profiles": lambda e: e["profiles"][0].update(name="N1"),
            "claim": lambda e: e["claim"].update(name="other_property"),
            "tools": lambda e: e["tools"][0].update(supported_profiles=["F0"]),
        }
        for field, change in changes.items():
            with self.subTest(field=field):
                code, out = self.run_cli("verify", str(self.tampered(change)))
                self.assertEqual(code, 1, out)
                self.assertIn(f"{field}: differs from the envelope re-derived", out)
                self.doCleanups()

    def test_claim_that_cannot_be_rederived_fails(self):
        envelope = json.loads(sorted((self.out / "envelopes").glob("*.json"))[0].read_text())
        self.assertEqual(rederive(envelope, ROOT), [])
        self.assertEqual(rederive(dict(envelope, claim=dict(envelope["claim"], pointer="/properties/99")), ROOT),
                         ["inventory-proof/ordering.json has no claim at '/properties/99'"])
        moved = dict(envelope, wrapped=dict(envelope["wrapped"], path="inventory-proof/other.json"))
        self.assertEqual(rederive(moved, ROOT), ["no wrapper for inventory-proof/other.json; the claim cannot be re-derived"])
        root = repo_copy()
        self.addCleanup(shutil.rmtree, root)
        (root / "inventory-proof/ordering.json").write_text("[]")
        errors = rederive(envelope, root)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("re-derivation from inventory-proof/ordering.json refused:"), errors)


class UnreadableInputTests(unittest.TestCase):
    """Item: unreadable inputs are refused with the file named, exit status 1, no traceback."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            return cli.main(list(argv)), buffer.getvalue()

    def inputs(self) -> dict[str, Path]:
        missing = self.dir / "missing.json"
        latin = self.dir / "latin1.json"
        latin.write_bytes(b'{"format": "weave-trace-v1", "subject": "caf\xe9"}')
        broken = self.dir / "broken.json"
        broken.write_text('{"format": ')
        return {"missing": missing, "not UTF-8": latin, "not JSON": broken, "directory": self.dir}

    def test_validate_and_verify_refuse_unreadable_files(self):
        for command in ("validate", "verify"):
            for name, path in self.inputs().items():
                with self.subTest(command=command, input=name):
                    code, out = self.run_cli(command, str(path))
                    self.assertEqual(code, 1, out)
                    self.assertIn(f"refused {path}", out)
                    self.assertIn(f"refused: ", out)
                    self.assertIn(str(path), out.split("\n", 1)[1])
                    self.assertNotIn("Traceback", out)

    @unittest.skipIf(hasattr(__import__("os"), "geteuid") and __import__("os").geteuid() == 0, "root reads any file")
    def test_unreadable_permissions_are_refused(self):
        path = self.dir / "locked.json"
        path.write_text("{}")
        path.chmod(0)
        self.addCleanup(path.chmod, 0o600)
        code, out = self.run_cli("validate", str(path))
        self.assertEqual(code, 1)
        self.assertIn(f"refused: cannot read {path}", out)

    def test_verify_refuses_a_trace_that_is_not_json(self):
        self.assertEqual(self.run_cli("wrap", "--out", str(self.dir), "inventory-proof/scenarios.json")[0], 0)
        envelope = sorted((self.dir / "envelopes").glob("*.json"))[0]
        trace = self.dir / "traces" / f"{json.loads(envelope.read_text())['trace']['sha256']}.json"
        for content in (b"not json", b"\xff\xfe"):
            with self.subTest(content=content):
                trace.write_bytes(content)
                code, out = self.run_cli("verify", str(envelope))
                self.assertEqual(code, 1, out)
                self.assertIn(f"trace {trace}: refused: {trace}", out)
                self.assertNotIn("Traceback", out)


class WrapOutputTests(unittest.TestCase):
    """Item: wrap --out writes nothing when any generated document is invalid."""

    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / "out"
        self.addCleanup(shutil.rmtree, self.out.parent)

    def test_invalid_generated_envelope_writes_nothing(self):
        real = cli.wrap

        def broken(root, rel):
            result = real(root, rel)
            result.envelopes[-1] = dict(result.envelopes[-1], claim_label="SCRIPTED")
            return result

        buffer = io.StringIO()
        with mock.patch.object(cli, "wrap", broken), contextlib.redirect_stdout(buffer), \
                contextlib.redirect_stderr(buffer):
            code = cli.main(["wrap", "--out", str(self.out), "inventory-proof/proof.json", "inventory-proof/ordering.json"])
        self.assertEqual(code, 1)
        self.assertIn("nothing written", buffer.getvalue())
        self.assertFalse(self.out.exists())

    def test_valid_run_writes_every_document(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(cli.main(["wrap", "--out", str(self.out), "inventory-proof/proof.json"]), 0)
        self.assertEqual(len(list((self.out / "envelopes").glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
