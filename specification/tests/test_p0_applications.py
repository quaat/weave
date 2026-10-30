# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""The P0 conformance applications (``scripts/p0_applications.py``, quaat/weave#11).

The harness must pass on the unchanged programs, fail on programs that sort wrongly,
lose stability or route by another rule, fail on a disagreeing ``weave`` binary, and
record a missing binary as not established, never as agreement.
"""
from pathlib import Path
import json
import os
import random
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import p0_applications as apps  # noqa: E402


def mutated(path: Path, old: str, new: str, tmp: str) -> Path:
    """A copy of an example with one source edit, as a path relative to the specification."""
    source = (ROOT / path).read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise AssertionError(f"{old!r} must occur once in {path}")
    out = Path(tmp) / path.name
    out.write_text(source.replace(old, new), encoding="utf-8")
    return Path(os.path.relpath(out, ROOT))


def reference_only() -> "apps.Sides":
    return apps.Sides(None, "cargo is not on PATH")


class Inputs(unittest.TestCase):
    def test_exhaustive_lists_are_every_list_once(self):
        lists = apps.exhaustive()
        self.assertEqual(len(lists), sum(3 ** n for n in range(7)))
        self.assertEqual(len({tuple(xs) for xs in lists}), len(lists))
        self.assertEqual(max(map(len, lists)), 6)

    def test_seeded_inputs_are_long_wide_and_repeatable(self):
        lists = apps.seeded_lists(random.Random(apps.SEED))
        self.assertEqual(lists, apps.seeded_lists(random.Random(apps.SEED)))
        self.assertGreaterEqual(max(map(len, lists)), 200)
        values = [x for xs in lists for x in xs]
        self.assertTrue(any(x < 0 for x in values))
        self.assertTrue(any(abs(x) >= 2 ** 64 for x in values))
        items = apps.seeded_items(random.Random(apps.SEED))
        for xs in items:
            self.assertEqual(len({r["id"] for r in xs}), len(xs))

    def test_stability_predicate(self):
        before = apps.items_of([1, 0, 1], [10, 11, 12])
        self.assertTrue(apps.stable_order_kept(before, apps.items_of([0, 1, 1], [11, 10, 12])))
        self.assertFalse(apps.stable_order_kept(before, apps.items_of([0, 1, 1], [11, 12, 10])))


class RouteOracle(unittest.TestCase):
    def test_named_cases_match_the_hand_written_decisions(self):
        for name, routes, limit, decision in apps.NAMED_ROUTES:
            with self.subTest(name):
                self.assertEqual(apps.route_oracle(routes, limit), decision)

    def test_invalid_reasons(self):
        self.assertEqual(apps.invalid_reasons(apps.R(0, 10, 16), 10), [])
        self.assertEqual(apps.invalid_reasons(apps.R(0, -1, 0), 10), ["negative cost", "hops below 1"])
        self.assertEqual(apps.invalid_reasons(apps.R(0, 11, 17), 10), ["hops over 16", "cost over limit"])

    def test_a_named_case_the_oracle_contradicts_fails(self):
        wrong = [("tie", [apps.R(7, 3, 1), apps.R(2, 3, 1)], 10, {"accepted": True, "dest": 7, "cost": 3})]
        with mock.patch.object(apps, "NAMED_ROUTES", wrong):
            with self.assertRaises(AssertionError):
                apps.route(reference_only(), random.Random(0), seeded=0)


class Applications(unittest.TestCase):
    def test_unchanged_programs_meet_the_oracles(self):
        sides = reference_only()
        rng = random.Random(apps.SEED)
        self.assertEqual(apps.merge_sort(sides, rng, seeded=4)["rust"], {"status": "skipped", "compared": 0})
        items = apps.sort_items(sides, rng, seeded=4)
        self.assertGreater(items["inputs_with_equal_keys"], 0)
        route = apps.route(sides, rng, seeded=20)
        self.assertGreater(route["invalid_records"], 0)
        self.assertGreater(route["valid_records"], 0)
        self.assertEqual(set(route["invalid_by_reason"]),
                         {"negative cost", "hops below 1", "hops over 16", "cost over limit"})
        self.assertGreater(route["inputs_with_cost_ties"], 0)
        self.assertEqual(apps.malformed(sides)["requests"], len(apps.MALFORMED_REQUESTS))

    def test_a_wrong_sort_fails(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            # The flipped comparison sorts descending.
            path = mutated(apps.MERGE_SORT, "if head(a) <= head(b):", "if head(a) >= head(b):", tmp)
            with self.assertRaises(AssertionError):
                apps.merge_sort(reference_only(), random.Random(0), path=path, seeded=2)

    def test_an_unstable_sort_fails_on_the_ids(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = mutated(apps.MERGE_SORT, "if x.key <= y.key:", "if x.key < y.key:", tmp)
            # The keys are still sorted; only the order of equal keys, seen through the ids, differs.
            with self.assertRaisesRegex(AssertionError, "stability"):
                apps.sort_items(reference_only(), random.Random(0), path=path, seeded=2)

    def test_another_routing_rule_fails(self):
        for old, new in (("r.hops <= 16", "r.hops <= 15"), ("r.cost <= limit", "r.cost < limit"),
                         ("r.cost >= 0", "r.cost >= 1"), ("r.dest < d.dest", "r.dest > d.dest")):
            with self.subTest(new), tempfile.TemporaryDirectory(dir=ROOT) as tmp:
                path = mutated(apps.ROUTING, old, new, tmp)
                with self.assertRaises(AssertionError):
                    apps.route(reference_only(), random.Random(0), path=path, seeded=0)

    def test_malformed_requests_are_invalid_run_requests(self):
        sides = reference_only()
        for name, path, entry, text in apps.MALFORMED_REQUESTS:
            with self.subTest(name):
                self.assertEqual(sides.reference(path, entry, text), {"code": "E540", "stage": "run"})
        # The well-formed counterpart of a malformed record is a value.
        ok = sides.reference(apps.ROUTING, "route", '[[{"dest": 1, "cost": 2, "hops": 1}], 10]')
        self.assertEqual((ok["code"], ok["value"]), ("VALUE", {"accepted": True, "dest": 1, "cost": 2}))

    def test_a_well_formed_request_listed_as_malformed_fails(self):
        well_formed = [("not malformed", apps.ROUTING, "route", "[[], 10]")]
        with mock.patch.object(apps, "MALFORMED_REQUESTS", well_formed):
            with self.assertRaises(AssertionError):
                apps.malformed(reference_only())


class RustSide(unittest.TestCase):
    def test_a_report_without_rust_says_not_established(self):
        report = apps.build_report(None, "cargo is not on PATH", seeded=2, seeded_route_lists=2)
        rust = report["rust_comparison"]
        self.assertEqual((rust["status"], rust["compared"]), ("skipped", 0))
        self.assertIn("not established", rust["note"])
        for app in report["applications"].values():
            self.assertEqual(app["rust"], {"status": "skipped", "compared": 0})
        self.assertEqual(report["invalid_run_requests"]["rust"]["compared"], 0)
        self.assertIn("#42", report["scope"])

    @unittest.skipIf(os.name == "nt", "the stand-in binary is a POSIX shell script")
    def test_a_disagreeing_binary_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "weave"
            # Every run returns the empty list with no budget used.
            doc = {"outcome": "value", "value": [], "fault": None, "exhausted": None, "diagnostics": [],
                   "budgets": {"fuel": {"limit": 1, "used": 0}, "depth": {"limit": 1, "max": 0},
                               "int_bits": {"limit": 1, "max": 0}}}
            fake.write_text(f"#!/bin/sh\necho '{json.dumps(doc)}'\n", encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            sides = apps.Sides(fake, "WEAVE_BIN")
            with self.assertRaises(AssertionError):
                apps.merge_sort(sides, random.Random(0), seeded=2)
            with self.assertRaises(AssertionError):
                apps.malformed(sides)


if __name__ == "__main__":
    unittest.main()
