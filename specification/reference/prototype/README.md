# Weave Inventory: coloured checking and crash recovery

A dependency-free executable language fragment: nominal linear flows with `?`,
explicit coloured Petri nets, invariant families, bounded ordering analysis, and
a SQLite process-crash model. Start with **`REPORT.md`**, which contains the source,
actual output, counterexamples, bounds, and assumptions.

The current protocol is **`Inventory.coloured.weave`**. The earlier uncoloured
`Inventory.weave`, checker, and synchronous executor remain regression fixtures.
Their output explicitly states the one-order modelling limitation.

## Run

Requires Python 3.11 or newer; tested with CPython 3.12.14. No third-party packages.

```bash
python3 demo.py
python3 -m unittest discover -s tests -v
python3 coloured.py analyze Inventory.coloured.weave
python3 coloured.py check Inventory.coloured.weave examples/checkout_propagating.weave
python3 durable.py
```

To retain the domain/provider SQLite databases for inspection:

```bash
python3 durable.py --directory ./crash-run
```

Use a fresh directory; earlier evidence is not overwritten. The default uses
and removes a temporary directory. The model contacts no external services.

`demo.py` regenerates `REPORT.md`, `ACTUAL_OUTPUT.txt`, the coloured proof/check
JSON, durable scenario histories, and the earlier proof/lowering artifacts.
Unexpected acceptance or a failed scenario assertion causes a nonzero exit.

## What the labels establish

| Result | Exact scope |
| --- | --- |
| `PROVED` aggregate stock and pool credits | Standard P-invariant accounting |
| `PROVED` registration, identity, and job families | Accounting for every colour and variable binding in the supported inscription fragment |
| `CHECKED WITHIN BOUNDS` | Ordering, token correlation, and unique reservation at two orders, one SKU, two stock units, one unit per order |
| `CHECKED` flows | Nominal state types, symbolic identity indices, linear moves/returns/propagation, exhaustive outcomes |
| `PASSED` crash case | A concrete injected process death, persisted-state recovery, and asserted postconditions |
| `NOT ESTABLISHED` | Explicit model bounds and remaining unverified properties |

The coloured exploration exhausts **841 states and 3,712 edges** and reaches all
24 transitions. Indexed places have at most one token per colour; shared stock
and pool credits have capacity two. The state budget is 100,000. Exceeding a bound
fails with `NOT ESTABLISHED`; no successor is silently dropped to obtain success.
The generic parser can describe larger bounds, but this delivery validates two
orders and makes no arbitrary-order cutoff claim.

## Colour is retained in the analysis

Places and arcs use explicit `[tenant, order]` indices. `available` remains a
shared stock pool; release also produces the order's own `released` token.
Each transition declares its firing colour. The bounded checker compares every
indexed input/read/output with that colour, and evidence/dispatch history is
maintained separately for each order.

An invariant family is checked by grouping the exact take/put coefficients by
symbolic colour tuple. Zero residual for every tuple preserves the equality for
all valuations, independently of the finite exploration. `colour-proof.json`
also includes the actual two-colour unfolding: 32 place rows and 48 firing modes.
This is the standard P-invariant method applied to coloured inscriptions, not a
new proof technique or a proof-assistant certificate.

Changing `sell` to take `paid[t,o]` and `registrations[t,other]` preserves aggregate
counts but fails the registration family (`E412`). The explorer additionally
reports an enabled cross-order theft (`E420`), naming the firing and registration
identities. Cross-order read arcs, which do not affect incidence arithmetic,
are caught by the correlation property.

`reserve` consumes a single-use `identities[t,o]` token. A second raw reservation
for the same identity is disabled; durable duplicate admission resumes the same
job. Type indices alone still do not establish freshness, and the flow checker
does not statically reject every duplicate reserve or prove it deadlock-free.
The identity and job invariant families check the underlying protocol accounting.

All activation resources retain sealed issuer/consumer rules. All runtime places
have closed consumer lists. API and foreign-outcome signatures must agree with
their transition arcs. The module's declarations are trusted input: changing its
properties or evidence interpretation changes the specification being checked.

## `?` and diagnostics

`examples/checkout_propagating.weave` uses `?` across helpers. It lowers to an
exhaustive match: `Ok` continues; `Err` and `Unknown` return their existing linear
payloads. Residual payload types and identity indices must agree exactly with
the enclosing declared enum. Other live handles cannot vanish on early exits.
There are no inferred open unions or implicit cancellation/release operations.

