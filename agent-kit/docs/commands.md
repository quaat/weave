# Runner commands

Run commands from the kit root. `scripts/weave.py` delegates to
`.agents/skills/weave/scripts/weave.py`. The latter also works by absolute path
from any directory, including after copying the canonical skill elsewhere.

| Command | Purpose |
| --- | --- |
| `doctor` | Report interpreter and bundled-file availability |
| `check FILE [FILE ...]` | Validate net, prove accounting, explore ordering, and check each flow file |
| `analyze` | Validate net, prove accounting, and explore ordering |
| `lower FILE --output PATH` | Check original flow, lower `?`, check lowered flow, and write output |
| `simulate FILE --entry NAME --outcome all` | Run scalar-entry source with each scripted outcome |
| `verify CERTIFICATE` | Recheck source-bound accounting; no ordering claim |
| `examples` | Run teaching-corpus expectations |
| `test` | Run the bundled prototype's regression suite |
| `check-pure FILE [FILE ...]` | Kit extension: check pure `fn` programs; reads no net |
| `run-pure FILE --entry NAME --args JSON` | Kit extension: check, then execute a pure entry function; reads no net |

`--net PATH` is available for `check`, `analyze`, `lower`, `simulate`, and `verify`.
The default is the bundled `Inventory.weave`, not a net inferred from your current
directory. `--max-states N` is available for `check`, `analyze`, and `lower`;
`simulate` retains the upstream default of 10,000 states. A net without an order
model cannot pass combined checks. Use upstream `checker.py prove NET` only when
accounting alone is explicitly the intended scope.

Batch flow files are checked independently: helpers are not linked across files.
Put mutually calling helpers in one file. Unused helper bodies are checked too.

## Examples

```bash
python3 scripts/weave.py --json check examples/valid/checkout.weave examples/valid/checkout_composed.weave
python3 scripts/weave.py analyze --net examples/nets/Inventory.weave --certificate proof.json
python3 scripts/weave.py verify proof.json --net examples/nets/Inventory.weave
python3 scripts/weave.py lower examples/valid/checkout_propagating.weave --output lowered.weave
python3 scripts/weave.py simulate examples/valid/checkout_propagating.weave --entry checkout_propagating --outcome Unknown --trace
python3 scripts/weave.py test --pattern test_composition.py --verbose
```

Put `--json` **before** the subcommand. It emits one JSON object with `command`
and `ok`. Rejections contain `diagnostic`, a `weave-diagnostic-v1` document with
`format`, `code`, `category`, `rule`, `secondary_rules`, `severity`, `stage`,
`message`, `span` (file, start and end line and column), `related` and
`details`; see the Diagnostics section of `docs/weave.md`. Batch checks put
diagnostics in corresponding `files` elements.
Results separate `accounting` from `ordering`, including bounds and assumptions.
Simulation returns `runs` with final `marking`; `--trace` adds complete `events`.

Text successes are compact; diagnostics retain full explanations and print
`file:line:column: CODE (RULE) [stage]`, followed by any related locations. There is no
persistent result cache. Only explicit `--certificate` and `--output` write files.
Output directories must exist; existing outputs are replaced, but input paths
cannot be output paths. The runner suppresses bytecode writes.

| Exit | Meaning |
| --- | --- |
| `0` | Requested checks or expected corpus outcomes succeeded |
| `1` | Weave rejection, counterexample, bounds exhaustion, unexpected corpus result, or failed/empty test selection |
| `2` | Usage, I/O, rejected certificate data, or unsupported/failed scripted execution |

A `CheckError` in a certificate's source net returns 1. Argument errors use
argparse's standard text diagnostics even with `--json`. Exit 0 does not establish
anything beyond the operation's documented scope.

## Pure-function extension commands

These commands belong to the kit's pure-function extension (`weave_pure`), not the
vendored prototype. They never parse, prove, or explore a net, and they report no
accounting or ordering status. `--net` and `--max-states` are not accepted.

```bash
python3 scripts/weave.py check-pure demos/merge_sort/merge_sort.weave
python3 scripts/weave.py --json run-pure demos/merge_sort/merge_sort.weave --entry merge_sort --args '[[3,1,2]]'
python3 scripts/weave.py run-pure demos/merge_sort/merge_sort.weave --entry merge_sort --args '[[3,1,2]]' --mode sequential --trace
```

| `run-pure` option | Default | Meaning |
| --- | --- | --- |
| `--entry NAME` | required | Entry function |
| `--args JSON` | `[]` | JSON array with one value per parameter. `Int`: integer (not boolean); `Bool`: `true`/`false`; `IntList`: list of integers; `IntListPair`: two integer lists |
| `--mode` | `concurrent` | `concurrent` (child activations via the cooperative scheduler) or `sequential` (fork calls run one after the other) |
| `--schedule` / `--seed` | `fifo` / `0` | Run-queue order: `fifo`, `lifo`, or seeded `random` |
| `--workers N` | 4 | Runnable tasks dispatched per scheduling round, all on one OS thread |
| `--quantum N` | 16 | Instructions a task runs before yielding |
| `--fuel N` | 10000000 | Total instruction budget (`P421`) |
| `--max-depth N` | 100000 | Interpreter frames per activation (`P422`) |
| `--max-tasks N` | 4096 | Live activations (`P423`) |
| `--trace` | off | Include scheduler events |

`run-pure` JSON contains `status: EXECUTED`, `check: CHECKED`, `result`,
`execution` (mode, scheduler, limits), and `stats` (steps, activations, forks,
joins, peak live tasks, peak frames, pending tasks/joins). With `--trace` it also
contains `events`. Check rejections exit 1. Input errors, runtime faults, and
exhausted limits exit 2 with a `runtime` or `input` stage. `examples` also
accepts manifest cases of kind `pure`.

## Corpus and original tools

Manifest paths are relative to the manifest directory. `flow` cases use its net;
`net_append` cases are appended inside that net; `net` cases supply a full
alternative net. Expected failures match diagnostic codes, not full message text.
For append mutations, line numbers refer to the combined net.

Original tools, tests, reports, and certificates live in
`.agents/skills/weave/assets/prototype/`. Running its `demo.py` regenerates its
report/output files; ordinary kit checks do not. Additional CLI tests run with:

```bash
python3 -B -m unittest discover -s tests -q
```
