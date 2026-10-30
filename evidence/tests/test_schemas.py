# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""AC-1: the published JSON Schemas, each with a fixed format identifier (three from #7, one from #6)."""
import json
import re
import unittest

from evidence.weave_evidence import documents, schema
from evidence.weave_evidence.documents import RESULT_LABELS, RUNTIME_STATUSES, assess

from .support import ROOT, minimal_diagnostic, minimal_envelope, minimal_net, minimal_trace

try:
    import jsonschema
except ImportError:  # optional cross-check; the tooling itself has no dependencies
    jsonschema = None

EXPECTED = {
    "weave-canonical-net-v1": "canonical-net.v1.schema.json",
    "weave-trace-v1": "trace.v1.schema.json",
    "weave-evidence-envelope-v1": "evidence-envelope.v1.schema.json",
    "weave-diagnostic-v1": "diagnostic.v1.schema.json",
}


def spec_labels() -> list[str]:
    """First-column entries of the Result vocabulary table in verification.rst."""
    text = (ROOT / "specification/docs/chapters/verification.rst").read_text(encoding="utf-8")
    table = text.split("Result vocabulary", 1)[1].split("Aggregate invariants", 1)[0]
    return [m for m in re.findall(r"(?m)^   \* - (.+)$", table) if m != "Label"]


class SchemaFileTests(unittest.TestCase):
    def test_exactly_four_schemas_with_fixed_format_identifiers(self):
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
        # The v1 envelope predates CHECKED pure (quaat/weave#10), the seventh label of the table.
        self.assertEqual(list(RESULT_LABELS), [label for label in spec_labels() if label != "CHECKED pure"])
        self.assertIn("CHECKED pure", spec_labels())
        self.assertEqual(len(set(RESULT_LABELS)), 6)

    def test_runtime_status_is_a_separate_field_disjoint_from_labels(self):
        envelope = schema.load(EXPECTED["weave-evidence-envelope-v1"])
        self.assertEqual(envelope["properties"]["runtime_status"]["enum"], list(RUNTIME_STATUSES) + [None])
        self.assertFalse(set(RUNTIME_STATUSES) & set(RESULT_LABELS))
        self.assertIn("runtime_status", envelope["required"])
        self.assertIn("claim_label", envelope["required"])


class ExampleTests(unittest.TestCase):
    def test_minimal_documents_are_accepted(self):
        for document in (minimal_trace(), minimal_envelope(), minimal_net(), minimal_diagnostic()):
            result = assess(document)
            self.assertTrue(result.accepted, result.errors)

    def test_each_runtime_status_and_null_is_accepted(self):
        for status in list(RUNTIME_STATUSES) + [None]:
            self.assertTrue(assess(minimal_envelope(runtime_status=status)).accepted, status)

    def test_each_label_is_accepted(self):
        for label in RESULT_LABELS:
            envelope = minimal_envelope(claim_label=label)
            if label == "CHECKED WITHIN BOUNDS":
                envelope.update(bounds={"max_states": 1}, completeness={"complete": True})
            if label == "VIOLATED":
                envelope.update(trace={"format": "weave-trace-v1", "sha256": "d" * 64})
            self.assertTrue(assess(envelope).accepted, (label, assess(envelope).errors))

    def test_reader_refuses_any_other_claim_label(self):
        # quaat/weave#8: prototype console words, abbreviations and other spellings are not labels.
        for label in ("PASSED", "NOT PROVED", "RECHECKED", "CHECKED", "CHECKED LOWERING", "EXECUTED", "SCRIPTED",
                      "passed scenario", "proved", "Proved", "CHECKED  flow", "NOT_ESTABLISHED", "Unknown",
                      "completed", "", None):
            result = assess(minimal_envelope(claim_label=label))
            self.assertFalse(result.accepted, label)
            self.assertTrue(any("claim_label" in e for e in result.errors), (label, result.errors))

    def test_reader_refuses_labels_and_outcomes_as_runtime_status(self):
        # Runtime status is separate from evidence: no label, and no application outcome such as Unknown.
        for status in list(RESULT_LABELS) + ["Unknown", "Ok", "Err", "EXECUTED", "PASSED", "Completed", ""]:
            result = assess(minimal_envelope(runtime_status=status))
            self.assertFalse(result.accepted, status)
            self.assertTrue(any("runtime_status" in e for e in result.errors), (status, result.errors))

    def test_label_and_runtime_status_are_both_required(self):
        for key in ("claim_label", "runtime_status"):
            envelope = minimal_envelope()
            del envelope[key]
            self.assertFalse(assess(envelope).accepted, key)


