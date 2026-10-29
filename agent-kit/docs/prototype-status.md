# Prototype status and provenance

Snapshot date: 2026-10-28. Source: `weave-inventory-proof.zip`, version 3.
The files are kept under `.agents/skills/weave/assets/prototype/`, byte-identical
to the specification's reference snapshot. They are the original bytes except for
the reviewed snapshot refresh of 2026-10-29 (quaat/weave#6), which replaced
`checker.py`, `coloured.py`, `durable.py`, `README.md` and three test files.
`PROVENANCE.json` records source identity, the current per-file hashes and the
refresh (`prototype_history`). The runner calls the existing Python API without
changing language rules.

## Implemented

- Restricted net/flow parsing and ownership validation, including sealed
  activation resources and closed runtime consumer lists.
- Source-bound integer P-invariant accounting and arithmetic certificate rechecking.
- Bounded one-order exploration with paid and final-rejection evidence witnesses.
- Nominal linear handles, indexed helper calls/returns, closed enums, exhaustive
  terminal matches, and `?` lowering.
- Synchronous reference execution with stock one, scalar entry parameters, and
  at most one scripted foreign operation; no external service is contacted.

This snapshot has **143 regression tests**. Earlier descriptions with fewer tests
or `?` listed as unimplemented refer to an older snapshot.

### Changes from version 2

- `E204` raised on a `?` early-return branch now names the `?` line and the
  handles still held, instead of the generic "obligations left at normal
  return" message. The code and the accepted/rejected programs are unchanged.
- The accounting report's `NOT ESTABLISHED` line now names `orders>=2` and
  cross-order token matching as outside the uncoloured model.
- New bundled modules, not wired into `scripts/weave.py`:
  `coloured.py` (tenant/order-indexed coloured nets over
  `Inventory.coloured.weave`, with per-family invariants and two-order
  exploration) and `durable.py` (the R0 process-crash reference driver and
  `durable-scenarios.json`). Run them directly from
  `.agents/skills/weave/assets/prototype/`, for example
  `python3 coloured.py analyze Inventory.coloured.weave` or `python3 durable.py`.
  The runner's `check`, `simulate`, and `verify` still use the uncoloured N0
  net, so the boundaries below describe the runner.

### Snapshot refresh for quaat/weave#6 (2026-10-29)

- Every `CheckError` carries a primary source span (1-based line and column; the
  end column is one past the last character). `E203` and `E204` also carry
  related spans: where each held or reused handle was bound, where it was
  consumed, and the `?` that propagates. `CheckError.diagnostic()` writes the
  error as a `weave-diagnostic-v1` document.
- Errors that had no line now take the line of the enclosing statement or net
  header, and errors found in a coloured net's erased projection report the
  coloured source line. A diagnostic about a whole source keeps line 0.
- The accepted and rejected programs, the codes and the generated outputs of
  `demo.py` are unchanged; the 143 tests now also assert spans.

### The prototype's own console lines are raw tool output

The vendored prototype prints its own status words: `checker.py` prints bare
`CHECKED …` lines (linear resources, runtime-owned places, foreign dispatch, a flow)
and `NOT PROVED` inside `E112`; `coloured.py` prints `NOT PROVED` inside `E412`;
`durable.py` prints `PASSED` and records `status: PASSED`; `verify_certificate.py`
prints `RECHECKED`; `demo.py` prints `CHECKED <flow>:`, `PASSED`, `RECHECKED` and
`EXPECTED … FAILURE`. These bytes are pinned and stay unchanged (quaat/weave#8).
They are raw tool output, not claims. The kit runner states claims itself, with
the six result labels only (`docs/commands.md`, "Claims, tool status and runtime
status"): for example `verify` reports `PROVED` where `verify_certificate.py`
prints `RECHECKED`. Raw output reaches the runner's output only as `test` output,
`upstream_output` or diagnostic messages, none of which is a claim. The evidence
envelopes in `evidence/` likewise wrap the prototype's files under the six labels.

## Kit extension: pure functions with fork/join

The kit adds a separate module, `.agents/skills/weave/scripts/weave_pure/`, that
implements pure `fn` declarations over `Int`, `Bool`, immutable `IntList`, and
`IntListPair`. It adds `<=`, terminal `if`/`else`, a closed set of list
primitives, direct self-recursion, and a two-branch `fork:`/join. It also provides
an instruction-level interpreter with a bounded cooperative scheduler, exposed
through the runner's `check-pure` and `run-pure` commands. The extension does
not modify the vendored prototype. Its diagnostics use the `P4xx` codes and the
kit rule IDs listed in the guide. Flows still reject recursion (`E218`) and `fn`
(`E200`). See the [language guide](weave.md#pure-function-extension-kit-addition).

| Area | Boundary |
| --- | --- |
| Termination | Not checked statically; fuel/depth/task limits are resource limits |
| Concurrency | Cooperative interleaving on one OS thread; no CPU parallelism |
| Scheduler properties | Pairing, single join consumption, cleanup, failure propagation, and mode agreement are tested, not proved |
| Scope | Pure data only; no effects, linear handles, net interaction, mutual recursion, higher-order functions, loops, or arithmetic beyond `<=` |
| Accounting | No net or certificate covers this task system |
| Result labels | Outside every specified profile: the runner's only claim about a pure program is `NOT ESTABLISHED`; a run's `runtime_status` is not evidence |

## Boundaries

| Area | Boundary |
| --- | --- |
| Accounting | Aggregate counts, not per-order registration matching |
| Ordering | One order, one item, one admission, explicit place/search bounds |
| Guards | Abstract witnesses; provider truth and correlation assumed |
| Flow checking | Static transfer/type discipline, not proof every call can fire |
| Cancellation | Route validation, not a durable scheduler or cancellation stack |
| Simulation | Chosen outcomes; no persistence, worker crashes, provider I/O, or adapter delivery model |
| Certificate recheck | Shared parser/expression reader, not an independent proof assistant |
| Implementation | Python and compiler/runtime refinement are not formally verified |

Unsupported in flows: `within`, `retry`, ordinary conditionals, loops, parallel
flows, recursion, higher-order flows, scalar computations, open unions,
subtyping, borrowing, and post-match statements. (Pure `fn` code supports only
the constructs listed above.)

Unestablished: multi-order identity preservation, idempotency retention, webhook
authentication, crash recovery, liveness/fairness, escalation budgets, safe
upgrades, and runtime refinement. The original `DESIGN_NOTES.md` discusses future
decisions; interpret it alongside this boundary and executable tests.

## Updates

Select an explicit prototype revision, replace the complete snapshot, update
provenance, and run original tests, teaching expectations, and CLI tests. Update
the guide and skill when syntax or behavior changes. Investigate changed expected
diagnostics before accepting them. Do not describe proposed features as implemented.

The kit and the vendored prototype are released under the MIT License; see
[`LICENSE`](../../LICENSE) at the repository root.
