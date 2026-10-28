# Claude Code task: Tiny Shop in Weave

You are working in a project folder with `weave-agent-kit` already installed. Initialize your understanding of this project, implement the demo below, run it, and test it. Complete the work rather than stopping after a plan or code generation. Make routine implementation decisions yourself; ask only if a missing prerequisite or genuine ambiguity blocks progress.

## 1. Initialize from the existing project

1. Confirm the working directory and inspect the project structure. Check `git status --short` if this is a Git repository; preserve existing user changes.
2. Read the applicable `CLAUDE.md` and `AGENTS.md`, including imported instructions. Initialization means learning and using this project's existing configuration. Do not overwrite these files or replace them with a generic initialization template.
3. Use the local `weave` skill. In the standard kit, read `.claude/skills/weave/SKILL.md`, then the canonical `.agents/skills/weave/SKILL.md`. If the canonical skill was installed directly under `.claude/skills/weave/`, use that complete installation instead.
4. Read `docs/weave.md`, `docs/commands.md`, `docs/prototype-status.md`, and the relevant examples: `examples/valid/checkout_composed.weave`, `examples/valid/checkout_propagating.weave`, and `examples/nets/Inventory.weave`. For a standalone skill installation, use its bundled guide and prototype examples. Read implementation source only when a diagnostic requires it.
5. Locate the existing runner. The commands below assume the standard kit root and `scripts/weave.py`; adapt paths to the actual installation. Do not invent a new Weave toolchain or install an unrelated package named Weave.
6. Confirm Python 3.11 or newer. The kit records CPython 3.12.14 as its tested reference. Run these baseline checks where available, and record any pre-existing failures:

```bash
python3 scripts/weave.py doctor
python3 scripts/weave.py examples
python3 scripts/weave.py test
python3 -B -m unittest discover -s tests -q
```

The standard kit needs no third-party packages or external services. If only the portable skill is installed, use its runner and available regressions; report unavailable kit-only checks accurately.

## 2. Build the demo: Tiny Shop — buy the last item

Implement a small terminal application that demonstrates purchasing the last item in stock. Every invocation starts a fresh, independent stock-one simulation. Users select a scripted payment outcome and see the executed transitions and final state.

The workflow must live in executable `.weave` source:

- Reserve the item through `Inventory.reserve`.
- Arm the reservation through `Inventory.arm`, creating its recovery registration.
- Call the scripted `Payments.charge` operation with the resulting escrow permit.
- On `Ok`, consume `Paid` through `Inventory.sell`.
- On `Err`, consume `Unpaid` through `Inventory.release`.
- On `Unknown`, consume `Uncertain` through `Inventory.handoff`, leaving the item in the recovery queue with its registration intact.

Use the bundled Inventory net unchanged. This is an application of the current language fragment, not a language or runtime extension.

Use small helper flows and demonstrate `?` propagation across a helper boundary. Have a scalar-entry flow named `checkout(tenant: TenantId, order: OrderId, amount: Money)` handle the final outcome explicitly. Keep mutually calling flows in the same file: the runner does not link helpers across flow files. Follow the accepted propagation example and explain the important differences between `ChargeOutcome` and `CheckoutOutcome` in comments or the README.

Treat `tenant`, `order`, and `amount` as symbolic simulator inputs. Do not imply that the application accepts real customer identities or computes or charges a monetary amount.

Expected final state:

| Scripted outcome | User-facing result | available | sold | recovery_queue | registrations |
| --- | --- | ---: | ---: | ---: | ---: |
| `Ok` | Purchase completed | 0 | 1 | 0 | 0 |
| `Err` | Payment rejected; item released | 1 | 0 | 0 | 0 |
| `Unknown` | Payment unresolved; item held for recovery | 0 | 0 | 1 | 1 |

For all three, `held`, `escrow`, `inflight`, `paid`, `unpaid`, `uncertain`, and `manual` must finish at zero. The prototype leaves `charge_requests=1` because it does not drain the adapter queue; preserve and explain that behavior. The Unknown scenario stops at handoff: it does not complete recovery.

## 3. Deliver a usable terminal application

Create these files, adapting only to established project conventions:

- `demos/tiny_shop/shop.weave`: the actual checkout and helper flows.
- `demos/tiny_shop/run_demo.py`: a thin standard-library CLI that invokes the existing Weave runner and renders its actual results.
- `demos/tiny_shop/tests/test_tiny_shop.py`: automated integration and rejection tests.
- `demos/tiny_shop/README.md`: prerequisites, exact commands, workflow explanation, expected outcomes, and prototype limits.
- `demos/tiny_shop/requirements.txt`: a comment stating that there are no third-party dependencies.
- `demos/tiny_shop/TEST_REPORT.md`: commands actually executed, exit codes, test counts, observed scenario results, and any remaining limitations.

Keep generated traces, lowered source, and certificates under `demos/tiny_shop/artifacts/`, separate from hand-written source.

CLI contract:

```bash
python3 demos/tiny_shop/run_demo.py --outcome all
python3 demos/tiny_shop/run_demo.py --outcome Ok --trace
python3 demos/tiny_shop/run_demo.py --outcome Err --trace
python3 demos/tiny_shop/run_demo.py --outcome Unknown --trace
python3 demos/tiny_shop/run_demo.py --outcome all --json
```

