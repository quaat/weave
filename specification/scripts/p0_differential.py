#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Compare the Rust P0 implementation with the Python reference (docs/chapters/pure.rst).

Inputs:

* the P0 corpus, ``examples/pure/manifest.json``: every check case and run case,
  against both implementations and against the manifest's expectation;
* sequential merge sort (``examples/pure/valid/merge_sort.weave``) on every list of
  length 0 to 5 over {0, 1, 2} and on seeded random lists, against Python ``sorted``;
* seeded generated programs: well-typed programs run on random arguments under
  random budgets, and copies with one injected static error whose code is known;
* the nesting limits of pure.rst: inputs just under and just over the syntax depth
  and expression depth limits, which both implementations must classify alike.

Compared: the static code (or ACCEPT), the outcome kind, the value, the fault or
exhaustion kind, the diagnostic code, and the budget usage. The Rust side is the
``weave`` binary named by ``WEAVE_BIN`` or built with ``cargo build --offline
--locked``. Without either, the Python reference is still checked against the
corpus expectations, and the comparison is recorded as not established in
``validation/p0-differential.json``, never as agreement.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
import p0_reference as ref  # noqa: E402

EXAMPLES = ROOT / "examples"
MANIFEST = EXAMPLES / "pure/manifest.json"
FORMAT = "weave-p0-conformance-v1"
SEED = 20261030
GENERATED_PROGRAMS = 40
RUNS_PER_PROGRAM = 4


# ---------------------------------------------------------------- the two sides

def manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"{MANIFEST}: unsupported format {data.get('format')!r}; expected {FORMAT}")
    return data


_CHECKED: dict[str, tuple[str, object]] = {}


def python_check(source: str) -> tuple[str, object]:
    """The reference's static result, parsed once per distinct source."""
    if source not in _CHECKED:
        try:
            _CHECKED[source] = ("ACCEPT", ref.check(source))
        except ref.Diagnostic as d:
            _CHECKED[source] = (d.code, None)
    return _CHECKED[source]


def python_run(source: str, entry: str, args, budgets: dict | None) -> dict:
    code, program = python_check(source)
    if program is None:
        return {"code": code}
    try:
        report = ref.run(program, entry, args, budgets or {})
    except ref.Diagnostic as d:
        return {"code": d.code}
    return normalise(report, [d.code for d in report["diagnostics"]])


def normalise(report: dict, codes: list[str]) -> dict:
    b = report["budgets"]
    return {"code": codes[0] if codes else "VALUE", "outcome": report["outcome"], "value": report["value"],
            "fault": report["fault"], "exhausted": report["exhausted"],
            "usage": {"fuel": b["fuel"]["used"], "depth": b["depth"]["max"], "int_bits": b["int_bits"]["max"]}}


def rust_binary() -> tuple[Path | None, str]:
    named = os.environ.get("WEAVE_BIN")
    if named:
        path = Path(named)
        if not path.is_file():
            raise FileNotFoundError(f"WEAVE_BIN={named} is not a file")
        return path, "WEAVE_BIN"
    cargo = shutil.which("cargo")
    if cargo is None:
        return None, "cargo is not on PATH and WEAVE_BIN is not set"
    if not (REPO / "Cargo.toml").is_file():
        return None, "no Cargo workspace next to the specification"
    subprocess.run([cargo, "build", "--quiet", "--offline", "--locked", "-p", "weave-cli", "--bin", "weave"],
                   cwd=REPO, check=True)
    return REPO / "target" / "debug" / ("weave.exe" if os.name == "nt" else "weave"), "cargo build --offline --locked"


def rust(binary: Path, argv: list[str], source: str) -> dict:
    done = subprocess.run([str(binary), *argv, "-", "--json"], input=source.encode("utf-8"),
                          capture_output=True, timeout=300)
    if done.returncode not in (0, 1, 3, 4):
        raise RuntimeError(f"weave {' '.join(argv)} exited {done.returncode}: {done.stderr.decode(errors='replace')}")
    return json.loads(done.stdout)


def rust_check(binary: Path, source: str) -> str:
    out = rust(binary, ["check"], source)
    return out["diagnostics"][0]["code"] if out["diagnostics"] else "ACCEPT"


