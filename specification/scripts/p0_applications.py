#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Conformance applications for P0 pure code (docs/chapters/pure.rst, quaat/weave#11).

Two ordinary P0 programs are run through the ordinary ``weave run`` command and the
Python P0 reference evaluator, and both are compared with oracles written in Python:

* ``examples/pure/valid/merge_sort.weave``, ``merge_sort``: every list of length 0
  to 6 over {0, 1, 2} and seeded random lists of up to 256 integers (negative
  values and integers far wider than 64 bits), against Python ``sorted``;
* the same file, ``sort_items``: (key, id) records with distinct ids, every key
  sequence of length 0 to 6 over {0, 1, 2} with ids equal to positions and seeded
  larger lists with shuffled ids, against Python's stable ``sorted`` by key.
  Stability is checked on the output ids, which make the order of equal keys
  observable;
* ``examples/pure/valid/routing.weave``, ``route``: named valid and invalid
  records, every single route of a boundary grid and seeded route lists, against
  ``route_oracle`` below, which is written from the routing rule and does not call
  the reference; and malformed run requests, which must be invalid run requests
  (E540, P0-RUN-1) with nothing evaluated.

The concurrent fork/join merge sort of ``agent-kit/claude-code-weave-merge-sort.md``
is not one of these applications; it is quaat/weave#42 (M6).

The Rust side is the ``weave`` binary named by ``WEAVE_BIN`` or built with
``cargo build --offline --locked`` (as in ``p0_differential.py``). Without either,
the reference is still compared with the oracles, and the Rust comparison is
recorded as not established in ``validation/p0-applications.json``, never as
agreement. Any disagreement fails.
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import p0_reference as ref  # noqa: E402
from p0_differential import normalise, rust_binary  # noqa: E402

SEED = 20261111
MERGE_SORT = Path("examples/pure/valid/merge_sort.weave")
ROUTING = Path("examples/pure/valid/routing.weave")
EXHAUSTIVE_MAX_LENGTH = 6
EXHAUSTIVE_VALUES = (0, 1, 2)
SEEDED_LISTS = 60
LONG_LENGTHS = (200, 256)
SEEDED_ROUTE_LISTS = 300
HOPS_LIMIT = 16
REQUEST_CODE = "E540"


# ---------------------------------------------------------------- the two sides

class Sides:
    """The Python reference, in process, and the ``weave`` binary, through its command line."""

    def __init__(self, binary: Path | None, how: str):
        self.binary, self.how = binary, how
        self.reference_runs = self.rust_runs = 0
        self._programs: dict[Path, ref.Checked] = {}

    def program(self, path: Path):
        if path not in self._programs:
            self._programs[path] = ref.check((ROOT / path).read_text(encoding="utf-8"))
        return self._programs[path]

    def reference(self, path: Path, entry: str, args_text: str) -> dict:
        """The reference's result, normalised as in ``p0_differential.py``."""
        self.reference_runs += 1
        args = json.loads(args_text, object_pairs_hook=ref.json_object)
        try:
            report = ref.run(self.program(path), entry, args, {})
        except ref.Diagnostic as d:
            return {"code": d.code, "stage": d.stage}
        return normalise(report, [d.code for d in report["diagnostics"]])

    def rust_one(self, path: Path, entry: str, args_text: str) -> tuple[int, dict]:
        argv = [str(self.binary), "run", path.as_posix(), "--entry", entry, "--args", args_text, "--json"]
        done = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=300)
        if done.returncode not in (0, 1, 3, 4):
            raise RuntimeError(f"weave run {path} --entry {entry} exited {done.returncode}: "
                               f"{done.stderr.decode(errors='replace')}")
        return done.returncode, json.loads(done.stdout)

    def rust(self, path: Path, entry: str, many: list[str]) -> list[tuple[int, dict]] | None:
        """``weave run FILE --entry ENTRY --args ARGS --json`` for each ARGS, or None without a binary."""
        if self.binary is None:
            return None
        self.rust_runs += len(many)
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
            return list(pool.map(lambda text: self.rust_one(path, entry, text), many))


