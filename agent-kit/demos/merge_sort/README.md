# Recursive concurrent merge sort in Weave

A stable ascending merge sort over integer lists. The recursion, comparisons,
branching, fork/join, and merge are written in [`merge_sort.weave`](merge_sort.weave).
They run on the kit's **pure-function extension**: a parser, checker, and
interpreter added in `.agents/skills/weave/scripts/weave_pure/` and exposed by
the existing runner as `check-pure` and `run-pure`. The vendored flow prototype
is unchanged. Recursive effectful flows are still rejected with `E218`.

`run_demo.py` only validates the input, calls `scripts/weave.py --json run-pure`,
and renders the runner's JSON. It does not sort. Python's `sorted()` appears only
in the tests, as an oracle.

## Prerequisites

Python 3.11 or newer (this run used Python 3.13.5; the kit reference is
3.12.14). No third-party packages, services, or network access are needed.

## Run

From the kit root (absolute-path invocation from any directory also works):

```bash
python3 demos/merge_sort/run_demo.py --values '[8,3,5,1,9,2,7,4,6]' --mode sequential
python3 demos/merge_sort/run_demo.py --values '[8,3,5,1,9,2,7,4,6]' --mode concurrent --trace
python3 demos/merge_sort/run_demo.py --values '[]' --mode concurrent
python3 demos/merge_sort/run_demo.py --values '[5,-2,5,0,-2]' --mode concurrent --json
python3 demos/merge_sort/run_demo.py --help
```

Results: `[1,2,3,4,5,6,7,8,9]` (both modes), `[]`, and `[-2,-2,0,5,5]`.

| Option | Default | Meaning |
| --- | --- | --- |
| `--values JSON` | required | JSON list of integers. Booleans, floats, strings, nulls, nested lists, and non-lists are rejected |
| `--mode` | `concurrent` | `concurrent` or `sequential` |
| `--trace` | off | Show the scheduler events of the actual run |
| `--json` | off | One JSON document on stdout; errors also go to stdout as JSON |
| `--max-values N` | 1000 | Demo input limit. At 1000 values the run peaks at 1,975 live activations, under the runner's 4,096 default |
| `--schedule`, `--seed` | `fifo`, 0 | Run-queue order (`fifo`, `lifo`, `random`) |
| `--workers`, `--quantum`, `--fuel`, `--max-tasks`, `--max-depth` | runner defaults 4, 16, 10,000,000, 4,096, 100,000 | Passed through to `run-pure` |
| `--source PATH` | `merge_sort.weave` | Alternative source (used by tests) |

Exit codes: 0 means success. 1 means the Weave checker rejected the source.
2 means invalid input or usage, a runtime fault (`E420`), or an exhausted limit
(`E421` fuel, `E422` depth, `E423` live activations). A failed run never prints a
partial result.

Direct runner use:

```bash
python3 scripts/weave.py check-pure demos/merge_sort/merge_sort.weave
python3 scripts/weave.py --json run-pure demos/merge_sort/merge_sort.weave --entry merge_sort --args '[[3,1,2]]' --trace
```

Tests:

```bash
python3 -B -m unittest discover -s demos/merge_sort/tests -v                      # demo + algorithm
python3 -B -m unittest tests.test_pure_language tests.test_pure_runtime          # extension
```

## Syntax actually used

`fn name(p: Type) -> Type:` with types `Int`, `Bool`, `IntList`, `IntListPair`;
`let`, `return expr`, terminal `if cond:` / `else:`, and `fork:` with exactly two
`let name = function(args)` branches. The only operator is `<=`. Integer literals
are allowed. The primitives are `length`, `is_empty`, `head`, `tail`, `cons`,
`split_half`, `first`, and `second`. Lists are persistent cons cells:
`head`/`tail`/`cons` are O(1) and share structure. `split_half` copies only the
first floor(n/2) nodes. The full rules and diagnostics are in
[docs/weave.md](../../docs/weave.md#pure-function-extension-kit-addition).

`merge_sort` returns lists of length ≤ 1 directly. Otherwise it splits the list
in order, forks two recursive sorts, and then calls `merge` once both results are
joined. `merge` is ordinary (non-fork) direct recursion. It takes from the left
on equal keys (`head(left) <= head(right)`), which with the contiguous split
makes the sort stable. The work is O(n log n). Because the merge is sequential,
the ideal span is O(n), not O(log n), and this small demo promises no speedup.

## Scheduling semantics

- **Concurrent mode.** Each `fork` creates two child activations with new task
  IDs and one shared fork ID; the parent becomes *waiting* and leaves the run
  queue. Each child produces one result envelope. The join fires only after both
  envelopes exist. It consumes them once, binds them in left/right source order,
  and requeues the parent once.
- **Interleaving.** One OS thread runs a cooperative round-robin scheduler. Each
  round dispatches up to `workers` runnable tasks, each for at most `quantum`
  interpreter instructions, so sibling activations interleave. This is
  concurrency, **not CPU parallelism**. Waiting parents occupy no worker slot, so
  even `--workers 1` cannot starve or deadlock.
- **Sequential mode.** The same compiled source runs the two fork calls one after
  the other inside one activation.
- **Frames.** Every activation keeps explicit interpreter frames, so recursion
  depth does not use the Python stack (3,000-element inputs are tested).
- **Failure.** When a child fails, its parent fails, the sibling subtree is
  cancelled, and the failure reaches the root with its diagnostic. No result is
  fabricated, and no task or join remains pending.
- **Trace events.** `activation_created`, `run` (progress: steps executed in a
  slice), `fork`, `wait`, `child_complete`, `join`, `root_complete`, `failure`,
  `cancelled`; plus `fork_inline`/`join_inline` in sequential mode.

## Limits and what is (not) established

- **Termination is not checked statically.** Fuel, depth, and task caps are
  resource limits that turn runaway programs into explicit errors. They are not
  termination proofs.
- **Tested, not proved:** sorting correctness against an oracle; stability via
  identity-tagged elements; scheduler pairing (unique IDs, one completion per
  child, one join per fork, join after both children, parent resumed once); no
  pending work after completion or failure; identical results across modes and
  schedules.
- No Inventory net, accounting certificate, or bounded ordering check applies to
  this task system. `check-pure` and `run-pure` never analyze a net.
- The extension supports only what this demo needs: no loops, arithmetic beyond
  `<=`, generics, mutual recursion, higher-order functions, effects, or linear
  handles in pure code, and no `fn` code inside flows.

## Files

- `merge_sort.weave`: the algorithm.
- `run_demo.py`: thin CLI over `run-pure`.
- `tests/test_merge_sort.py`: algorithm and CLI tests. Extension tests are in the
  kit's `tests/test_pure_language.py` and `tests/test_pure_runtime.py`.
- `artifacts/`: generated traces and the command log.
- `TEST_REPORT.md`: commands run and observed results.
