# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""AC-2: unknown or missing schema versions are never interpreted as successful evidence."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from evidence.weave_evidence import __main__ as cli
from evidence.weave_evidence.documents import assess, assess_file, assess_text
from evidence.weave_evidence.traces import ConversionError
from evidence.weave_evidence.wrap import wrap

from .support import ALL_FILES, ROOT, minimal_envelope, minimal_net, minimal_trace, repo_copy

VALID = {"weave-canonical-net-v1": minimal_net, "weave-trace-v1": minimal_trace,
         "weave-evidence-envelope-v1": minimal_envelope}
NEAR = ["weave-trace-v2", "weave-trace-v0", "weave-trace-v10", "weave-trace", "weave-trace-v1 ", " weave-trace-v1",
        "Weave-Trace-V1", "weave-evidence-envelope-v2", "weave-canonical-net-v2", "weave-place-invariant-v1",
        "weave-specification-validation-v1", ""]


def run_cli(*argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class UnknownVersionTests(unittest.TestCase):
    def assert_refused(self, document, named=None):
        result = assess(document)
        self.assertFalse(result.accepted)
        self.assertTrue(result.refused)
        self.assertTrue(result.errors[0].startswith("refused:"), result.errors)
        if named is not None:
            self.assertIn(repr(named), result.errors[0])

    def test_unknown_version_of_an_otherwise_valid_document_is_refused(self):
        for fmt, make in VALID.items():
            self.assertTrue(assess(make()).accepted, fmt)
            for other in NEAR:
                with self.subTest(fmt=fmt, other=other):
                    self.assert_refused(dict(make(), format=other), named=other)

    def test_missing_format_is_refused(self):
        for fmt, make in VALID.items():
            document = make()
            del document["format"]
            self.assert_refused(document)
            self.assertIn("no top-level 'format' field", assess(document).errors[0])

    def test_non_string_format_is_refused(self):
        for value in (None, 1, True, ["weave-trace-v1"], {"id": "weave-trace-v1"}):
            self.assert_refused(dict(minimal_trace(), format=value), named=value)

    def test_non_object_and_non_strict_json_are_refused(self):
        self.assert_refused([minimal_trace()])
        for text in ('{"format": "weave-trace-v1", "format": "weave-trace-v1"}', '{"format": NaN}', "{", ""):
            result = assess_text(text)
            self.assertFalse(result.accepted)
            self.assertTrue(result.refused)

    def test_existing_evidence_files_are_not_read_as_versioned_evidence(self):
        for rel in ALL_FILES:
            result = assess_file(ROOT / rel)
            self.assertFalse(result.accepted, rel)
            self.assertTrue(result.refused, rel)

    def test_nested_trace_reference_with_unknown_version_is_invalid(self):
        envelope = minimal_envelope(trace={"format": "weave-trace-v2", "sha256": "d" * 64})
        self.assertFalse(assess(envelope).accepted)


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def write(self, name, document) -> str:
        path = self.dir / name
        path.write_text(json.dumps(document))
        return str(path)

    def test_validate_refuses_unknown_version_and_names_it(self):
        path = self.write("v2.json", dict(minimal_trace(), format="weave-trace-v2"))
        code, out = run_cli("validate", path)
        self.assertEqual(code, 1)
        self.assertIn("refused", out)
        self.assertIn("'weave-trace-v2'", out)
        self.assertNotIn("valid ", out.replace("invalid", ""))

    def test_validate_refuses_missing_version(self):
        document = minimal_envelope()
        del document["format"]
        code, out = run_cli("validate", self.write("none.json", document))
        self.assertEqual(code, 1)
        self.assertIn("no top-level 'format' field", out)

    def test_one_refused_input_fails_the_whole_run(self):
        good = self.write("good.json", minimal_trace())
        bad = self.write("bad.json", dict(minimal_trace(), format="weave-trace-v9"))
        self.assertEqual(run_cli("validate", good)[0], 0)
        self.assertEqual(run_cli("validate", good, bad)[0], 1)

    def test_verify_refuses_an_envelope_with_unknown_version(self):
        path = self.write("env.json", dict(minimal_envelope(), format="weave-evidence-envelope-v2"))
        code, out = run_cli("verify", path)
        self.assertEqual(code, 1)
        self.assertIn("'weave-evidence-envelope-v2'", out)
        self.assertNotIn("hashes recompute", out)


class WrapperVersionTests(unittest.TestCase):
    """The wrappers read the existing prototype formats and refuse identifiers they do not implement."""

    @classmethod
    def setUpClass(cls):
        cls.root = repo_copy()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def rewrite(self, rel, change):
        path = self.root / rel
        original = path.read_bytes()
        self.addCleanup(path.write_bytes, original)
        document = json.loads(original)
        change(document)
        path.write_text(json.dumps(document))

    def test_unknown_or_missing_original_format_is_refused(self):
        cases = {
            "inventory-proof/proof.json": "weave-place-invariant-v2",
            "inventory-proof/ordering.json": "weave-one-order-check-v1",
            "inventory-proof/colour-proof.json": "weave-colour-invariant-v2",
            "inventory-proof/colour-check.json": "weave-colour-exploration-v2",
            "specification/validation/report.json": "weave-specification-validation-v2",
        }
        for rel, other in cases.items():
            for value in (other, None):
                with self.subTest(rel=rel, value=value):
                    self.rewrite(rel, lambda d: d.update(format=value) if value else d.pop("format"))
                    with self.assertRaises(ConversionError) as caught:
                        wrap(self.root, rel)
                    self.assertIn(repr(value) if value else "'(no format field)'", str(caught.exception))
                    self.doCleanups()

    def test_unversioned_scenario_files_wrapped_only_in_their_known_shape(self):
        for rel in ("inventory-proof/scenarios.json", "inventory-proof/durable-scenarios.json"):
            with self.subTest(rel=rel):
                self.rewrite(rel, lambda d: d[0].update(format="weave-scenario-v1"))
                with self.assertRaises(ConversionError):
                    wrap(self.root, rel)
                self.doCleanups()


if __name__ == "__main__":
    unittest.main()
