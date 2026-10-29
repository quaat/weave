# Tiny Shop: buy the last item

A small terminal demo of purchasing the last item in stock, written as executable
Weave flows in [`shop.weave`](shop.weave) and run by this kit's existing runner
(`scripts/weave.py`) against the bundled, unchanged `Inventory.weave` net.

Every invocation is a fresh, independent stock-one simulation. You choose the
scripted `Payments.charge` outcome; the demo shows the NET transitions the runner
actually executed and the final marking. `tenant`, `order`, and `amount` are
opaque symbolic simulator inputs: the demo takes no customer identity, computes
no amount, and charges nothing.

## Prerequisites

- Python 3.11 or newer (the kit's tested reference is CPython 3.12.14; this demo
  was run with Python 3.13.5).
- No third-party packages, services, or credentials (see `requirements.txt`).

## Run it

From the kit root (the script also works by absolute path from any directory):

```bash
python3 demos/tiny_shop/run_demo.py                      # same as --outcome all
python3 demos/tiny_shop/run_demo.py --outcome Ok --trace
python3 demos/tiny_shop/run_demo.py --outcome Err --trace
python3 demos/tiny_shop/run_demo.py --outcome Unknown --trace
python3 demos/tiny_shop/run_demo.py --outcome all --json
python3 demos/tiny_shop/run_demo.py --help
```