Generated propagation returns retain their origin. An outstanding handle now
produces a diagnostic of the form:

```text
example.weave:4: E204
  '?' on line 4 may propagate Err/Unknown while these linear handles are still held: hold2: Paid[u, v].
  Consume them before '?', or handle the outcome explicitly and return the obligations.
```

Every `CheckError` also carries source locations (quaat/weave#6). Its `span` is
the statement the error is reported at: 1-based line and column, ending one
column past the last character, without indentation or comment. E203 and E204
also have `related` spans: where each live or reused handle was bound
(`binding`), where a moved handle was consumed (`moved`), and the `?` that
propagates (`propagation`). `error.diagnostic(file, source, stage, rule, ...)`
returns the error as a `weave-diagnostic-v1` document (schema in
`evidence/schemas/` of the repository); the caller supplies the rule from the
code-to-rule map `specification/diagnostics.json`. An error with no single line
keeps `line` 0, and its span covers the whole source. A coloured net's errors
found in its erased projection are reported at the coloured source line.

`LOWERED_PROPAGATION.weave` is the separately checkable expansion. The flow fragment
still excludes general expressions, ordinary conditionals, loops, `parallel`,
recursion, higher-order flows, `within`, and `retry`. The broader ergonomics claim
is not established by this small implementation.

## Durable process-crash model

`durable.py` executes the parsed coloured inscriptions through `Unfolding.fire`.
It checks enabledness, identity, the relevant ledger evidence, and invariant
accounting. Marking changes and operation/result records commit together in a
SQLite domain database. A separate SQLite provider database implements the
scripted keyed payment contract. Both use WAL and `synchronous=FULL`.

The six acceptance cases terminate a subprocess with `os._exit(91)` after:

1. Admission commit, before source acknowledgment.
2. Result/completion/credit commit, before worker acknowledgment.
3. Provider success commit, before the response is recorded.
4. Payment-evidence commit, before cancellation completes the sale.
5. Cancellation and its Unknown completion, before late evidence is delivered.
6. Inconclusive-evidence commit, before recovery retries and escalation.

Each case reopens the databases and preserves a second unresolved order's own
registration. The adapter fires `adapter_dequeue`; neither order has a leftover
request token at the end. A result token, result row, job completion, and pool
credit return commit atomically. A later resolution updates an Unknown result's
status under the same identity; it does not issue another credit/completion.

The suite also exercises uncommitted transaction rollback, the dequeue/send gap,
keyed resend after a lost reply, duplicate results/receipts, wrong-order receipts,
worker-generation fencing, immutable final evidence, and late resolution of
manual recovery. The simulator enforces a two-attempt reconciliation budget;
that policy is not a general temporal proof in the net analyser.

These are process-crash tests on one machine, not verification of SQLite,
physical power-loss durability, real providers, network authentication,
distributed consensus, or every crash schedule. Source revision changes require
an explicit migration; automatic migration is not implemented. The driver
executes protocol operations and does not prove compilation correctness for all
flow programs.

## Files

| File | Purpose |
| --- | --- |
| `Inventory.coloured.weave` | Current coloured protocol, identities, worker credits, invariant families |
| `coloured.py` | Colour parser, family proofs, finite unfolding, two-order exploration |
| `checker.py` | Shared syntax/structural validation and linear flow checking |
| `durable.py` | File-backed domain/provider model and subprocess crash cases |
| `demo.py` | Reproducible combined demonstration |
| `REPORT.md`, `ACTUAL_OUTPUT.txt` | Generated source and actual results |
| `colour-proof.json`, `colour-check.json` | Symbolic families, coloured incidence matrix, bounded results |
| `durable-scenarios.json` | Crash checkpoints, event histories, markings, ledger/result/provider rows |
| `examples/checkout_propagating.weave`, `LOWERED_PROPAGATION.weave` | Source flow and actual lowering |
| `Inventory.weave`, `simulate.py`, `proof.json`, `ordering.json`, `scenarios.json` | Earlier single-order regression model and artifacts |
| `verify_certificate.py` | Legacy uncoloured arithmetic recheck only |
| `tests/`, `TEST_OUTPUT.txt` | Regression tests and captured results |
| `DESIGN_NOTES.md` | Earlier proposed mechanisms; see this README for implemented scope |

The coloured witness is generated by the same checker; there is no independent
formal verifier for it. The legacy certificate rechecker shares its parser.
General liveness, arbitrary-order ordering, real evidence truthfulness, upgrades,
and compiler-to-runtime refinement remain explicitly unestablished.