def rust_run(binary: Path, source: str, entry: str, args, budgets: dict | None) -> dict:
    argv = ["run", "--entry", entry, "--args", json.dumps(args)]
    for key, flag in (("fuel", "--fuel"), ("depth", "--max-depth"), ("int_bits", "--int-bits")):
        if budgets and key in budgets:
            argv += [flag, str(budgets[key])]
    out = rust(binary, argv, source)
    codes = [d["code"] for d in out["diagnostics"]]
    if out.get("outcome") is None:
        return {"code": codes[0]}
    return normalise(out, codes)


# ---------------------------------------------------------------- corpus

def expected_of(case: dict) -> dict:
    if case["kind"] == "check" or case["expect"] == "E540":
        return {"code": case["expect"]}
    want = {"code": case["expect"]}
    if case["expect"] == "VALUE":
        want["value"] = case["value"]
    if "usage" in case:
        want["usage"] = case["usage"]
    return want


def meets(result: dict, want: dict) -> bool:
    return all(result.get(k) == v for k, v in want.items())


def corpus(binary: Path | None) -> list[dict]:
    rows = []
    for case in manifest()["cases"]:
        source = (EXAMPLES / case["file"]).read_text(encoding="utf-8")
        want = expected_of(case)
        if case["kind"] == "check":
            py = {"code": python_check(source)[0]}
            rs = {"code": rust_check(binary, source)} if binary else None
        else:
            py = python_run(source, case["entry"], case["args"], case.get("budgets"))
            rs = rust_run(binary, source, case["entry"], case["args"], case.get("budgets")) if binary else None
        if not meets(py, want):
            raise AssertionError(f"{case['id']} {case['file']}: Python reference {py}, expected {want}")
        if rs is not None and rs != py:
            raise AssertionError(f"{case['id']} {case['file']}: Rust {rs}, Python reference {py}")
        rows.append({"id": case["id"], "kind": case["kind"], "expected": case["expect"], "python": py["code"],
                     **({"rust": rs["code"]} if rs is not None else {})})
    return rows


def merge_sort_inputs(rng: random.Random) -> list[list[int]]:
    lists: list[list[int]] = [[]]
    frontier: list[list[int]] = [[]]
    for _ in range(5):
        frontier = [xs + [v] for xs in frontier for v in (0, 1, 2)]
        lists += frontier
    for _ in range(40):
        lists.append([rng.randint(-1000, 1000) for _ in range(rng.randint(0, 60))])
    return lists


def merge_sort(binary: Path | None, rng: random.Random) -> dict:
    source = (EXAMPLES / "pure/valid/merge_sort.weave").read_text(encoding="utf-8")
    inputs = merge_sort_inputs(rng)
    for xs in inputs:
        py = python_run(source, "merge_sort", [xs], None)
        if py.get("value") != sorted(xs):
            raise AssertionError(f"merge_sort({xs}): Python reference {py}")
        if binary is not None:
            rs = rust_run(binary, source, "merge_sort", [xs], None)
            if rs != py:
                raise AssertionError(f"merge_sort({xs}): Rust {rs}, Python reference {py}")
    return {"inputs": len(inputs), "oracle": "Python sorted()"}


# ---------------------------------------------------------------- generated programs