`--trace` adds the recorded marking after every event. `--json` prints exactly one
JSON document on stdout. `--source PATH` runs another flow file with a `checkout`
entry (used by the tests to show failures). Unsupported options or outcomes exit
with code 2. If the runner rejects the flow or fails, the demo prints the
diagnostic (code, stage, file, line, message) and exits nonzero (1 for a Weave
rejection, the runner's own code otherwise); it never shows scenarios for a failed
check.

Tests and checks:

```bash
python3 -B -m unittest discover -s demos/tiny_shop/tests -v
python3 scripts/weave.py check demos/tiny_shop/shop.weave
python3 scripts/weave.py lower demos/tiny_shop/shop.weave --output demos/tiny_shop/artifacts/shop.lowered.weave
python3 scripts/weave.py --json simulate demos/tiny_shop/shop.weave --entry checkout --outcome all --trace
python3 scripts/weave.py analyze --certificate demos/tiny_shop/artifacts/inventory-proof.json
python3 scripts/weave.py verify demos/tiny_shop/artifacts/inventory-proof.json
```

## Workflow

All reservation, outcome branching, and settlement live in `shop.weave`:

| Flow | Does |
| --- | --- |
| `checkout(tenant, order, amount)` | Scalar entry. Calls `buy_last_item` and handles every `CheckoutOutcome` case explicitly: `Ok()` returns, `Err(unpaid)` → `Inventory.release`, `Unknown(uncertain)` → `Inventory.handoff`. |
| `buy_last_item(...) -> CheckoutOutcome` | `Inventory.reserve` → `arm_reservation` → `(charge_payment(...))?` → `Inventory.sell` → `Ok()`. |
| `arm_reservation(hold) -> Escrow` | `Inventory.arm`: moves the hold into escrow and creates the recovery registration. |
| `charge_payment(..., escrow) -> ChargeOutcome` | `(Payments.charge(..., escrow))?` then `Ok(paid)`; the scripted foreign call consumes the escrow permit. |

`?` is used twice, so `Err`/`Unknown` propagate across two helper boundaries
(`charge_payment` → `buy_last_item` → `checkout`). This follows the accepted
`examples/valid/checkout_propagating.weave` pattern.

### `ChargeOutcome` vs `CheckoutOutcome`

Both are closed linear enums declared in `Inventory.weave`:

| | `ChargeOutcome[t, o]` | `CheckoutOutcome[t, o]` |
| --- | --- | --- |
| `Ok` | `Ok(Paid[t, o])` – payment evidence that still holds the registration and **must** be consumed (by `Inventory.sell`) | `Ok(Unit)` – the sale is already committed; nothing is owed |
| `Err` | `Err(Unpaid[t, o])` | same `Unpaid[t, o]` payload |
| `Unknown` | `Unknown(Uncertain[t, o])` | same `Uncertain[t, o]` payload |

`?` on a `ChargeOutcome` inside a flow returning `CheckoutOutcome` is accepted
because the residual `Err` and `Unknown` payload types and identity indices are
identical; only the success type differs. Propagation inserts no cleanup: the
`Unpaid` and `Uncertain` obligations arrive at `checkout` unchanged, and
`checkout` must discharge them itself. `Unknown` is neither success nor
rejection, so the item is neither sold nor released; it is handed to the recovery
queue with its registration intact.

## Expected (and observed) outcomes

| Scripted outcome | Result | NET transitions | available | sold | recovery_queue | registrations |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `Ok` | Purchase completed | reserve, arm, dispatch, charge_ok, sell | 0 | 1 | 0 | 0 |
| `Err` | Payment rejected; item released | reserve, arm, dispatch, charge_err, release | 1 | 0 | 0 | 0 |
| `Unknown` | Payment unresolved; item held for recovery | reserve, arm, dispatch, charge_unknown, handoff | 0 | 0 | 1 | 1 |

In all three, `held`, `escrow`, `inflight`, `paid`, `unpaid`, `uncertain`, and
`manual` end at 0. `charge_requests` ends at 1 because `dispatch` enqueues an
adapter request and the prototype simulator never drains the adapter queue
(`adapter_dequeue` is not fired). This is expected prototype behavior, not a leak
in the flow. The `Unknown` scenario stops at `handoff`; recovery (`recover_paid`,
`recover_rejected`, `escalate`) is not run.

The result label is chosen from the settlement transition the runner actually
executed (`sell`/`release`/`handoff`); Python does not re-implement the workflow.

## What the results mean

- **PROVED** – the two Inventory accounting invariants (`stock_conservation`,
  `registration_balance`) hold for every finite firing sequence under the parsed
  net semantics. Aggregate counts only, not per-order registration matching.
- **CHECKED WITHIN BOUNDS** – the net's one-order safety model: 20 states / 43
  edges with orders=1, stock=1, admission ≤ 1, tokens/place ≤ 1, abstract and
  assumed-truthful payment/rejection evidence, no late replies, no liveness.
- **CHECKED flow** – `shop.weave` (and its lowered form) satisfies the supported type,
  identity-index, exhaustive-match, and linear-ownership rules.
- **SCRIPTED / passed scenario** – each scenario is one synchronous run with a chosen
  payment outcome. It is not a multi-order or multi-interleaving proof. Its
  `runtime status: completed` says the run finished; it is not evidence, and the
  `Unknown` payment outcome is an application outcome, not `NOT ESTABLISHED`.

The demo prints each claim as a `LABEL statement` line with the runner's label, and
`--json` relays the runner's `claim_label` and `runtime_status` fields unchanged.

`verify` rechecks the certificate's source-bound accounting only; it does not
recheck ordering and is not a proof of this application.

## Prototype limits

No persistent inventory, real payment I/O, asynchronous or durable recovery
service, adapter delivery, crash handling, or established multi-order
correctness. A `recovery_queue` token here is a simulator count, not a running
recovery worker. The runner does not link helpers across files, so all mutually
calling flows live in `shop.weave`. Weave conditionals, loops, retries, parallel
flows, recursion, scalar computation, and post-match statements are unsupported
and are not used.

## Files

- `shop.weave` – hand-written flows.
- `run_demo.py` – thin standard-library CLI over `scripts/weave.py`.
- `tests/test_tiny_shop.py` – integration and rejection tests.
- `artifacts/` – generated: `shop.lowered.weave`, `source-trace.json`,
  `lowered-trace.json`, `scenarios.json`, `inventory-proof.json`.
- `TEST_REPORT.md` – commands run and observed results.
