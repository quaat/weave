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
persistent result cache.

## Claims, tool status and runtime status

Every claim the runner makes carries exactly one of the six result labels of the
specification (`verification.rst`, Result vocabulary), verbatim: `PROVED`,
`CHECKED WITHIN BOUNDS`, `CHECKED flow`, `SCRIPTED / passed scenario`, `VIOLATED`,
`NOT ESTABLISHED`. A label belongs to one claim, never to a whole command. Nothing
else the runner reports is a claim, and it is never written with a label.

| What | JSON | Text |
| --- | --- | --- |
| A claim | an object with a `claim_label` member | an unindented line that begins with the label: `LABEL statement` |
| Tool or step status | `ok` (and the exit code); `examples` results carry `ok` per expectation | `tool status: PASS …`, `tool status: READY …` |
| Runtime status of a run | `runtime_status`: `waiting`, `timed out` or `completed` | `runtime status: completed` |
| Diagnostics | `diagnostic` | `file:line:column: CODE (RULE) [stage]` and indented lines |
| Raw output of another tool | `output`, `upstream_output` | indented under `raw output (…; not a claim):` |

No JSON member is named `status`, and no JSON value is another upper-case status word
such as `PASSED` (the teaching manifest's `ACCEPT` expectation is the one exception;
user-chosen names such as an upper-case property, invariant or flow name are not status words).

Text output is a closed set of line forms. An unindented line is a claim only if it
begins with one of the six labels exactly as written (not `proved`, `Checked flow` or
`CHECKED FLOW`). Every other unindented line is blank, a diagnostic header
(`file:line:column: CODE (RULE) [stage]`, or `file: TOOL_ERROR [stage]` with a file path
or nothing before it), the JSON detail of a failed `examples` expectation (a JSON object,
itself linted as JSON), or begins with one of these prefixes: `tool status: `,
`runtime status: `, `result: `, `stats: `, `prototype: `, `missing: `, `certificate: `,
`raw output (`, `error: ` (`NON_CLAIM_PREFIXES` in `weave_labels.py`). Indented lines
belong to the line above. The demos declare their own headings (`TEXT_PREFIXES` in each
`run_demo.py`), each non-empty and ending with `:`, `: ` or ` - `.
`tests/test_result_labels.py` fails on any other unindented line.

| Command | Claims (JSON position: label) |
| --- | --- |
| `check`, `analyze`, `lower`, `simulate`, `examples` | `accounting`: `PROVED` (the net's invariants); `ordering`: `CHECKED WITHIN BOUNDS` (one bounded exploration) |
| same, when the ordering check fails | `ordering`: `VIOLATED` with `E320` (a counterexample: `property`, `trace`, `marking`) or `NOT ESTABLISHED` with `E321` (`reason`: the specific cause, such as an exhausted or non-positive state budget, an initial marking above `place_bound` or `place_bound` exceeded, with its `trace` where the checker records one); both carry the model bounds (`orders`, `stock`, `admission_limit`, `place_bound`, `max_states`); `ok` is false and `diagnostic` holds the code |
| `check` | each accepted `files` element: `CHECKED flow` (every flow in that file) |
| `lower` | `files`: `CHECKED flow` for the source and for the lowered output (`lowered_from`) |
| `simulate` | each `runs` element: `SCRIPTED / passed scenario`, with `runtime_status: completed`; `outcome` (`Ok`, `Err`, `Unknown`) is the scripted application outcome |
| `verify` | `accounting`: `PROVED` with `method: certificate recheck` and its scope (shared parser; ordering not rechecked) |
| `check-pure` | each accepted `files` element: `NOT ESTABLISHED` (see below) |
| `run-pure` | `check`: `NOT ESTABLISHED`; the run itself is `runtime_status: completed` |
| `doctor`, `test` | none; `ok` is the tool status and `test` output is raw unittest output |

`examples` compares each teaching case with its expected outcome; those results are
step statuses (`ok`), not claims. An `Unknown` outcome is an application outcome:
a run that returns `Unknown` is still a `SCRIPTED / passed scenario` claim, and
`Unknown` is never `NOT ESTABLISHED`. Diagnostic messages repeat the prototype's
own wording (for example `NOT PROVED` in `E112`); a diagnostic is not a claim. Only explicit `--certificate` and `--output` write files.
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
accounting or ordering claim. `--net` and `--max-states` are not accepted.

Pure `fn` programs are outside F0 and every specified profile, so no specified
guarantee is established for them. Each accepted file is one `NOT ESTABLISHED`
claim (`reason`: missing model) whose statement names what the kit's own checker
accepted; `scope` describes those checks. The kit does not report the extension
check under a separate passing field: a successful check is a statement about the
program, and the six labels are the only vocabulary for such statements.

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

`run-pure` JSON contains `check` (the `NOT ESTABLISHED` claim, with `functions`),
`runtime_status: completed`, `result`, `execution` (mode, scheduler, limits), and
`stats` (steps, activations, forks, joins, peak live tasks, peak frames, pending
tasks/joins). With `--trace` it also contains `events`. Text output prints the
claim line, then `runtime status:`, `result:` and `stats:` lines. Check rejections exit 1. Input errors, runtime faults, and
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