Default to `--outcome all`. Provide `--help`; reject unsupported options or outcomes with a nonzero exit code. Resolve paths from the script location so the application also works when invoked by absolute path from another directory.

Use `sys.executable` and subprocess argument lists to call the existing runner. Put its global `--json` before its subcommand. Parse its returned JSON; preserve its check status, diagnostics, and actual execution data. On failure, return a nonzero exit code and expose the useful diagnostic. Do not present a failed check as a completed demo.

In normal output, show the outcome, actual NET transition sequence, final stock and recovery counts, and a short explanation. With `--trace`, also show the recorded marking after each event. With `--json`, emit one valid JSON document without banners or progress text on stdout.

Keep all reservation, payment-result branching, and settlement behavior in Weave. Python may select scenarios, invoke tools, format output, and assert test expectations; it must not reproduce the workflow as a second state machine or fabricate successful traces. No browser UI, database, provider integration, or background worker is needed.

## 4. Check, lower, run, and verify

Create the artifact directory before using output options. Execute these operations against the newly written application, adapting paths only as necessary:

```bash
python3 scripts/weave.py check demos/tiny_shop/shop.weave
python3 scripts/weave.py lower demos/tiny_shop/shop.weave --output demos/tiny_shop/artifacts/shop.lowered.weave
python3 scripts/weave.py --json simulate demos/tiny_shop/shop.weave --entry checkout --outcome all --trace
python3 scripts/weave.py --json simulate demos/tiny_shop/artifacts/shop.lowered.weave --entry checkout --outcome all --trace
python3 scripts/weave.py analyze --certificate demos/tiny_shop/artifacts/inventory-proof.json
python3 scripts/weave.py verify demos/tiny_shop/artifacts/inventory-proof.json
```

These commands use the default bundled Inventory net. If the installation requires an explicit net path, pass the same `--net` to every applicable operation; do not accidentally analyze a different net.

Run the application itself using all five CLI examples above. Capture actual JSON scenario output as `artifacts/scenarios.json`. Compare source and lowered results per outcome: same final marking, return result, and ordered NET transition names. Do not compare incidental file paths or source-line details.

## 5. Test observable behavior and safety properties

Use standard-library `unittest` and the real runner. Assert substantive outcomes, not merely that a command prints text or exits successfully.

Required tests:

1. The new flow passes checking and lowering.
2. All three scenarios execute and match the expected final markings above.
3. NET transition names are exactly:
   - `Ok`: `reserve`, `arm`, `dispatch`, `charge_ok`, `sell`.
   - `Err`: `reserve`, `arm`, `dispatch`, `charge_err`, `release`.
   - `Unknown`: `reserve`, `arm`, `dispatch`, `charge_unknown`, `handoff`.
4. At every recorded marking, counts are nonnegative and both Inventory accounting equations hold: `available + held + escrow + inflight + paid + unpaid + uncertain + recovery_queue + manual + sold == 1`, and `registrations == escrow + inflight + paid + unpaid + uncertain + recovery_queue + manual`.
5. The Unknown path neither sells nor releases the item and retains the recovery registration. The Err path never sells; the Ok path never releases.
6. Source and lowered execution agree for every outcome.
7. The application emits parseable JSON, handles invalid CLI input with a nonzero exit, surfaces runner failures, and works from a different working directory. Use temporary copies for any deliberate source corruption.
8. Temporary, deliberately invalid Weave variants are rejected with the expected diagnostics: omit the Unknown match arm (`E214`); reuse a moved hold (`E203`); pass Paid to `Inventory.release` (`E208`). Use the kit's known invalid examples as references and assert the diagnostic code, not just failure. Never repair or overwrite the teaching fixtures.

Run:

```bash
python3 -B -m unittest discover -s demos/tiny_shop/tests -v
python3 scripts/weave.py examples
python3 scripts/weave.py test
python3 -B -m unittest discover -s tests -q
```

Investigate failures, repair the application, and rerun affected checks. Report pre-existing failures separately. Do not weaken assertions, invariants, type rules, identity checks, evidence guards, or consumer lists to get a pass. Leave the vendored prototype unchanged.

## 6. Finish with evidence

Populate the README and test report from actual results. Clearly distinguish:

- `PROVED`: aggregate token accounting under the parsed net semantics.
- `CHECKED WITHIN BOUNDS`: the declared one-order safety model, with its reported bounds and assumptions.
- `CHECKED`: the flow's supported type and linear-ownership rules.
- `SCRIPTED`: execution with a selected payment outcome.

Certificate verification checks source-bound accounting; it is not a proof of the entire application. This demo has no persistent inventory, real payment I/O, asynchronous recovery, or established multi-order correctness. A recovery-queue token in this simulator is not a running durable recovery service.

Do not use unsupported Weave conditionals, loops, retries, parallel flows, recursion, scalar computations, or statements after a terminal match. Python CLI control flow is ordinary presentation and test plumbing and is not a Weave language feature.

When done, give a concise summary of what you created, the exact command to run the demo, actual test results, the locations of the source and report, and remaining limits. If execution is blocked, state exactly what you could and could not run. Never claim execution or tests that did not occur. Do not commit, push, or publish unless separately requested.
