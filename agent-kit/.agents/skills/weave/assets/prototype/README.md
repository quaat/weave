# Weave Inventory: conservation, ordering, and linear composition

A dependency-free executable specification of a restricted language fragment.
It contains a net parser, structural ownership validator, integer P-invariant
checker, bounded single-order explorer, nominal linear flow checker, and a small
in-memory executor for scripted foreign outcomes.
There is no distributed runtime, payment adapter, or full language implementation.

**Start with `REPORT.md`.** It includes source and actual analyzer output,
including six protocol violations and a checkout that propagates `Unknown` with `?`.

## Reproduce

Requires Python 3.11 or newer; tested with CPython 3.12.14. No third-party
packages are needed; `requirements.txt` records that environment.

```bash
python3 demo.py
python3 -m unittest discover -s tests -v
```

`demo.py` checks valid callers and expected failures, then regenerates
`REPORT.md`, `ACTUAL_OUTPUT.txt`, `proof.json`, `ordering.json`, `scenarios.json`,
and `LOWERED_PROPAGATION.weave`.
An unexpected acceptance or diagnostic makes the demo exit nonzero.

Individual commands:

```bash
python3 checker.py analyze Inventory.weave --certificate proof.json
python3 checker.py order Inventory.weave
python3 checker.py check Inventory.weave examples/checkout_composed.weave
python3 checker.py check Inventory.weave examples/checkout_propagating.weave
python3 checker.py check Inventory.weave LOWERED_PROPAGATION.weave
python3 simulate.py Unknown
python3 checker.py prove Inventory.weave --certificate proof.json
python3 verify_certificate.py Inventory.weave proof.json
python3 checker.py check Inventory.weave examples/direct_charge.weave
```

The last command should exit 1: the direct charge lacks an escrow permit.
`analyze` completes structural validation, accounting, and ordering before printing
success labels. `check` runs those net checks before checking the given flows.
The deliberately narrower `prove` command reports only accounting equalities.

## What each result means

| Check | Result and scope |
| --- | --- |
| `stock_conservation` | `PROVED`: aggregate stock equality |
| `registration_balance` | `PROVED`: registration count equals the sum of payment-phase reservation counts |
| `sold_requires_paid` | `CHECKED WITHIN BOUNDS`: every sale has a paid-evidence guard in its history |
| `dispatched_release_requires_rejection` | `CHECKED WITHIN BOUNDS`: after dispatch, stock can return to available only with final rejection evidence |
| `paid_never_available` | `CHECKED WITHIN BOUNDS`: stock never returns to available after paid evidence |
| `paid_state_requires_paid` | `CHECKED WITHIN BOUNDS`: the intermediate paid state requires evidence too |
| `unpaid_state_requires_rejection` | `CHECKED WITHIN BOUNDS`: the intermediate unpaid state requires rejection evidence |
| Registration presence properties | `CHECKED WITHIN BOUNDS`: inflight, uncertain, recovery, and manual states retain a registration in the single-order model |
| Resource declarations | `CHECKED`: sealed issuers and consumers, atomic registration with escrow, cancellation routes, API/arc agreement |
| Runtime state declarations | `CHECKED`: every runtime-owned place has a closed consumer list |
| Flow declarations | `CHECKED`: nominal state types, identity indices, linear transfers across calls, returns and `?`, exhaustive outcomes, no normal drops |
| Reference execution | `SCRIPTED`: a concrete in-memory execution of one supplied outcome, not a proof |

`NOT ESTABLISHED` is used for absent models, exhausted search budgets, violated
model bounds, and explicitly unimplemented guarantees. A found counterexample
is reported as `VIOLATED` with a trace, rather than as uncertainty.
No label means that the Python implementation has been formally verified.

## Standard P-invariant accounting

For source-declared `wᵀ M = a*stock + b`, the checker verifies the symbolic initial
marking and `wᵀ C = 0`, where `C = Post - Pre` is derived from all transitions.
Induction then preserves the equality for arbitrary nonnegative stock and every
finite firing sequence. Guards are ignored for this accounting argument.

This is the textbook P-invariant method. The work here is source integration,
diagnostics, and composition with other checks, not a new proof technique.
Its unbounded stock parameter does not make it stronger than an ordering check:
the two methods establish different properties.

