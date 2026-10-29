# Tiny Shop test report

Date: 2026-10-28. Interpreter: Python 3.13.5 (`doctor`: READY, no third-party
dependencies). The kit is not a Git repository, so there was no `git status` to
preserve. All commands below were run from the kit root unless noted. Default
bundled `Inventory.weave` net (byte-identical to `examples/nets/Inventory.weave`);
no `--net` override was used, and the vendored prototype was not modified.

Note (kit 0.3.0, quaat/weave#8): the outputs quoted below are those of the kit at the
time of this report. The runner and demos now print each claim as a `LABEL statement`
line with one of the six result labels and report tool and runtime status separately
(`docs/commands.md`); the files in `artifacts/` were regenerated with the current output.

## Baseline (before any changes)

| Command | Exit | Result |
| --- | ---: | --- |
| `python3 scripts/weave.py doctor` | 0 | READY Python 3.13.5 |
| `python3 scripts/weave.py examples` | 0 | PASS 28/28 example expectations |
| `python3 scripts/weave.py test` | 0 | Ran 107 tests, OK |
| `python3 -B -m unittest discover -s tests -q` | 0 | Ran 14 tests, OK |

No pre-existing failures.

## Check, lower, simulate, certify

| Command | Exit | Result |
| --- | ---: | --- |
| `python3 scripts/weave.py check demos/tiny_shop/shop.weave` | 0 | PROVED 2 accounting invariants; CHECKED WITHIN BOUNDS 20 states/43 edges (orders=1, stock=1, admission<=1, tokens/place<=1); CHECKED checkout, buy_last_item, arm_reservation, charge_payment |
| `python3 scripts/weave.py lower demos/tiny_shop/shop.weave --output demos/tiny_shop/artifacts/shop.lowered.weave` | 0 | CHECKED LOWERING (both `?` sites became terminal matches) |
| `python3 scripts/weave.py --json simulate demos/tiny_shop/shop.weave --entry checkout --outcome all --trace` | 0 | `status: SCRIPTED`; saved as `artifacts/source-trace.json` |
| `python3 scripts/weave.py --json simulate demos/tiny_shop/artifacts/shop.lowered.weave --entry checkout --outcome all --trace` | 0 | `status: SCRIPTED`; saved as `artifacts/lowered-trace.json` |
| `python3 scripts/weave.py analyze --certificate demos/tiny_shop/artifacts/inventory-proof.json` | 0 | PROVED 2 invariants; CHECKED WITHIN BOUNDS 20/43; certificate written |
| `python3 scripts/weave.py verify demos/tiny_shop/artifacts/inventory-proof.json` | 0 | RECHECKED 2 accounting invariants; ordering not rechecked |

### Source vs lowered (per outcome)

Compared final marking, `(return_type, return_tag)`, and ordered NET transition names:

| Outcome | Marking equal | Return equal | NET sequence equal |
| --- | --- | --- | --- |
| Ok | yes | yes | yes |
| Err | yes | yes | yes |
| Unknown | yes | yes | yes |

## Application runs

| Command | Exit |
| --- | ---: |
| `python3 demos/tiny_shop/run_demo.py --outcome all` | 0 |
| `python3 demos/tiny_shop/run_demo.py --outcome Ok --trace` | 0 |
| `python3 demos/tiny_shop/run_demo.py --outcome Err --trace` | 0 |
| `python3 demos/tiny_shop/run_demo.py --outcome Unknown --trace` | 0 |
| `python3 demos/tiny_shop/run_demo.py --outcome all --json` → `artifacts/scenarios.json` (valid JSON) | 0 |
| `python3 <abs path>/run_demo.py --outcome Err` from `/tmp` | 0 |
| `python3 demos/tiny_shop/run_demo.py --help` | 0 |
| `python3 demos/tiny_shop/run_demo.py --outcome Maybe --json` | 2 (argparse usage error on stderr, empty stdout) |
| `python3 demos/tiny_shop/run_demo.py --nope` | 2 |
| `run_demo.py --source <temp copy of examples/invalid/missing_unknown.weave>` (manual check) | 1, `FAILED E214 [flow] …:3: Non-exhaustive or invalid ChargeOutcome match. Missing ['Unknown']` |

### Observed scenario results (`artifacts/scenarios.json`)

| Outcome | Settlement | NET transitions | available | sold | recovery_queue | registrations | charge_requests |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Ok | Purchase completed | reserve, arm, dispatch, charge_ok, sell | 0 | 1 | 0 | 0 | 1 |
| Err | Payment rejected; item released | reserve, arm, dispatch, charge_err, release | 1 | 0 | 0 | 0 | 1 |
| Unknown | Payment unresolved; item held for recovery | reserve, arm, dispatch, charge_unknown, handoff | 0 | 0 | 1 | 1 | 1 |

`held`, `escrow`, `inflight`, `paid`, `unpaid`, `uncertain`, `manual` = 0 in all
three. `charge_requests=1` remains because the simulator does not drain the
adapter queue. In the Err and Unknown traces, `RETURN charge_payment[<tag>]` and
`RETURN buy_last_item[<tag>]` events show `?` propagation across both helpers.

## Tests

| Command | Exit | Result |
| --- | ---: | --- |
| `python3 -B -m unittest discover -s demos/tiny_shop/tests -v` | 0 | Ran 17 tests, OK |
| `python3 scripts/weave.py examples` | 0 | PASS 28/28 example expectations |
| `python3 scripts/weave.py test` | 0 | Ran 107 tests, OK |
| `python3 -B -m unittest discover -s tests -q` | 0 | Ran 14 tests, OK |

The 17 demo tests cover: check + lowering (and recheck of the lowered file);
expected final markings for all three outcomes; exact NET sequences; nonnegative
counts and both accounting equations at every recorded marking; Unknown neither
sells nor releases and keeps its registration, Err never sells, Ok never
releases; `?` return tags at both helper boundaries; source/lowered agreement;
app JSON content, single-outcome trace text, default `all`, invalid CLI input
(exit ≠ 0), running from another directory, and surfacing a runner rejection
(E208) and a missing source file; temporary invalid variants of `shop.weave`
rejected with `E214` (Unknown arm removed), `E203` (moved hold reused), `E208`
(Paid passed to `Inventory.release`); and the matching teaching fixtures
(`missing_unknown`, `reuse_hold`, `paid_release`) still report those codes.
Fixtures were only read, never modified.

## Scope of the evidence and remaining limits

- **PROVED**: aggregate token accounting (2 invariants) under the parsed net semantics.
- **CHECKED WITHIN BOUNDS**: the one-order safety model (20 states, 43 edges;
  orders=1, stock=1, admission ≤ 1, tokens/place ≤ 1; evidence witnesses assumed
  truthful and correlated; no late replies; no liveness/fairness).
- **CHECKED**: `shop.weave` and its lowered form under the supported type and
  linear-ownership rules.
- **SCRIPTED**: three single-order synchronous runs with chosen outcomes.

Certificate verification rechecks accounting only, not ordering and not the
application. There is no persistent inventory, real payment I/O, asynchronous or
durable recovery, adapter queue draining, or established multi-order
correctness. The Unknown scenario ends at `handoff`; recovery is not executed.