class Generator:
    """Seeded well-typed P0 programs over Int, Bool, List[Int] and one record."""

    TYPES = ("Int", "Bool", "List[Int]", "Pair")

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.functions: list[tuple[str, list[tuple[str, str]], str]] = []
        self.fresh = 0

    def name(self, prefix: str) -> str:
        self.fresh += 1
        return f"{prefix}{self.fresh}"

    def literal(self) -> str:
        r = self.rng.random()
        if r < 0.05:
            return str(self.rng.randint(10**20, 10**25))
        return str(self.rng.choice([0, 1, 2, 3, 5, 7, 10, 100]))

    def synth_list(self, scope: dict, depth: int) -> str:
        """A List[Int] expression for a position without an expected type, where [] is E511."""
        text = self.expr("List[Int]", scope, depth)
        return "cons(0, [])" if text == "[]" else text

    def expr(self, ty: str, scope: dict, depth: int) -> str:
        rng = self.rng
        vars_ = [n for n, t in scope.items() if t == ty]
        if depth <= 0 or rng.random() < 0.25:
            if vars_ and rng.random() < 0.7:
                return rng.choice(vars_)
            return {"Int": self.literal, "Bool": lambda: rng.choice(["true", "false"]),
                    "List[Int]": lambda: rng.choice(["[]", f"[{self.literal()}]"]),
                    "Pair": lambda: f"Pair(a: {self.literal()}, b: {self.literal()})"}[ty]()
        d = depth - 1
        e = lambda t: self.expr(t, scope, d)  # noqa: E731
        calls = [f for f in self.functions if f[2] == ty]
        if ty == "Int":
            options = [lambda: f"{e('Int')} + {e('Int')}", lambda: f"{e('Int')} - {e('Int')}",
                       lambda: f"({e('Int')}) * ({e('Int')})", lambda: f"-({e('Int')})",
                       lambda: f"div({e('Int')}, {e('Int')})", lambda: f"mod({e('Int')}, {e('Int')})",
                       lambda: f"length({self.synth_list(scope, d)})", lambda: f"head({self.synth_list(scope, d)})"]
            pairs = [n for n, t in scope.items() if t == "Pair"]
            if pairs:
                options.append(lambda: f"{rng.choice(pairs)}.{rng.choice('ab')}")
        elif ty == "Bool":
            options = [lambda: f"{e('Int')} {rng.choice(['<', '<=', '>', '>=', '==', '!='])} {e('Int')}",
                       lambda: f"({e('Bool')}) {rng.choice(['and', 'or'])} ({e('Bool')})",
                       lambda: f"not({e('Bool')})", lambda: f"is_empty({self.synth_list(scope, d)})",
                       lambda: f"({e('Bool')}) {rng.choice(['==', '!='])} ({e('Bool')})"]
        elif ty == "List[Int]":
            options = [lambda: f"cons({e('Int')}, {e('List[Int]')})", lambda: f"tail({self.synth_list(scope, d)})",
                       lambda: f"[{e('Int')}, {e('Int')}]"]
        else:
            options = [lambda: f"Pair(a: {e('Int')}, b: {e('Int')})", lambda: f"Pair(b: {e('Int')}, a: {e('Int')})"]
        if calls and rng.random() < 0.3:
            fname, params, _ = rng.choice(calls)
            return f"{fname}({', '.join(e(t) for _, t in params)})"
        return rng.choice(options)()

    def block(self, ret: str, scope: dict, indent: int, depth: int) -> list[str]:
        pad = "    " * indent
        lines, scope = [], dict(scope)
        for _ in range(self.rng.randint(0, 2)):
            ty = self.rng.choice(self.TYPES)
            name = self.name("v")
            value = self.synth_list(scope, 3) if ty == "List[Int]" else self.expr(ty, scope, 3)
            lines.append(f"{pad}let {name} = {value}")
            scope[name] = ty
        if depth > 0 and self.rng.random() < 0.4:
            lines.append(f"{pad}if {self.expr('Bool', scope, 2)}:")
            lines += self.block(ret, scope, indent + 1, depth - 1)
            lines.append(f"{pad}else:")
            lines += self.block(ret, scope, indent + 1, depth - 1)
        else:
            lines.append(f"{pad}return {self.expr(ret, scope, 3)}")
        return lines

    def program(self) -> tuple[str, list[tuple[str, list[tuple[str, str]], str]]]:
        out = ["record Pair:", "    a: Int", "    b: Int", ""]
        for _ in range(self.rng.randint(1, 4)):
            name = self.name("f")
            params = [(self.name("p"), self.rng.choice(self.TYPES)) for _ in range(self.rng.randint(0, 3))]
            ret = self.rng.choice(self.TYPES)
            sig = ", ".join(f"{p}: {t}" for p, t in params)
            out.append(f"fn {name}({sig}) -> {ret}:")
            out += self.block(ret, dict(params), 1, 2)
            out.append("")
            self.functions.append((name, params, ret))
        rec = self.name("r")
        step = self.expr("Int", {"n": "Int", "acc": "Int"}, 2)
        out += [f"fn {rec}(n: Int, acc: Int) -> Int:", "    if n <= 0:", "        return acc", "    else:",
                f"        return {rec}(n - 1, {step})", ""]
        self.functions.append((rec, [("n", "Int"), ("acc", "Int")], "Int"))
        return "\n".join(out), self.functions

    def value(self, ty: str):
        rng = self.rng
        if ty == "Int":
            return rng.choice([0, 1, -1, 2, 3, -7, 100, rng.randint(-10**6, 10**6), 2**70])
        if ty == "Bool":
            return rng.random() < 0.5
        if ty == "List[Int]":
            return [self.value("Int") for _ in range(rng.randint(0, 4))]
        return {"a": self.value("Int"), "b": self.value("Int")}

    def budgets(self) -> dict | None:
        r = self.rng.random()
        if r < 0.5:
            return None
        return {k: v for k, v in (("fuel", self.rng.choice([1, 2, 5, 50])), ("depth", self.rng.choice([1, 2, 3, 20])),
                                  ("int_bits", self.rng.choice([4, 16, 64, 200]))) if self.rng.random() < 0.7}