`registration_balance` replaces the misleading name `recovery_coverage`.
Equal aggregate counts cannot rule out a registration for A being used for B.
The arithmetic certificate rechecker shares the parser and affine-expression
reader. It checks arithmetic against source, not operational semantics or an
independent compiler implementation.

## Consumption sealing

An activation-owned place has one linear resource declaration. Only its declared
issuer can produce its token. A transition may consume it only when it is:

- The `via`/dispatch transition of an exported API with a matching resource parameter; or
- That resource's declared cancellation transition.

API parameters must account for all activation-owned inputs, with matching counts.
Read arcs over activation-owned places are rejected because borrowing is not
implemented. Cancellation must consume its resource without external guard/read
waits and leave outputs under durable ownership.

Every runtime-owned place, including registrations, requires a `runtime_state`
declaration with a consumer list (or `terminal` for no consumers). Listed
transitions must exist and consume exactly one token from that place. Omitting a
list does not open access. Runtime read arcs remain allowed.

All six supplied mutations fail declaration validation (`E101`). Explicitly
authorizing `quick_recover`, `leak`, or `manual_leak` still fails ordering (`E320`).
Adding the matching API and runtime authorization for `bogus_sell` is also unsafe: ordering
still finds a counterexample. Nor does sealing protect a declared cancellation
whose implementation returns paid stock to available; the explorer catches that.

The trusted module can change its public contract, guard classifications, and
properties. The checker checks those explicit declarations; it does not infer
business intent or treat edited assumptions as immutable security policy.

## Bounded one-order model

The model is declared in `Inventory.weave`. It fixes stock to one, permits
`reserve` at most once, and includes every place and transition. The initial
marking, takes, puts, and reads come from the net. Four extra bits record
admission, foreign dispatch, paid evidence, and final rejection evidence.

A guard classified `establishes_paid` or `establishes_rejected` sets its witness
on its own firing. The observed dispatch must match the foreign signature.
Other guards enable nondeterministically. Their false branches only stutter;
their true branches are all explored. Evidence never resets. Guards are abstract
contracts, not executed provider predicates. No assumption is made that paid and
rejected evidence are mutually exclusive, or that an adapter request must have
been dequeued before evidence can arrive.

The default source explores **20 states and 43 edges**, exercises all 21
transitions, and reaches the premise of each property. The place bound is one
and the search budget is 10,000 states. No depth cutoff is used. A successor
that exceeds a bound causes `NOT ESTABLISHED` and a nonzero exit; it is never
silently omitted. `--max-states` changes the search budget.

The one-admission restriction is explicit: re-reservation after release, other
orders, concurrent identities, and reuse of stock by another order are excluded.
This is an isolated order model, not a cutoff theorem for arbitrarily many
orders. Truthfulness, consistency, and identity correlation of evidence remain
assumptions. Independent contradictory/late provider replies are not modeled.
The witnesses can both become true if the source permits it; neither is erased.
Escalation budget correctness is also explicitly unestablished: an authorized
escalation without its budget guard passes these safety properties.
`ordering.json` is a source-bound result summary, not a verified proof certificate.

## Linear handles across flow calls

`examples/checkout_composed.weave` implements this checked path:

1. `checkout_composed` reserves a `Hold` and moves it into `pay_with`.
2. `pay_with` calls `arm_hold`, which returns an `Escrow` with the same indices.
3. Payment consumes the escrow and returns a linear closed `ChargeOutcome`.
4. The helper returns that enum to its caller, which moves it to `settle`.
5. `settle` sells, releases, or hands off the state-specific handle in every branch.

All helper signatures and bodies are checked, including unused helpers and
forward declarations. Calls unify symbolic identities; returns require the exact
declared type. A moved argument is unavailable to its caller. A return moves its
value and rejects any other live obligations. Enum payloads retain the same
linear discipline, including `Unknown`. No arbitrary sealed constructors exist.

Cancellation routing remains attached to the resource type across a call. The
checker validates the declared routes and their net behavior; it does not execute
a cancellation stack or prove the runtime transfer. The intended runtime must
serialize ownership transfer at calls, returns, suspension, and cancellation.

## `?` propagation and reference execution

