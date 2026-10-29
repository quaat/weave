# Merge-sort demo and pure-extension test report

Date: 2026-10-28. Interpreter: Python 3.13.5 (`doctor`: READY, no third-party
dependencies). The kit is not a Git repository, so there was no Git status to
preserve; the existing Tiny Shop demo was left untouched and its tests were rerun.
All commands were run from the kit root unless noted.

Note (kit 0.3.0, quaat/weave#8): the outputs quoted below are those of the kit at the
time of this report. The runner and demos now print each claim as a `LABEL statement`
line with one of the six result labels and report tool and runtime status separately
(`docs/commands.md`); the files in `artifacts/` were regenerated with the current output.

## Starting point

The original fragment had no `fn` declarations: the flow checker rejects them with
`E200` and rejects recursive flows with `E218`. It had no conditionals, scalar
computation, list runtime, or parallel/fork construct. The repository had not
already advanced beyond that fragment.

| Baseline command (before changes) | Exit | Result |
| --- | ---: | --- |
| `python3 scripts/weave.py doctor` | 0 | READY Python 3.13.5 |
| `python3 scripts/weave.py examples` | 0 | PASS 28/28 |
| `python3 scripts/weave.py test` | 0 | 107 tests OK |
| `python3 -B -m unittest discover -s tests -q` | 0 | 14 tests OK |

There were no pre-existing failures.

## What was implemented

- `.agents/skills/weave/scripts/weave_pure/` (kit code; vendored prototype unchanged):
  - `syntax.py`: line/indent parser and recursive-descent expression parser.
  - `check.py`: signature-first checking, types, terminal branches, effect
    exclusion, fork scope, and SCC-based mutual-recursion detection.
  - `values.py`: persistent cons-cell lists and the eight primitives.
  - `runtime.py`: compiler to an instruction list, plus a resumable frame machine
    with a bounded cooperative fork/join scheduler.
  - `cli.py`: the `check-pure` and `run-pure` runner commands.
- Runner (`.agents/skills/weave/scripts/weave.py`): registers the two commands and
  adds manifest kind `pure`.
- Corpus: 2 valid and 4 invalid pure fixtures. `examples` now has 34 expectations.
  The only changed existing assertion is the corpus count in
  `tests/test_runner.py` (28 → 34).
- Docs: `docs/weave.md` (synced to the skill reference via
  `scripts/sync_skill_reference.py`), `docs/commands.md`,
  `docs/prototype-status.md`, `docs/validation.md` addendum, skill `SKILL.md`,
  `AGENTS.md`, `README.md`, and a `kit_extensions` record in `PROVENANCE.json`.
  `prototype_changes` stays `none`, and the hash checks still pass.

## Demo commands (log: `artifacts/demo-run-log.txt`)

| Command | Exit | Observed |
| --- | ---: | --- |
| `run_demo.py --values '[8,3,5,1,9,2,7,4,6]' --mode sequential` | 0 | `Sorted: [1, 2, 3, 4, 5, 6, 7, 8, 9]`; 693 instructions, 1 activation, 0 forks |
| `run_demo.py --values '[8,3,5,1,9,2,7,4,6]' --mode concurrent --trace` | 0 | Same output; 677 instructions, 17 activations, 8 forks, 8 joins, max live 15, max frames 10; trace in `artifacts/trace-concurrent.txt` |
| `run_demo.py --values '[]' --mode concurrent` | 0 | `Sorted: []`; 7 instructions, 1 activation |
| `run_demo.py --values '[5,-2,5,0,-2]' --mode concurrent --json` | 0 | `"output": [-2, -2, 0, 5, 5]`, 4 forks/joins, `pending_tasks: 0` (`artifacts/mixed-sign.json`) |
| `run_demo.py --help` | 0 | usage text |
| `--values '[1,true]'` / `--values '[1.5]'` | 2 / 2 | `error: --values[1] must be an integer, got true` / `… got 1.5` |
| `--values '[5,4,3,2,1]' --fuel 20` | 2 | `E421` fuel exhausted in `merge_sort` |
| `--values '[5,4,3,2,1]' --max-tasks 2` | 2 | `E423` live activation limit (line 13) |
| absolute path from `/tmp`, `--values '[3,2,1]'` | 0 | `Sorted: [1, 2, 3]` |
| `run_demo.py … --quantum 1 --workers 2 --json --trace` | 0 | Before the first root child completed, task 2 ran 84 one-instruction slices and task 3 ran 22 (`artifacts/trace-concurrent-quantum1.json`) |

Runner commands:

| Command | Exit | Observed |
| --- | ---: | --- |
| `scripts/weave.py check-pure demos/merge_sort/merge_sort.weave` | 0 | `CHECKED … merge_sort, merge (pure; termination not checked)`; no net analysis output |
| `scripts/weave.py run-pure … --entry merge_sort --args '[[8,3,5,1,9,2,7,4,6]]'` | 0 | `RESULT [1, 2, …, 9]`, `forks=8 joins=8 max_live=15` |
| `scripts/weave.py check examples/invalid/recursion.weave` | 1 | `E218` Recursive flow calls are unsupported (unchanged) |
| `scripts/weave.py check-pure` on `pure_last`, `pure_fork`, `pure_mutual` | 1 | First two CHECKED; `pure_mutual` → `E411` line 2 |

An informal timing at the demo limit was n = 1000 random values in about 0.24 s
wall time (204,254 instructions, 1,999 activations, peak 1,975 live). This is not
a benchmark.

## Test results (final run)

| Command | Exit | Result |
| --- | ---: | --- |
| `python3 -B -m unittest discover -s demos/merge_sort/tests -v` | 0 | 13 tests OK |
| `python3 -B -m unittest tests.test_pure_language tests.test_pure_runtime` | 0 | 45 tests OK (24 language, 21 runtime) |
| `python3 -B -m unittest discover -s tests -q` | 0 | 59 tests OK (14 original runner + 45 extension) |
| `python3 scripts/weave.py examples` | 0 | PASS 34/34 |
| `python3 scripts/weave.py test` | 0 | 107 tests OK (vendored prototype) |
| `python3 -B -m unittest discover -s demos/tiny_shop/tests -q` | 0 | 17 tests OK (existing demo unaffected) |

During development, three failures came from my own test expectations, and each
was fixed by correcting the expectation, not the code. (1) A diagnostic line
number was miscounted. (2–3) A 3,000-element concurrent run correctly hit the
4,096 live-activation limit (`E423`) before the depth limit, so those tests now
set `max_tasks` explicitly.

What the tests cover:

- **Algorithm.** The named cases were run in sequential mode, concurrent fifo,
  concurrent lifo (workers 1, quantum 1), and random (seed 11): empty, singleton,
  two, sorted, reverse, duplicates, all-equal, negative, mixed-sign, odd, and even
  lengths. Also covered:
  - all 364 inputs over {-1, 0, 1} of length 0–5;
  - 60 seeded random cases;
  - properties: nondecreasing output, equal multisets, unchanged input,
    idempotence.
- **Stability.** Identity-based, using a test-only `int` subclass that carries
  the original position through `head`/`cons`. Equal keys keep their original
  order in every mode. A temporary mutation that takes from the right on equal
  keys was observed to change the tag order (`[1,3,0,2,4]` → `[3,1,4,2,0]`),
  showing the instrumentation can tell the difference. `merge` on equal heads
  takes left first.
- **Language.** Covered:
  - direct recursion, base cases, nested returns, forward references;
  - every body checked, including unused functions;
  - return/argument/arity errors and unknown functions or primitives (`sorted`,
    `merge_sorted` → `E404`);
  - malformed branches, rebinding, mutual and indirect recursion;
  - `Hold`/`Escrow` in signatures (`E401`); `Payments.charge`,
    `Inventory.reserve`, `await`, and flow calls (`E409`); mixed files (`E410`);
  - fork-scope violations (`E412`);
  - unsupported syntax: `while`, `+`, `-`, chained `<=`, `match`, tabs;
  - `check-pure` reports no accounting or ordering status; flow `check` still
    gives `E218`/`E200`.
- **Runtime.**
  - `head`/`tail` of an empty list (`E420` with source line).
  - A non-terminating function fails with `E421` under a 5,000-instruction budget
    (subprocess, 60 s timeout).
  - Depth limit (`E422`); fork bomb (`E423`, cleanup verified).
  - 3,000-element input (3× Python's recursion limit) in both modes, with
    max frames above the host recursion limit.
  - Input decoding (`E424`) and unknown entry (`E425`).
  - Persistent-list sharing and split balance.
  - A renamed function runs. Changing the comparison in a temporary copy yields
    descending output, and changing a branch yields a different result.
- **Concurrency.**
  - With quantum 1, both root children progress before either completes.
  - A controlled chooser hook forces left-first and right-first completion; the
    non-commutative `append(l, r)` join and merge sort still produce left/right
    source order.
  - A pairing checker (unique IDs, parent correlation, one completion per child,
    one join per fork after both children, parent resumed after join, one
    `root_complete`, zero pending) runs across fifo/lifo/random × workers
    {1, 2, 8} × quantum {1, 5, 64}.
  - Waiting parents are never dispatched. `workers=1` with 255 nested forks
    completes.
  - On child failure, the parent fails with the child as cause, the sibling is
    cancelled, and there is no join or root completion. A deep failure leaves
    every activation completed, failed, or cancelled, with nothing pending.

## Status labels and remaining limits

- `CHECKED`: the pure program satisfies the extension's type, branch, effect,
  fork-scope, and recursion-shape rules. **Termination is not checked.**
- `EXECUTED`: one run under explicit resource limits. Fuel, depth, and task limits
  are resource limits, not termination proofs.
- Scheduler and sorting properties are **tested only**, not proved or
  bounded-checked. The Inventory accounting certificate and ordering model say
  nothing about this task system.
- Concurrency is cooperative on one OS thread. There are no CPU-parallel workers
  and no speedup is claimed. The merge is sequential (span O(n)).
- Out of scope: loops, arithmetic other than `<=`, generics, mutual recursion,
  higher-order functions, recursive effectful flows, mixing `fn` and flow
  declarations in one file, and calling pure functions from flows.
- Not exercised: Python 3.11/3.12 (only 3.13.5 was run), Windows, and macOS.
