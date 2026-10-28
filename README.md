<div align="center">

# Weave

**A protocol language for services that cannot afford to lose track of money or resources.**

Linear resource handles · conservation proofs · bounded protocol checking · durable external effects
— in one artifact, with a disciplined vocabulary for what each result means.

[![CI](https://github.com/quaat/weave/actions/workflows/ci.yml/badge.svg)](https://github.com/quaat/weave/actions/workflows/ci.yml)
[![Specification site](https://github.com/quaat/weave/actions/workflows/docs.yml/badge.svg)](https://github.com/quaat/weave/actions/workflows/docs.yml)
![Status: research](https://img.shields.io/badge/status-research%20draft%200.2-blueviolet)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Dependencies: none](https://img.shields.io/badge/runtime%20deps-none-success)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

[Specification](https://quaat.github.io/weave/) ·
[Single page](https://quaat.github.io/weave/single-page/) ·
[PDF](https://github.com/quaat/weave/releases) ·
[Roadmap](https://github.com/quaat/weave/issues/61) ·
[Prototype report](inventory-proof/REPORT.md)

</div>

---

Weave is an experimental language that combines **Petri nets** for describing stateful protocols with **nominally typed, linear flows** for composing their operations. A net declares what a resource is, who may issue it, who may consume it, and what must be conserved. A flow receives handles to those resources and cannot drop, copy, or forge one. External operations return one of **three** outcomes, and the third one, *Unknown*, cannot be ignored by any program the checker accepts.

The project is grounded in a working prototype and a specification that only describes what the prototype actually does. Where the design is ahead of the implementation, the specification says so, by name.

> **Status.** Research-stage. There is no general compiler and no distributed runtime. The prototype checks, proves, explores, and executes a restricted fragment against a reference protocol. See [What is not here](#what-is-not-here) before relying on any claim.

## Why

Most production incidents in payment, inventory, booking, and provisioning systems are not computation bugs. They are custody bugs: a reservation that was released while a charge was in flight, a refund that was retried into a double refund, a lost provider response that was treated as a failure. Mainstream languages cannot stop you from writing these; the best they offer is a code-review finding. Weave makes them type errors.

| Guarantee | How Weave gets it |
|---|---|
| You cannot write code that forgets a reservation | Handles are **linear**: every path must transfer or discharge every live handle (`E204`) |
| You cannot charge without the protocol's permission | Operations need a **permit** that only the net's own transitions can mint (`E201`, `E205`) |
| Stock and money are never created or lost | **P-invariant proofs** over the net's incidence matrix, for any starting quantity (`PROVED`) |
| "Released while the charge was in flight" is found before deploy | **Bounded exploration** with evidence witnesses and a readable counterexample trace (`E320`, `E420`) |
| A lost response is not a failure | Foreign operations return `Ok` / `Err` / **`Unknown`**; `Unknown` carries a recovery obligation that propagation preserves |
| Per-order bookkeeping cannot cross orders | **Coloured** places and per-colour invariant families; `tokens match firing` rejects cross-identity arcs |
| A crashed worker does not lose the protocol state | A **process-crash model** with six injected crash points, fencing, and immutable final evidence |

## A taste

Three flows against the reference `Inventory` protocol. `?` propagates `Err` and `Unknown` with their payloads; the `Unknown` branch must hand the obligation to recovery or the file does not check.

```weave
flow checkout_propagating(tenant: TenantId, order: OrderId, amount: Money):
    let result = await place_order(tenant, order, amount)
    match result:
        Ok():
            return
        Err(unpaid):
            await Inventory.release(unpaid)
            return
        Unknown(uncertain):
            await Inventory.handoff(uncertain)
            return

flow place_order(tenant: TenantId, order: OrderId, amount: Money) -> CheckoutOutcome[tenant, order]:
    let hold = await Inventory.reserve(tenant, order)
    let paid = (await pay_with(tenant, order, amount, hold))?
    await Inventory.sell(paid)
    return Ok()

flow pay_with(tenant: TenantId, order: OrderId, amount: Money, hold: Hold[tenant, order]) -> ChargeOutcome[tenant, order]:
    let escrow = await Inventory.arm(hold)
    let paid = (await Payments.charge(tenant, order, amount, escrow))?
    return Ok(paid)
```

Try to skip the escrow step:

```weave
flow bypass(tenant: TenantId, order: OrderId, amount: Money):
    let result = await Payments.charge(tenant, order, amount)
    return
```

```text
direct_charge.weave:2: E201
  Payments.charge expects 4 arguments; got 3.
  Missing or invalid arguments: permit: Escrow[tenant, order].
  Obtain Escrow through Inventory.arm; its constructor is sealed.
```

And what the analyser says about the protocol itself:

```text
PROVED aggregate stock_conservation
PROVED aggregate pool_credits
PROVED per-colour family job_accounting
PROVED per-colour family registration_balance
PROVED per-colour family identity_conservation
CHECKED WITHIN BOUNDS orders=2, stock=2, states=841, edges=3712
CHECKED token identity on every enabled firing; unique admission per tenant/order
```

## Reading a result

Weave's tooling uses six words, and the specification forbids using one when another is meant.

| Label | What it establishes |
|---|---|
| **PROVED** | An exact integer invariant holds for every finite firing sequence and every nonnegative initial stock. Says nothing about ordering. |
| **CHECKED WITHIN BOUNDS** | A finite model was exhaustively explored at explicit colours, stock, token bounds and guard abstraction. |
| **CHECKED flow** | Static type, identity, move, return and exhaustiveness checks passed. |
| **SCRIPTED / passed scenario** | One concrete execution or injected crash case satisfied its assertions. |
| **VIOLATED** | A counterexample was found; the trace is printed. |
| **NOT ESTABLISHED** | Missing model, exhausted budget, or a guarantee outside the tool. Never reported as a pass. |

## Repository map

Each directory is self-contained with its own README, tests and requirements. Run commands from inside the directory.

| Directory | What it is | Start with |
|---|---|---|
| [`specification/`](specification) | The language specification, draft 0.2: lexical rules, EBNF, inference rules, net and flow semantics, the dynamic execution contract (D0), declared evidence (N2), verification semantics, conformance appendix, rationale and design history. Every displayed example is re-checked at build time. | [`specification/README.md`](specification/README.md) · [site](https://quaat.github.io/weave/) |
| [`inventory-proof/`](inventory-proof) | The prototype (v3): net parser, ownership validator, P-invariant prover with certificates, bounded order explorer, linear flow checker with `?` lowering, scripted executor, coloured nets, and a SQLite-backed process-crash model. Standard library only. | [`inventory-proof/REPORT.md`](inventory-proof/REPORT.md) |
| [`agent-kit/`](agent-kit) | A starter kit for working on Weave with Codex or Claude Code: `AGENTS.md`, a portable `weave` skill with a vendored prototype and CLI, teaching examples with expected diagnostics, and demos (`tiny_shop`, `merge_sort`). Includes an explicitly separate pure-`fn` extension with integer lists, recursion and a cooperative fork/join scheduler. | [`agent-kit/README.md`](agent-kit/README.md) |

## Quick start

Python 3.11 or newer. Only the specification build needs third-party packages.

```bash
# Prototype: prove, explore, check, simulate, crash-test
cd inventory-proof
python3 demo.py
python3 -m unittest discover -s tests -v        # 143 tests, including process-crash cases

# Agent kit: the same prototype behind a small CLI
cd agent-kit
python3 scripts/weave.py doctor
python3 scripts/weave.py check examples/valid/checkout_propagating.weave
python3 scripts/weave.py simulate examples/valid/checkout_propagating.weave \
    --entry checkout_propagating --outcome all
python3 scripts/weave.py examples                 # teaching corpus vs. expected diagnostics
python3 scripts/weave.py test                     # bundled prototype suite (143 tests)

# Specification: build the site locally
cd specification
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements.txt
make html                 # _build/html/index.html
make validate-offline     # examples, grammar audit, tests, strict build, link audit
make latexpdf             # needs XeLaTeX + latexmk
```

## How the pieces fit

```
                 ┌──────────────────────────┐
   net  ───────▶ │ parse · validate sealing │──▶ PROVED invariants (certificate)
                 │ P-invariants · families  │──▶ CHECKED WITHIN BOUNDS (trace on failure)
                 └────────────┬─────────────┘
                              │ API environment
   flows ──────▶ ┌────────────▼─────────────┐
                 │ F0 checker · ? lowering  │──▶ CHECKED flow  /  E2xx with line + rule
                 └────────────┬─────────────┘
                              │
                 ┌────────────▼─────────────┐
                 │ scripted executor (N0)   │──▶ SCRIPTED trace, final marking
                 │ crash model R0 (N1)      │──▶ passed scenario, persisted state
                 └──────────────────────────┘
```

The net is the single source of truth: the type checker, the prover, the explorer and the executors all read the same file. There is no separate model to keep in sync.

## What is not here

The specification keeps a register of these; the short list:

- **No general computation in flows.** Values are opaque scalars. Pure functions, arithmetic, lists, `if`/`else`, loops and recursion exist only in the agent kit's separate `fn` extension and are not part of the specified fragment ([M1](https://github.com/quaat/weave/issues/55)).
- **No general runtime.** The simulator fails on a disabled transition instead of waiting; the crash model executes the Inventory protocol, not arbitrary flows. The dynamic contract D0 is specified, not implemented ([M3](https://github.com/quaat/weave/issues/57)).
- **Payment vocabulary in the check grammar.** `paid_evidence` and `rejected_evidence` are keywords today. Declared evidence classes (N2) are specified, not implemented ([M2](https://github.com/quaat/weave/issues/56)).
- **Bounded, not general.** Ordering is checked at two orders; conservation is proved for any stock. No liveness, deadlock-freedom, fairness, or arbitrary-order theorem.
- **No provider truth, no network.** Evidence guards are abstract witnesses; adapters, authentication and retention are external contracts.
- **No modules, no time, no inbound events** yet.

## Roadmap

Tracked as milestones and epics; the plan is [#61](https://github.com/quaat/weave/issues/61).

| Milestone | Theme |
|---|---|
| [M0](https://github.com/quaat/weave/issues/54) | Contracts and baseline: rule IDs in diagnostics, conformance artifact, independent certificate verifier |
| [M1](https://github.com/quaat/weave/issues/55) | Pure code and modules |
| [M2](https://github.com/quaat/weave/issues/56) | General protocols (N2 declared evidence) and the adapter ABI |
| [M3](https://github.com/quaat/weave/issues/57) | General execution: D0 waiting scheduler, any flow against any net |
| [M4](https://github.com/quaat/weave/issues/58) | Analysis and public experimental release |
| [M5](https://github.com/quaat/weave/issues/59) | Durable service preview: outbox, persisted deadlines, version binding, crash suite |
| [M6](https://github.com/quaat/weave/issues/60) | Composition and industrial pilots: fork/join, race, saga, operational controls |

## Continuous integration

| Workflow | Runs on | What it does |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | Pushes to `main`, pull requests | `inventory-proof`: unit tests, `demo.py` reproduces committed outputs, `durable.py` (Python 3.11–3.13). `agent-kit`: `doctor`, kit tests, example expectations, bundled prototype suite, demo tests (3.11–3.13). `specification`: `make validate-offline`, single-page and text builds, HTML link audit |
| [`docs.yml`](.github/workflows/docs.yml) | Pushes to `main`; PRs touching `specification/` | Builds the multi-page and single-page editions, audits links, form targets and assets; only `main` deploys to GitHub Pages |
| [`pdf.yml`](.github/workflows/pdf.yml) | Manual runs; `spec-v*` tags | Builds the XeLaTeX PDF; tag pushes attach it to the release |

External link checking (`make linkcheck`) is run locally before a release.

## Prototype snapshots

The v3 prototype lives in three places. Keep them identical unless you also update the recorded hashes.

| Location | Role | Pinned by |
|---|---|---|
| `inventory-proof/` | Working copy for further development | Started byte-identical to the specification snapshot |
| `agent-kit/.agents/skills/weave/assets/prototype/` | Vendored, unchanged; the pure `fn` extension lives beside it in `scripts/weave_pure/` | `agent-kit/PROVENANCE.json` |
| `specification/reference/prototype/` | Snapshot the specification is grounded in | `specification/PROVENANCE.json`, verified by `scripts/validate.py` |

Changes in `inventory-proof/` reach the specification only through a deliberate snapshot refresh and a new `PROVENANCE.json`.

## Where Weave fits

Weave is a domain language, not a general one. It is an obvious choice where an **exclusive resource** meets an **external party whose answer can be lost**, and someone later has to **prove what happened**: payment orchestration, inventory and seat allocation, cloud quota and provisioning, settlement and trade lifecycle, telecom and energy grants. It is a poor choice for data pipelines, CRUD services and user interfaces, and the project does not recommend it there.

Compared with Rust, Haskell or Erlang, Weave offers a guarantee they structurally cannot: obligations tied to a declared protocol that the compiler will not let you drop. Compared with Move, P, TLA+ and durable-execution runtimes such as Temporal, it is the only design we know of that puts linear resource types, conservation proofs, bounded protocol checking and durable external effects in one artifact.

## Contributing

Issues and pull requests are welcome. Contributions are accepted under the [MIT License](LICENSE). There is one house rule that the specification states formally and the test suites enforce: **do not weaken a check to make a caller pass.** A flow that cannot be written against a net is a finding about the net or the caller, not a reason to relax a guard, a consumer list, an invariant or an ordering property. Expected-rejection fixtures are intentional.

- Read [`agent-kit/AGENTS.md`](agent-kit/AGENTS.md) for the working conventions, whether or not you use an agent.
- Prototype changes need tests, an updated boundary in `docs/prototype-status.md`, and a refreshed `PROVENANCE.json`.
- Specification changes are built with `-W` (warnings are errors) and every displayed example is re-checked by the build.

## Citing

If you reference this work, cite the specification draft and the prototype version together, since claims attach to exact snapshot hashes:

```text
Weave language specification, draft 0.2, with prototype v3. https://github.com/quaat/weave (2026).
```

## License

Weave is released under the [MIT License](LICENSE). Copyright (c) 2026 Thomas F. Hagelien.

The license covers the whole repository: the prototype and its vendored copies, the agent kit, and the specification sources and their built editions (HTML, single page and PDF).