# One static error appended to a valid program, with the code the chapter requires.
MUTATIONS = [
    ("E501", "fn head(x: Int) -> Int:\n    return x\n"),
    ("E504", "fn zz_hold(h: Hold[t, o]) -> Int:\n    return 0\n"),
    ("E505", "fn zz_unknown(x: Int) -> Int:\n    return zz_missing + x\n"),
    ("E506", "fn zz_shadow(x: Int) -> Int:\n    let x = 1\n    return x\n"),
    ("E507", "fn zz_arity(x: Int) -> Int:\n    return zz_arity(x, x)\n"),
    ("E508", "fn zz_pair() -> Pair:\n    return Pair(a: 1)\n"),
    ("E509", "fn zz_field(p: Pair) -> Int:\n    return p.c\n"),
    ("E510", "fn zz_type(x: Int) -> Bool:\n    return x + 1\n"),
    ("E511", "fn zz_empty() -> Int:\n    return length([])\n"),
    ("E512", "fn zz_effect(x: Int) -> Int:\n    return Payments.charge(x)\n"),
    ("E513", "fn zz_await(x: Int) -> Int:\n    return await Inventory.reserve(x)\n"),
    ("E514", "fn zz_fork(x: Int) -> Int:\n    fork:\n        let y = x\n    return x\n"),
    ("E515", "fn zz_path(x: Int) -> Int:\n    if x < 0:\n        return 0\n    return x\n"),
    ("E516", "fn zz_even(n: Int) -> Bool:\n    return n == 0 or zz_odd(n - 1)\n\n"
             "fn zz_odd(n: Int) -> Bool:\n    return n != 0 and zz_even(n - 1)\n"),
    ("E500", "fn zz_chain(x: Int) -> Bool:\n    return 0 < x < 9\n"),
]


def generated(binary: Path | None, rng: random.Random, programs: int = GENERATED_PROGRAMS) -> dict:
    runs = mutants = outcomes = 0
    kinds: dict[str, int] = {}
    injected: dict[str, int] = {}
    for index in range(programs):
        gen = Generator(rng)
        source, functions = gen.program()
        code = python_check(source)[0]
        if code != "ACCEPT":
            raise AssertionError(f"generated program rejected by the reference ({code}):\n{source}")
        if binary is not None and rust_check(binary, source) != "ACCEPT":
            raise AssertionError(f"generated program rejected by Rust:\n{source}")
        for _ in range(RUNS_PER_PROGRAM):
            name, params, _ = rng.choice(functions)
            args = [gen.value(t) for _, t in params]
            budgets = gen.budgets()
            py = python_run(source, name, args, budgets)
            kinds[py["code"]] = kinds.get(py["code"], 0) + 1
            if binary is not None:
                rs = rust_run(binary, source, name, args, budgets)
                if rs != py:
                    raise AssertionError(f"{name}{args} {budgets}: Rust {rs}, Python {py}\n{source}")
                outcomes += 1
            runs += 1
        want, text = MUTATIONS[index % len(MUTATIONS)]
        injected[want] = injected.get(want, 0) + 1
        mutant = source + "\n" + text
        py_code = python_check(mutant)[0]
        if py_code != want:
            raise AssertionError(f"mutant: Python reference {py_code}, expected {want}\n{mutant}")
        if binary is not None and rust_check(binary, mutant) != want:
            raise AssertionError(f"mutant: Rust {rust_check(binary, mutant)}, expected {want}\n{mutant}")
        mutants += 1
    return {"seed": SEED, "programs": programs, "runs": runs, "mutants": mutants,
            "outcome_codes": dict(sorted(kinds.items())), "mutant_codes": dict(sorted(injected.items())),
            "compared_runs": outcomes}


def _int_fn(expr: str) -> str:
    return f"fn f(x: Int) -> Int:\n    return {expr}\n"


def _bool_fn(expr: str) -> str:
    return f"fn f(x: Bool) -> Bool:\n    return {expr}\n"


