---
name: weave
description: Write, check, lower, simulate, and test .weave files using the bundled functional Petri-net prototype. Use for this restricted language, not unrelated products named Weave.
---

# Weave

Use Python 3.11+; CPython 3.12.14 is the reference. Install no packages.
Resolve paths below relative to this skill directory. Invoke `scripts/weave.py`
by absolute path when working elsewhere; supplied paths are relative to the current
working directory. The default net is `assets/prototype/Inventory.weave`.

## Choose the smallest useful operation

```bash
python3 scripts/weave.py doctor
python3 scripts/weave.py check /absolute/path/flow.weave
python3 scripts/weave.py check /absolute/path/a.weave /absolute/path/b.weave --net /absolute/path/Net.weave
python3 scripts/weave.py simulate /absolute/path/flow.weave --entry checkout_propagating --outcome all
python3 scripts/weave.py lower /absolute/path/flow.weave --output /absolute/path/lowered.weave
python3 scripts/weave.py analyze --certificate /absolute/path/proof.json
python3 scripts/weave.py verify /absolute/path/proof.json
python3 scripts/weave.py test --pattern test_rejection_and_propagation.py
python3 scripts/weave.py check-pure /absolute/path/program.weave
python3 scripts/weave.py run-pure /absolute/path/program.weave --entry merge_sort --args '[[3,1,2]]' --mode concurrent
```

`check-pure` and `run-pure` belong to the kit's pure-function extension
(`scripts/weave_pure/`): `fn`, `if`/`else`, `<=`, list primitives, direct
recursion, and `fork:`. They read no net and report no accounting claim; their
only claim is `NOT ESTABLISHED`, because pure programs are outside every specified profile.
Termination is not checked; concurrency is cooperative on one thread.

Replace paths and entry names with the task's actual files and declaration.
Use `--net PATH` for a changed net. Batch flows sharing a net to check that net
once. Put `--json` before the command for machine-readable output. Add `--trace`
to simulation only when snapshots are needed. Run `test` for all bundled
regressions after implementation changes. In the starter kit, run `examples`
for the teaching corpus; elsewhere pass `examples --manifest PATH`.

Read [the language guide](references/weave.md) for syntax or semantic work.
Use `assets/prototype/examples/checkout.weave`, `checkout_composed.weave`, and
`checkout_propagating.weave` for complete source patterns. Read implementation
files only when a diagnostic or implementation task requires them.

## Preserve meaning

- Check changed flows; use `lower` to check original and lowered source.
- Preserve nominal state types and identity indices. Move each linear handle
  exactly once on each path, including early returns at `?`.
- Treat `Unknown` as a recovery obligation. Propagation inserts no cleanup.
- Use implemented syntax; do not invent loops, retry, parallel, or unrestricted FFI.
  Pure `fn` syntax is valid only in pure files under `check-pure`/`run-pure`, never in flows.
- Separate `PROVED` accounting, `CHECKED WITHIN BOUNDS` ordering, `CHECKED flow`
  checks, and `SCRIPTED / passed scenario`
  execution. Report bounds/budget exhaustion as not established.
  Its label is `NOT ESTABLISHED`; a counterexample is `VIOLATED`. Use only these six
  labels for claims, one per claim: a claim is a JSON `claim_label` or an
  unindented text line that begins with its label.
  `ok`/`tool status` and `runtime_status` are not evidence; `Unknown` is an
  application outcome, never `NOT ESTABLISHED`.
- Preserve net contracts while repairing callers. Report incompatible requirements
  instead of weakening guards, consumer lists, or invariants to obtain a pass.
- Report diagnostic codes, rules, source locations, and messages. Exit 0 means the requested
  expectations were met; 1 is a rejection or failed test; 2 is usage, I/O,
  certificate-data, or scripted-execution failure. Expected-invalid fixtures make
  `examples` succeed only when their particular diagnostic codes match.

Run no real external operations. The executor is synchronous, stock-one,
scalar-entry, and limited to at most one scripted foreign operation. Do not claim
persistence, distributed recovery, or multi-order correctness from its traces.
