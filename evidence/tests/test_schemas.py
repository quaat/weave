# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""AC-1: three published JSON Schemas, each with a fixed format identifier."""
import json
import re
import unittest

from evidence.weave_evidence import documents, schema
from evidence.weave_evidence.documents import RESULT_LABELS, RUNTIME_STATUSES, assess

from .support import ROOT, minimal_envelope, minimal_net, minimal_trace

try:
    import jsonschema
except ImportError:  # optional cross-check; the tooling itself has no dependencies
    jsonschema = None

EXPECTED = {
    "weave-canonical-net-v1": "canonical-net.v1.schema.json",
    "weave-trace-v1": "trace.v1.schema.json",
    "weave-evidence-envelope-v1": "evidence-envelope.v1.schema.json",
}


def spec_labels() -> list[str]:
    """First-column entries of the Result vocabulary table in verification.rst."""
    text = (ROOT / "specification/docs/chapters/verification.rst").read_text(encoding="utf-8")
    table = text.split("Result vocabulary", 1)[1].split("Aggregate invariants", 1)[0]
    return [m for m in re.findall(r"(?m)^   \* - (.+)$", table) if m != "Label"]


class SchemaFileTests(unittest.TestCase):
    def test_exactly_three_schemas_with_fixed_format_identifiers(self):
        self.assertEqual(documents.SCHEMA_FILES, EXPECTED)
        self.assertEqual(sorted(p.name for p in schema.SCHEMA_DIR.glob("*.json")), sorted(EXPECTED.values()))
        for fmt, name in EXPECTED.items():
            loaded = schema.load(name)
            self.assertRegex(fmt, r"^weave-[a-z]+(-[a-z]+)*-v[1-9][0-9]*$")
            self.assertEqual(loaded["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(loaded["$id"], f"urn:weave:schema:{fmt}")
            self.assertEqual(loaded["properties"]["format"], {"const": fmt})
            self.assertIn("format", loaded["required"])
            self.assertFalse(loaded["additionalProperties"])

    def test_schemas_use_only_the_supported_subset(self):
        for name in EXPECTED.values():
            schema.check_subset(json.loads((schema.SCHEMA_DIR / name).read_text()))
        with self.assertRaises(schema.SchemaError):
            schema.check_subset({"type": "object", "oneOf": []})
        with self.assertRaises(schema.SchemaError):
            schema.validate({"a": "x"}, {"type": "object", "properties": {"a": {"maxLength": 1}}})

    def test_const_and_enum_compare_json_values(self):
        self.assertTrue(schema.validate(1, {"const": True}))
        self.assertTrue(schema.validate(True, {"enum": [1, 0]}))
        self.assertFalse(schema.validate(True, {"const": True}))

    def test_label_set_is_exactly_the_six_specification_labels(self):
        envelope = schema.load(EXPECTED["weave-evidence-envelope-v1"])
        self.assertEqual(tuple(envelope["properties"]["claim_label"]["enum"]), RESULT_LABELS)
        self.assertEqual(list(RESULT_LABELS), spec_labels())
        self.assertEqual(len(set(RESULT_LABELS)), 6)

    def test_runtime_status_is_a_separate_field_disjoint_from_labels(self):
        envelope = schema.load(EXPECTED["weave-evidence-envelope-v1"])
        self.assertEqual(envelope["properties"]["runtime_status"]["enum"], list(RUNTIME_STATUSES) + [None])
        self.assertFalse(set(RUNTIME_STATUSES) & set(RESULT_LABELS))
        self.assertIn("runtime_status", envelope["required"])
        self.assertIn("claim_label", envelope["required"])


class ExampleTests(unittest.TestCase):
    def test_minimal_documents_are_accepted(self):
        for document in (minimal_trace(), minimal_envelope(), minimal_net()):
            result = assess(document)
            self.assertTrue(result.accepted, result.errors)

    def test_each_runtime_status_and_null_is_accepted(self):
        for status in list(RUNTIME_STATUSES) + [None]:
            self.assertTrue(assess(minimal_envelope(runtime_status=status)).accepted, status)


@unittest.skipIf(jsonschema is None, "jsonschema is not installed; the meta-schema cross-check is optional")
class MetaSchemaTests(unittest.TestCase):
    """Cross-check with an independent JSON Schema implementation, where one is installed."""

    def test_schemas_are_valid_draft_2020_12_schemas(self):
        for name in EXPECTED.values():
            jsonschema.Draft202012Validator.check_schema(schema.load(name))

    def test_independent_validator_agrees_on_examples(self):
        cases = [
            (minimal_trace(), True),
            (minimal_envelope(), True),
            (minimal_net(), True),
            (minimal_envelope(claim_label="SCRIPTED"), False),
            (minimal_envelope(runtime_status="Unknown"), False),
            (minimal_envelope(sources=[]), False),
            (minimal_envelope(claim_label="VIOLATED", trace=None), False),
            (dict(minimal_trace(), steps=[{"sequence": 1, "kind": "fire"}]), False),
        ]
        for document, expected in cases:
            validator = jsonschema.Draft202012Validator(schema.load(documents.SCHEMA_FILES[document["format"]]))
            ours = not schema.validate(document, schema.load(documents.SCHEMA_FILES[document["format"]]))
            self.assertEqual(validator.is_valid(document), expected, document)
            self.assertEqual(ours, expected, document)


if __name__ == "__main__":
    unittest.main()
