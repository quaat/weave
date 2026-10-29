# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Trace converters (weave-trace-v1) and the canonical-net exporter (weave-canonical-net-v1)."""
import json
import shutil
import unittest

from evidence.weave_evidence.documents import assess, canonical_bytes
from evidence.weave_evidence.netexport import ExportError, export
from evidence.weave_evidence.traces import (ConversionError, from_counterexample, from_durable, from_scheduler_run,
                                            from_simulation, marking_dict)

from .support import ROOT, minimal_net, minimal_trace, repo_copy


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class TraceConversionTests(unittest.TestCase):
    def test_simulation_runs_convert_without_loss(self):
        for i, run in enumerate(load("inventory-proof/scenarios.json")):
            trace = from_simulation(run, f"scenarios/{i}")
            self.assertTrue(assess(trace).accepted, assess(trace).errors)
            self.assertEqual(marking_dict(trace["final_marking"]), run["marking"])
            self.assertEqual(len(trace["steps"]), len(run["events"]))
            for step, event in zip(trace["steps"], run["events"]):
                self.assertEqual(marking_dict(step["marking"]), event["marking"])
                if event["kind"] == "NET":
                    self.assertEqual((step["kind"], step["transition"]), ("fire", event["name"]))
                else:
                    self.assertEqual((step["kind"], step["flow"], step["tag"]), ("return", event["name"], event["tag"]))
            self.assertEqual(trace["outcome"], run["outcome"])

    def test_durable_cases_convert_without_loss(self):
        for i, case in enumerate(load("inventory-proof/durable-scenarios.json")):
            trace = from_durable(case, f"durable/{i}")
            self.assertTrue(assess(trace).accepted, assess(trace).errors)
            self.assertEqual(marking_dict(trace["final_marking"]), case["marking"])
            for step, event in zip(trace["steps"], case["events"]):
                self.assertEqual(step["sequence"], event["sequence"])
                self.assertEqual(marking_dict(step["marking"]), event["marking"])
                rebuilt = dict(step.get("detail", {}))
                for key in ("colour", "transition"):
                    if key in step:
                        rebuilt[key] = step[key]
                self.assertEqual(rebuilt, event["detail"])
            self.assertEqual(trace["context"]["crash"], case["crash"])

    def test_counterexamples_convert(self):
        e320 = from_counterexample((ROOT / "specification/validation/counterexample-E320.txt").read_text(), "E320")
        self.assertTrue(assess(e320).accepted, assess(e320).errors)
        self.assertEqual(e320["subject"], "dispatched_release_requires_rejection")
        self.assertEqual([s["transition"] for s in e320["steps"]], ["reserve", "arm", "dispatch", "charge_ok", "cancel_paid"])
        self.assertEqual(marking_dict(e320["final_marking"]), {"available": 1, "charge_requests": 1})
        self.assertEqual(e320["context"]["flags"], {"dispatched": True, "paid_evidence": True, "rejected_evidence": False})
        e420 = from_counterexample((ROOT / "specification/validation/counterexample-E420.txt").read_text(), "E420")
        self.assertTrue(assess(e420).accepted, assess(e420).errors)
        self.assertEqual(e420["steps"][-1]["detail"]["binding"], {"t": "tenant", "o": "order1", "other": "order2"})
        self.assertIsNone(e420["final_marking"])

    def test_scheduler_run_converts(self):
        run = load("agent-kit/demos/merge_sort/artifacts/trace-concurrent.json")
        trace = from_scheduler_run(run, "merge_sort")
        self.assertTrue(assess(trace).accepted, assess(trace).errors)
        self.assertEqual(len(trace["steps"]), len(run["events"]))
        self.assertEqual(trace["kind"], "scheduler-run")

    def test_unrecognised_shapes_are_refused(self):
        run = load("inventory-proof/scenarios.json")[0]
        with self.assertRaises(ConversionError):
            from_simulation(dict(run, extra=1), "x")
        bad = json.loads(json.dumps(run))
        bad["events"][0]["kind"] = "STEP"
        with self.assertRaises(ConversionError):
            from_simulation(bad, "x")
        bad = json.loads(json.dumps(run))
        bad["marking"]["held[a,"] = 1
        with self.assertRaises(ConversionError):
            from_simulation(bad, "x")
        bad = json.loads(json.dumps(run))
        bad["marking"]["held"] = -1
        with self.assertRaises(ConversionError):
            from_simulation(bad, "x")
        with self.assertRaises(ConversionError):
            from_counterexample("examples/x.weave:1: E320\n  not a violation\n", "x")

    def test_reader_checks_reject_malformed_traces(self):
        cases = {
            "sequence": lambda t: t["steps"].reverse(),
            "fire without transition": lambda t: t["steps"][0].pop("transition"),
            "label as outcome": lambda t: t.update(outcome="NOT ESTABLISHED"),
            "duplicate count": lambda t: t["final_marking"].append(dict(t["final_marking"][0])),
            "unknown kind": lambda t: t.update(kind="proof"),
            "negative count": lambda t: t["final_marking"][0].update(count=-1),
        }
        for name, change in cases.items():
            trace = minimal_trace()
            change(trace)
            self.assertFalse(assess(trace).accepted, name)


class CanonicalNetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n0 = export(ROOT / "inventory-proof/Inventory.weave", "N0", ROOT, "0.2-draft")
        cls.n1 = export(ROOT / "inventory-proof/Inventory.coloured.weave", "N1", ROOT, "0.2-draft")

    def test_exports_are_accepted(self):
        for net in (self.n0, self.n1):
            self.assertTrue(assess(net).accepted, assess(net).errors)

    def test_n0_export_agrees_with_the_place_invariant_certificate(self):
        proof = load("inventory-proof/proof.json")
        self.assertEqual(self.n0["source_sha256"], proof["source_sha256"])
        self.assertEqual(sorted(proof["places"]), [p["name"] for p in self.n0["places"]])
        self.assertEqual(sorted(proof["transitions"]), [t["name"] for t in self.n0["transitions"]])
        transitions = {t["name"]: t for t in self.n0["transitions"]}
        for i, place in enumerate(proof["places"]):
            for j, name in enumerate(proof["transitions"]):
                change = sum(a["weight"] * (1 if a["kind"] == "put" else -1)
                             for a in transitions[name]["arcs"] if a["place"] == place and a["kind"] != "read")
                self.assertEqual(change, proof["incidence"][i][j], (place, name))
        initial = {m["place"]: [m["parameters"].get("stock", 0), m["constant"]] for m in self.n0["initial_marking"]}
        self.assertEqual([initial[p] for p in proof["places"]], proof["initial_affine"])

    def test_n1_export_agrees_with_the_colour_certificate(self):
        proof = load("inventory-proof/colour-proof.json")
        self.assertEqual(self.n1["source_sha256"], proof["source_sha256"])
        self.assertEqual(self.n1["colour_sorts"], ["tenant", "order"])
        for t in self.n1["transitions"]:
            self.assertEqual(t["binder"], ["t", "o"])
            arcs = {kind: {a["place"]: a["inscription"] for a in t["arcs"] if a["kind"] == kind}
                    for kind in ("take", "put", "read")}
            self.assertEqual(arcs, proof["transition_inscriptions"][t["name"]], t["name"])
        identities = next(m for m in self.n1["initial_marking"] if m["place"] == "identities")
        self.assertEqual((identities["constant"], identities["parameters"]), (1, {}))

    def test_export_is_reproducible_and_independent_of_declaration_order(self):
        again = export(ROOT / "inventory-proof/Inventory.weave", "N0", ROOT, "0.2-draft")
        self.assertEqual(canonical_bytes(again), canonical_bytes(self.n0))
        root = repo_copy()
        self.addCleanup(shutil.rmtree, root)
        path = root / "inventory-proof/Inventory.weave"
        text = path.read_text()
        first, second = "    place held = 0 owner activation\n", "    place escrow = 0 owner activation\n"
        swapped = text.replace(first + second, second + first)
        self.assertNotEqual(swapped, text)
        path.write_text(swapped)
        reordered = export(path, "N0", ROOT, "0.2-draft")
        self.assertNotEqual(reordered["source_sha256"], self.n0["source_sha256"])
        self.assertEqual(dict(reordered, source_sha256=None), dict(self.n0, source_sha256=None))
        # Guards are a set in the prototype; two guards declared in either order export alike.
        exports = []
        for extra in ("        guard outcome_unresolved\n" + "        guard operation_is_dispatchable\n",
                      "        guard operation_is_dispatchable\n" + "        guard outcome_unresolved\n"):
            path.write_text(text.replace("        guard operation_is_dispatchable\n", extra, 1))
            exports.append(export(path, "N0", ROOT, "0.2-draft"))
        guards = [next(t["guards"] for t in e["transitions"] if t["name"] == "adapter_dequeue") for e in exports]
        self.assertEqual(guards, [["operation_is_dispatchable", "outcome_unresolved"]] * 2)
        self.assertEqual(dict(exports[0], source_sha256=None), dict(exports[1], source_sha256=None))

    def test_exporter_refuses_unsupported_input(self):
        with self.assertRaisesRegex(ExportError, "unsupported profile 'N2'"):
            export(ROOT / "inventory-proof/Inventory.weave", "N2", ROOT, "0.2-draft")
        with self.assertRaisesRegex(ExportError, "the N0 parser rejected the source: E003"):
            export(ROOT / "inventory-proof/Inventory.coloured.weave", "N0", ROOT, "0.2-draft")

    def test_reader_checks_reject_malformed_nets(self):
        cases = {
            "unsorted places": lambda n: n["places"].reverse(),
            "undeclared arc place": lambda n: n["transitions"][0]["arcs"][1].update(place="nowhere"),
            "inscription arity": lambda n: n["transitions"][0]["arcs"][1].update(inscription=["t"]),
            "missing initial entry": lambda n: n["initial_marking"].pop(),
            "undeclared parameter": lambda n: n["initial_marking"][0].update(parameters={"budget": 1}),
            "duplicate transition": lambda n: n["transitions"].append(json.loads(json.dumps(n["transitions"][0]))),
            "arc order": lambda n: n["transitions"][0]["arcs"].reverse(),
            "binder arity": lambda n: n["transitions"][0].update(binder=["t"]),
            "zero weight": lambda n: n["transitions"][0]["arcs"][0].update(weight=0),
            "unknown owner": lambda n: n["places"][0].update(owner="kernel"),
            "unsorted guards": lambda n: n["transitions"][0].update(guards=["b", "a"]),
            "duplicate guard": lambda n: n["transitions"][0].update(guards=["a", "a"]),
        }
        for name, change in cases.items():
            net = minimal_net()
            change(net)
            self.assertFalse(assess(net).accepted, name)


if __name__ == "__main__":
    unittest.main()