_G = "fn g(x: Int) -> Int:\n    return x\n\n"
E = ref.EXPR_DEPTH_LIMIT

# (name, source, required code) at and just over each nesting limit.
LIMIT_PROBES = [
    ("sum chain at the expression limit", _int_fn(" + ".join(["x"] * E)), "ACCEPT"),
    ("sum chain over the expression limit", _int_fn(" + ".join(["x"] * (E + 1))), "E500"),
    ("product chain over the limit", _int_fn(" * ".join(["x"] * (E + 1))), "E500"),
    ("and chain at the limit", _bool_fn(" and ".join(["x"] * E)), "ACCEPT"),
    ("or chain over the limit", _bool_fn(" or ".join(["x"] * (E + 1))), "E500"),
    ("long sum chain", _int_fn(" + ".join(["x"] * 2000)), "E500"),
    ("unary minus at the limit", _int_fn("-" * (E - 1) + "1"), "ACCEPT"),
    ("unary minus over the limit", _int_fn("-" * E + "1"), "E500"),
    ("parentheses at the syntax limit", _int_fn("(" * 41 + "1" + ")" * 41), "ACCEPT"),
    ("parentheses over the syntax limit", _int_fn("(" * 42 + "1" + ")" * 42), "E500"),
    ("parenthesised name over the syntax limit", _int_fn("(" * 41 + "x" + ")" * 41), "E500"),
    ("nested calls at the syntax limit", _G + _int_fn("g(" * 28 + "x" + ")" * 28), "ACCEPT"),
    ("nested calls over the syntax limit", _G + _int_fn("g(" * 29 + "x" + ")" * 29), "E500"),
    ("parentheses far over the parser limit", _int_fn("(" * 70 + "1" + ")" * 70), "E500"),
]


def limits(binary: Path | None) -> dict:
    for name, source, want in LIMIT_PROBES:
        py = python_check(source)[0]
        if py != want:
            raise AssertionError(f"limit probe {name}: Python reference {py}, required {want}")
        if binary is not None and rust_check(binary, source) != py:
            raise AssertionError(f"limit probe {name}: Rust {rust_check(binary, source)}, Python reference {py}")
    return {"probes": len(LIMIT_PROBES), "syntax_depth_limit": ref.SYNTAX_DEPTH_LIMIT,
            "expression_depth_limit": ref.EXPR_DEPTH_LIMIT}


def build_report(binary: Path | None, how: str, programs: int = GENERATED_PROGRAMS) -> dict:
    """Run every comparison; without a binary, check the reference alone and say so."""
    rng = random.Random(SEED)
    rows = corpus(binary)
    sorting = merge_sort(binary, rng)
    gen = generated(binary, rng, programs)
    bounds = limits(binary)
    report = {
        "scope": "Rust weave versus the Python P0 reference evaluator: static codes, outcome kinds, values, fault and "
                 "exhaustion kinds, diagnostic codes and budget usage. Regression evidence on these inputs, not a proof "
                 "of equivalence.",
        "corpus": {"cases": len(rows), "rows": rows},
        "merge_sort": sorting,
        "generated": gen,
        "limits": bounds,
    }
    if binary is None:
        report["rust_differential"] = {"status": "skipped", "compared": 0,
                                       "note": f"Rust/Python P0 agreement not established: {how}."}
    else:
        report["rust_differential"] = {"status": "compared", "binary": how,
                                       "compared": len(rows) + sorting["inputs"] + gen["runs"] + gen["mutants"]
                                       + gen["programs"] + bounds["probes"]}
    return report


def main() -> int:
    binary, how = rust_binary()
    report = build_report(binary, how)
    rows, sorting, gen = report["corpus"]["rows"], report["merge_sort"], report["generated"]
    out = ROOT / "validation"
    out.mkdir(exist_ok=True)
    (out / "p0-differential.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: P0 reference meets {len(rows)} corpus expectations; merge sort agrees with sorted() on "
          f"{sorting['inputs']} lists; {gen['programs']} generated programs, {gen['runs']} runs, {gen['mutants']} mutants; "
          f"{report['limits']['probes']} nesting-limit probes")
    if binary is None:
        print(f"SKIP: {report['rust_differential']['note']}")
    else:
        print(f"PASS: Rust weave agrees with the P0 reference on {report['rust_differential']['compared']} inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