def rust_normalised(exit_code: int, doc: dict) -> dict:
    codes = [d["code"] for d in doc["diagnostics"]]
    if doc.get("outcome") is None:
        stage = doc["diagnostics"][0]["stage"] if doc["diagnostics"] else None
        return {"code": codes[0] if codes else None, "stage": stage, "exit": exit_code}
    return dict(normalise(doc, codes), exit=exit_code)


EXIT_OF = {"value": 0, "fault": 3, "exhausted": 4}


def compare(sides: Sides, path: Path, entry: str, cases: list[tuple[str, object]], what: str) -> dict:
    """Run every (args_text, oracle value) on both sides; any difference from the oracle fails."""
    reference = []
    for text, want in cases:
        py = sides.reference(path, entry, text)
        if py.get("code") != "VALUE" or py.get("value") != want:
            raise AssertionError(f"{what} {entry}{text}: Python reference {py}, oracle {want}")
        reference.append(py)
    results = sides.rust(path, entry, [text for text, _ in cases])
    if results is None:
        return {"status": "skipped", "compared": 0}
    for (text, want), py, (exit_code, doc) in zip(cases, reference, results):
        rs = rust_normalised(exit_code, doc)
        py = dict(py, exit=EXIT_OF[py["outcome"]])
        if rs != py:
            raise AssertionError(f"{what} {entry}{text}: Rust {rs}, Python reference {py}")
        if doc.get("value") != want:
            raise AssertionError(f"{what} {entry}{text}: Rust value {doc.get('value')}, oracle {want}")
    return {"status": "compared", "compared": len(cases)}


def rust_status(sides: Sides, compared: int) -> dict:
    if sides.binary is None:
        return {"status": "skipped", "compared": 0,
                "note": f"Rust weave agreement on the applications not established: {sides.how}."}
    return {"status": "compared", "binary": sides.how, "compared": compared}


# ---------------------------------------------------------------- inputs

def exhaustive(max_length: int = EXHAUSTIVE_MAX_LENGTH, values=EXHAUSTIVE_VALUES) -> list[list[int]]:
    """Every list of length 0 to max_length over values, shortest first."""
    out: list[list[int]] = [[]]
    frontier: list[list[int]] = [[]]
    for _ in range(max_length):
        frontier = [xs + [v] for xs in frontier for v in values]
        out += frontier
    return out


def wide(rng: random.Random) -> int:
    """An integer from one of several ranges: small with repeats, 64-bit edges, far wider."""
    pick = rng.randrange(5)
    if pick == 0:
        return rng.randint(-3, 3)
    if pick == 1:
        return rng.randint(-10**6, 10**6)
    if pick == 2:
        return rng.choice([2**63 - 1, -2**63, 2**63, -2**63 - 1, 2**64, -2**64])
    if pick == 3:
        return rng.randint(-10**40, 10**40)
    return rng.randint(-2**200, 2**200)


def seeded_lengths(rng: random.Random, count: int) -> list[int]:
    return list(LONG_LENGTHS) + [rng.randint(0, 120) for _ in range(count - len(LONG_LENGTHS))]


def seeded_lists(rng: random.Random, count: int = SEEDED_LISTS) -> list[list[int]]:
    lists = [[wide(rng) for _ in range(n)] for n in seeded_lengths(rng, count)]
    # Shapes a split or merge can get wrong: ascending, descending, all equal.
    lists += [list(range(-50, 50)), list(range(50, -50, -1)), [7] * 64, [0, -1] * 40]
    return lists


def items_of(keys: list[int], ids: list[int]) -> list[dict]:
    return [{"key": k, "id": i} for k, i in zip(keys, ids)]


def seeded_items(rng: random.Random, count: int = SEEDED_LISTS) -> list[list[dict]]:
    out = []
    for n in seeded_lengths(rng, count):
        keys = [rng.randint(-3, 3) if rng.random() < 0.8 else wide(rng) for _ in range(n)]
        ids = rng.sample(range(-10**6, 10**6), n)
        out.append(items_of(keys, ids))
    return out