TOOL_ERROR = {"category": "tool", "code": "TOOL_ERROR", "rule": None, "secondary_rules": [], "stage": "net",
              "span": None, "related": []}
INVALID_DIAGNOSTICS = [
    {"rule": None},                                   # a language diagnostic needs its principal rule
    {"span": None},                                   # and a primary span
    {"rule": "f0-return-1"},                          # rule IDs are upper case
    {"secondary_rules": ["F0-TRY-3", "F0-TRY-3"]},    # without repeats
    {"category": "rule"},                             # closed category set
    {"severity": "fatal"},                            # closed severity set
    {"span": {"file": "flow.weave", "start": {"line": 0, "column": 1}, "end": {"line": 1, "column": 1}}},  # 1-based
    {"span": {"file": "flow.weave", "start": {"line": 1}, "end": {"line": 1, "column": 2}}},  # column required
    {"related": [{"role": "binding", "label": "x", "span": None}]},  # a related location has a span
    {"related": [{"role": "Binding", "label": "x", "span": minimal_diagnostic()["span"]}]},
    {"details": []},
    {"message": ""},
    dict(TOOL_ERROR, rule="F0-RETURN-1"),             # a tool failure has no rule
    dict(TOOL_ERROR, secondary_rules=["F0-RETURN-1"]),
]


class DiagnosticSchemaTests(unittest.TestCase):
    def test_tool_failure_without_rule_or_span_is_accepted(self):
        result = assess(minimal_diagnostic(**TOOL_ERROR))
        self.assertTrue(result.accepted, result.errors)

    def test_kit_extension_rule_is_accepted(self):
        result = assess(minimal_diagnostic(code="P420", category="kit-extension", rule="KIT-PURE-RUN-1",
                                           secondary_rules=[], related=[], stage="runtime"))
        self.assertTrue(result.accepted, result.errors)

    def test_invalid_diagnostics_are_rejected(self):
        for change in INVALID_DIAGNOSTICS:
            with self.subTest(change=change):
                self.assertFalse(assess(minimal_diagnostic(**change)).accepted)

    def test_reader_checks_span_order_and_repeated_principal_rule(self):
        backwards = {"file": "f", "start": {"line": 3, "column": 1}, "end": {"line": 2, "column": 9}}
        result = assess(minimal_diagnostic(span=backwards))
        self.assertIn("span: span ends before it starts", result.errors)
        result = assess(minimal_diagnostic(related=[{"role": "binding", "label": "x", "span": backwards}]))
        self.assertIn("related[0]: span ends before it starts", result.errors)
        result = assess(minimal_diagnostic(secondary_rules=["F0-RETURN-1"]))
        self.assertIn("principal rule 'F0-RETURN-1' is repeated in secondary_rules", result.errors)

    def test_prototype_checker_output_is_a_valid_diagnostic(self):
        """The working-copy checker's diagnostic() output, with the map's rules, conforms to the schema."""
        import sys
        sys.path.insert(0, str(ROOT / "inventory-proof"))
        sys.dont_write_bytecode = True
        try:
            from checker import CheckError, check_flow, parse_net
        finally:
            sys.path.remove(str(ROOT / "inventory-proof"))
        rules = json.loads((ROOT / "specification/diagnostics.json").read_text(encoding="utf-8"))["codes"]
        net = parse_net((ROOT / "inventory-proof/Inventory.weave").read_text(encoding="utf-8"))
        source = ("flow leak(result: ChargeOutcome[t, o], extra: Paid[u, v]) -> ChargeOutcome[t, o]:\n"
                  "    let paid = result?\n    await Inventory.sell(extra)\n    return Ok(paid)\n")
        with self.assertRaises(CheckError) as raised:
            check_flow(net, source)
        entry = rules[raised.exception.code]
        document = raised.exception.diagnostic("leak.weave", source, "flow", entry["rule"], entry["secondary_rules"])
        result = assess(document)
        self.assertTrue(result.accepted, result.errors)
        self.assertEqual([r["role"] for r in document["related"]], ["binding", "propagation"])


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
            (minimal_diagnostic(), True),
            (minimal_diagnostic(**TOOL_ERROR), True),
        ] + [(minimal_diagnostic(**change), False) for change in INVALID_DIAGNOSTICS]
        for document, expected in cases:
            validator = jsonschema.Draft202012Validator(schema.load(documents.SCHEMA_FILES[document["format"]]))
            ours = not schema.validate(document, schema.load(documents.SCHEMA_FILES[document["format"]]))
            self.assertEqual(validator.is_valid(document), expected, document)
            self.assertEqual(ours, expected, document)


if __name__ == "__main__":
    unittest.main()