`examples/checkout_propagating.weave` uses `?` in both `pay_with` and `place_order`.
Supported syntax is `let value = outcome?` or `let value = (await helper(...))?`.
The compiler lowers it to an exhaustive terminal match. `Ok` continues with its
payload; `Err` and `Unknown` immediately return the same tagged payload. Generated
nodes retain the source line and use fresh names. There is no implicit cleanup.

Every early-return path must account for all other linear bindings. In particular,
disposing of a second handle only after `?` is insufficient: the error and unknown
branches skip that code. The demo includes this rejection at the `?` source line.

The input outcome must have exactly `Ok`, `Err`, and `Unknown`. The enclosing
declared enum must support the same `Err` and `Unknown` payload types and indices.
Its success payload may differ: `CheckoutOutcome` declares `Ok(Unit)` because
`place_order` commits the sale before returning success. No open union or implicit
payload conversion is inferred. `return Ok(handle)` moves an existing payload;
`return Ok()` requires `Unit`. Foreign outcomes still require linear resources.

`simulate.py` executes the same lowered source against parsed net transitions,
using one scripted foreign reply. The `Unknown` trace has `uncertain=1` and
`registrations=1` at both helper returns, followed by `recovery_queue=1` and
`registrations=1` after the caller's explicit handoff. There is no intervening
net transition during propagation. The success and error scenarios commit sale
and rejection/release respectively. All three traces are in `scenarios.json`.

This synchronous interpreter has no persistence, provider I/O, asynchronous
cancellation, or worker failure. It supplies completion directly and does not
simulate an adapter delivery queue; `charge_requests` can remain in the marking.
It shares the lowering and parser with the checker and is not an independent
compiler refinement proof.

The fragment still excludes `within`, `retry`, ordinary conditionals, loops,
`parallel`, recursion, higher-order flows, scalar computations, open unions,
subtyping, and statements after a terminal match. The earlier full `place_order`
proposal is not supported. This revision tests one composition case; it does not
establish the broader ergonomics thesis.

## Regressions and remaining boundary

Tests include the six supplied additive mutations; corruption of an authorized
sell/cancel transition; omitted or moved evidence guards; token and state bound
exhaustion; preservation of read-arc enabling; caller reuse, helper leaks,
incorrect state/identity returns, dropped outcomes, and non-exhaustive helpers.
They also check rejection guard placement, missing/invalid runtime lists,
propagation's early-exit obligations, payload compatibility, all three reference
executions, and the original source/certificate and foreign-signature checks.

Still unestablished: multi-order identity preservation, truthful and consistent provider status,
idempotency retention, webhook authentication, persistence, crash recovery,
scheduling/fairness, liveness, escalation budgets, safe upgrades, and source-to-runtime refinement.
No Python source is evaluated from `.weave` files, and the demo sends no network
requests. Running the checker is not an OS or capability-security boundary.

## Files

| File | Purpose |
| --- | --- |
| `Inventory.weave` | Net, accounting invariants, ordering model, resources, APIs |
| `checker.py` | Parser, validator, arithmetic, exploration, and flow typing |
| `simulate.py` | Synchronous reference execution of one scripted foreign outcome |
| `verify_certificate.py` | Source-bound arithmetic recheck |
| `examples/checkout_composed.weave` | Linear helper parameters, returns, and outcomes |
| `examples/checkout_propagating.weave` | `?` across two helper boundaries and explicit caller handling |
| `LOWERED_PROPAGATION.weave` | Generated, separately checkable exhaustive-match lowering |
| `examples/checkout.weave` | Original direct caller |
| `examples/*.weave` | Original invalid callers |
| `mutations/*.weave` | Six additive protocol counterexamples |
| `tests/` | Regression tests |
| `demo.py` | Reproducible output and report generator |
| `REPORT.md`, `ACTUAL_OUTPUT.txt` | Actual results with explanations |
| `proof.json`, `ordering.json` | Accounting certificate and bounded-check summary |
| `scenarios.json` | Concrete marking snapshots for Ok, Err, and Unknown executions |
| `TEST_OUTPUT.txt` | Captured test output |
| `DESIGN_NOTES.md` | Separate, unimplemented runtime/language decisions |