def stable_order_kept(before: list[dict], after: list[dict]) -> bool:
    """For every key, the ids of equal-key items keep their input order."""
    order = {}
    for item in before:
        order.setdefault(item["key"], []).append(item["id"])
    seen = {}
    for item in after:
        seen.setdefault(item["key"], []).append(item["id"])
    return order == seen


# ---------------------------------------------------------------- merge sort

def merge_sort(sides: Sides, rng: random.Random, path: Path = MERGE_SORT, seeded: int = SEEDED_LISTS) -> dict:
    short = exhaustive()
    long = seeded_lists(rng, seeded)
    cases = [(json.dumps([xs]), sorted(xs)) for xs in short + long]
    rust = compare(sides, path, "merge_sort", cases, "merge sort")
    return {"file": path.as_posix(), "entry": "merge_sort", "oracle": "Python sorted()",
            "exhaustive": {"max_length": EXHAUSTIVE_MAX_LENGTH, "values": list(EXHAUSTIVE_VALUES),
                           "inputs": len(short)},
            "seeded": {"inputs": len(long), "longest": max(map(len, long)),
                       "widest_bits": max((abs(x).bit_length() for xs in long for x in xs), default=0)},
            "inputs": len(cases), "reference": "equal to the oracle on every input", "rust": rust}


def sort_items(sides: Sides, rng: random.Random, path: Path = MERGE_SORT, seeded: int = SEEDED_LISTS) -> dict:
    short = [items_of(keys, list(range(len(keys)))) for keys in exhaustive()]
    long = seeded_items(rng, seeded)
    cases, duplicates = [], 0
    for items in short + long:
        want = sorted(items, key=lambda r: r["key"])  # Python's sort is stable
        if not stable_order_kept(items, want):
            raise AssertionError(f"oracle is not stable on {items}")
        duplicates += len({r["key"] for r in items}) < len(items)
        cases.append((json.dumps([items]), want))
    rust = compare(sides, path, "sort_items", cases, "stability")
    return {"file": path.as_posix(), "entry": "sort_items",
            "oracle": "Python sorted(key=key), which is stable",
            "stability": "observable: every item has a distinct id, and the whole output, ids included, must "
                         "equal the stable oracle's; equal keys keep their input order",
            "exhaustive": {"max_length": EXHAUSTIVE_MAX_LENGTH, "keys": list(EXHAUSTIVE_VALUES),
                           "ids": "positions", "inputs": len(short)},
            "seeded": {"inputs": len(long), "longest": max(map(len, long)), "ids": "distinct, shuffled"},
            "inputs": len(cases), "inputs_with_equal_keys": duplicates,
            "reference": "equal to the oracle on every input", "rust": rust}


# ---------------------------------------------------------------- routing

def invalid_reasons(r: dict, limit: int) -> list[str]:
    """Why a route is not valid under routing.weave's rule; empty for a valid route."""
    reasons = []
    if r["cost"] < 0:
        reasons.append("negative cost")
    if r["hops"] < 1:
        reasons.append("hops below 1")
    if r["hops"] > HOPS_LIMIT:
        reasons.append(f"hops over {HOPS_LIMIT}")
    if r["cost"] > limit:
        reasons.append("cost over limit")
    return reasons


def route_oracle(routes: list[dict], limit: int) -> dict:
    """The routing rule: a route is valid when 0 <= cost <= limit and 1 <= hops <= 16;
    the decision accepts the valid route of least cost, ties going to the lower
    destination, and is the rejection (accepted false, dest 0, cost 0) when no route
    is valid."""
    valid = [r for r in routes if not invalid_reasons(r, limit)]
    if not valid:
        return {"accepted": False, "dest": 0, "cost": 0}
    best = min(valid, key=lambda r: (r["cost"], r["dest"]))
    return {"accepted": True, "dest": best["dest"], "cost": best["cost"]}


def R(dest: int, cost: int, hops: int) -> dict:
    return {"dest": dest, "cost": cost, "hops": hops}


REJECT = {"accepted": False, "dest": 0, "cost": 0}

# (name, routes, limit, decision written by hand from the rule)
NAMED_ROUTES = [
    ("empty list", [], 10, REJECT),
    ("one valid route", [R(3, 4, 2)], 10, {"accepted": True, "dest": 3, "cost": 4}),
    ("negative cost is invalid even when cheapest", [R(1, -1, 1), R(2, 5, 1)], 10,
     {"accepted": True, "dest": 2, "cost": 5}),
    ("hops 0 is invalid", [R(1, 1, 0), R(2, 2, 1)], 10, {"accepted": True, "dest": 2, "cost": 2}),
    ("negative hops is invalid", [R(1, 1, -3)], 10, REJECT),
    ("hops 16 is valid", [R(1, 1, 16)], 10, {"accepted": True, "dest": 1, "cost": 1}),
    ("hops 17 is invalid", [R(1, 1, 17), R(2, 9, 16)], 10, {"accepted": True, "dest": 2, "cost": 9}),
    ("hops far over 16 is invalid", [R(1, 1, 1000)], 10, REJECT),
    ("cost equal to the limit is valid", [R(5, 10, 3)], 10, {"accepted": True, "dest": 5, "cost": 10}),
    ("cost one over the limit is invalid", [R(5, 11, 3)], 10, REJECT),
    ("cost 0 under limit 0 is valid", [R(2, 0, 1)], 0, {"accepted": True, "dest": 2, "cost": 0}),
    ("a negative limit admits nothing", [R(1, 0, 1), R(2, -1, 1)], -1, REJECT),
    ("all invalid", [R(1, -1, 1), R(2, 1, 0), R(3, 1, 17), R(4, 99, 2)], 10, REJECT),
    ("tie on cost goes to the lower dest", [R(7, 3, 1), R(2, 3, 9)], 10, {"accepted": True, "dest": 2, "cost": 3}),
    ("tie in the other order", [R(2, 3, 9), R(7, 3, 1)], 10, {"accepted": True, "dest": 2, "cost": 3}),
    ("tie with negative dests", [R(-1, 3, 1), R(-5, 3, 1), R(0, 3, 1)], 10,
     {"accepted": True, "dest": -5, "cost": 3}),
    ("cheaper beats lower dest", [R(1, 4, 1), R(9, 3, 1)], 10, {"accepted": True, "dest": 9, "cost": 3}),
    ("duplicate routes", [R(4, 2, 2), R(4, 2, 2)], 10, {"accepted": True, "dest": 4, "cost": 2}),
    ("cheapest invalid by hops, next chosen", [R(1, 1, 17), R(2, 2, 16), R(3, 2, 1)], 10,
     {"accepted": True, "dest": 2, "cost": 2}),
    ("integers wider than 64 bits", [R(2**70, 10**30, 1), R(-2**70, 10**30, 16)], 10**30,
     {"accepted": True, "dest": -2**70, "cost": 10**30}),
    ("C160 corpus input", [R(1, 5, 2), R(2, 3, 20), R(3, 3, 1), R(0, 3, 4)], 10,
     {"accepted": True, "dest": 0, "cost": 3}),
]

GRID_COSTS = (-1, 0, 1, 2, 3)
GRID_HOPS = (-1, 0, 1, 16, 17)
GRID_LIMITS = (-1, 0, 2)


def seeded_routes(rng: random.Random, count: int) -> list[tuple[list[dict], int]]:
    out = []
    for _ in range(count):
        limit = rng.choice([rng.randint(-2, 20), rng.randint(0, 10**25)]) if rng.random() < 0.2 else rng.randint(-2, 20)
        n = rng.randint(0, 30)
        routes = [R(rng.randint(-5, 5), rng.choice([rng.randint(-3, limit + 3), rng.randint(-3, 25)]),
                    rng.choice([rng.randint(-1, 18), 0, 1, 16, 17])) for _ in range(n)]
        out.append((routes, limit))
    return out


# (name, file, entry, --args text): requests P0-RUN-1 makes invalid (E540).
MALFORMED_REQUESTS = [
    ("route: missing hops", ROUTING, "route", '[[{"dest": 1, "cost": 2}], 10]'),
    ("route: extra field", ROUTING, "route", '[[{"dest": 1, "cost": 2, "hops": 1, "via": 3}], 10]'),
    ("route: duplicate field", ROUTING, "route", '[[{"dest": 1, "cost": 2, "cost": 3, "hops": 1}], 10]'),
    ("route: cost as a string", ROUTING, "route", '[[{"dest": 1, "cost": "2", "hops": 1}], 10]'),
    ("route: hops as a Bool", ROUTING, "route", '[[{"dest": 1, "cost": 2, "hops": true}], 10]'),
    ("route: dest with a fraction", ROUTING, "route", '[[{"dest": 1.5, "cost": 2, "hops": 1}], 10]'),
    ("route: cost with an exponent", ROUTING, "route", '[[{"dest": 1, "cost": 2e1, "hops": 1}], 10]'),
    ("route: null cost", ROUTING, "route", '[[{"dest": 1, "cost": null, "hops": 1}], 10]'),
    ("route: limit as a string", ROUTING, "route", '[[], "10"]'),
    ("route: routes not a list", ROUTING, "route", '[{"dest": 1, "cost": 2, "hops": 1}, 10]'),
    ("route: a list where a record goes", ROUTING, "route", '[[[1, 2, 1]], 10]'),
    ("route: one bad record among valid ones", ROUTING, "route",
     '[[{"dest": 1, "cost": 2, "hops": 1}, {"dest": 2, "cost": 2}], 10]'),
    ("route: missing limit", ROUTING, "route", "[[]]"),
    ("route: an extra argument", ROUTING, "route", "[[], 10, 1]"),
    ("route: arguments not an array", ROUTING, "route", '{"routes": [], "limit": 10}'),
    ("unknown function", ROUTING, "routes", "[[], 10]"),
    ("valid is not the entry's shape", ROUTING, "valid", "[[], 10]"),
    ("merge_sort: a Bool element", MERGE_SORT, "merge_sort", "[[1, true]]"),
    ("merge_sort: a fraction", MERGE_SORT, "merge_sort", "[[1.5]]"),
    ("merge_sort: two arguments", MERGE_SORT, "merge_sort", "[[1], [2]]"),
    ("sort_items: missing id", MERGE_SORT, "sort_items", '[[{"key": 1}]]'),
    ("sort_items: extra field", MERGE_SORT, "sort_items", '[[{"key": 1, "id": 2, "rank": 0}]]'),
    ("sort_items: Int where an Item goes", MERGE_SORT, "sort_items", "[[1, 2]]"),
]


def route(sides: Sides, rng: random.Random, path: Path = ROUTING, seeded: int = SEEDED_ROUTE_LISTS) -> dict:
    inputs: list[tuple[list[dict], int]] = []
    for name, routes, limit, decision in NAMED_ROUTES:
        if route_oracle(routes, limit) != decision:
            raise AssertionError(f"route oracle disagrees with the named case {name!r}")
        inputs.append((routes, limit))
    grid = [([R(1, c, h)], limit) for c in GRID_COSTS for h in GRID_HOPS for limit in GRID_LIMITS]
    generated = seeded_routes(rng, seeded)
    inputs += grid + generated
    reasons: dict[str, int] = {}
    valid_records = invalid_records = ties = 0
    for routes, limit in inputs:
        valid = [r for r in routes if not invalid_reasons(r, limit)]
        valid_records += len(valid)
        invalid_records += len(routes) - len(valid)
        for r in routes:
            for why in invalid_reasons(r, limit):
                reasons[why] = reasons.get(why, 0) + 1
        if valid:
            least = min(r["cost"] for r in valid)
            ties += len({r["dest"] for r in valid if r["cost"] == least}) > 1
    accepted = sum(route_oracle(r, limit)["accepted"] for r, limit in inputs)
    cases = [(json.dumps([routes, limit]), route_oracle(routes, limit)) for routes, limit in inputs]
    rust = compare(sides, path, "route", cases, "routing")
    return {"file": path.as_posix(), "entry": "route",
            "oracle": "route_oracle in scripts/p0_applications.py, written from the routing rule; it does not "
                      "call the reference",
            "named": len(NAMED_ROUTES), "single_route_grid": len(grid), "seeded": len(generated),
            "inputs": len(cases), "accepted_decisions": accepted, "rejections": len(cases) - accepted,
            "valid_records": valid_records, "invalid_records": invalid_records,
            "invalid_by_reason": dict(sorted(reasons.items())), "inputs_with_cost_ties": ties,
            "reference": "equal to the oracle on every input", "rust": rust}


def malformed(sides: Sides) -> dict:
    """Each malformed request is E540 at stage run on both sides; Rust exits 1 and reports no budget."""
    for name, path, entry, text in MALFORMED_REQUESTS:
        py = sides.reference(path, entry, text)
        if py != {"code": REQUEST_CODE, "stage": "run"}:
            raise AssertionError(f"invalid request {name}: Python reference {py}, required {REQUEST_CODE}")
    rust: dict = {"status": "skipped", "compared": 0}
    if sides.binary is not None:
        for name, path, entry, text in MALFORMED_REQUESTS:
            exit_code, doc = sides.rust(path, entry, [text])[0]
            got = rust_normalised(exit_code, doc)
            if got != {"code": REQUEST_CODE, "stage": "run", "exit": 1} or "budgets" in doc:
                raise AssertionError(f"invalid request {name}: Rust {got}, required {REQUEST_CODE} with exit 1 "
                                     f"and no budget used")
        rust = {"status": "compared", "compared": len(MALFORMED_REQUESTS)}
    return {"requests": len(MALFORMED_REQUESTS), "code": REQUEST_CODE, "rule": "P0-RUN-1",
            "cases": [name for name, *_ in MALFORMED_REQUESTS],
            "reference": f"{REQUEST_CODE} at stage run for every request", "rust": rust}


# ---------------------------------------------------------------- report

def build_report(binary: Path | None, how: str, seeded: int = SEEDED_LISTS,
                 seeded_route_lists: int = SEEDED_ROUTE_LISTS) -> dict:
    sides = Sides(binary, how)
    rng = random.Random(SEED)
    apps = {"merge_sort": merge_sort(sides, rng, seeded=seeded),
            "sort_items": sort_items(sides, rng, seeded=seeded),
            "route": route(sides, rng, seeded=seeded_route_lists)}
    requests = malformed(sides)
    compared = sum(a["rust"]["compared"] for a in apps.values()) + requests["rust"]["compared"]
    return {
        "scope": "Two P0 programs run with the ordinary weave run command and the Python P0 reference evaluator, "
                 "compared with Python oracles: values, and for invalid run requests the code, stage, exit "
                 "status and budget use. Regression evidence on these inputs, not a proof of correctness or "
                 "stability for all inputs. The concurrent fork/join merge sort is not covered (quaat/weave#42, M6).",
        "seed": SEED,
        "applications": apps,
        "invalid_run_requests": requests,
        "reference_runs": sides.reference_runs,
        "rust_comparison": rust_status(sides, compared),
    }


def main() -> int:
    binary, how = rust_binary()
    report = build_report(binary, how)
    out = ROOT / "validation"
    out.mkdir(exist_ok=True)
    (out / "p0-applications.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    apps, requests = report["applications"], report["invalid_run_requests"]
    print(f"PASS: P0 reference equals the oracles: merge_sort on {apps['merge_sort']['inputs']} lists, "
          f"sort_items on {apps['sort_items']['inputs']} lists (stability on ids), route on "
          f"{apps['route']['inputs']} route lists; {requests['requests']} invalid run requests give "
          f"{requests['code']} (seed {report['seed']})")
    rust = report["rust_comparison"]
    if binary is None:
        print(f"SKIP: {rust['note']}")
    else:
        print(f"PASS: weave run equals the oracles and the P0 reference on {rust['compared']} runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
