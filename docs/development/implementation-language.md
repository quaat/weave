# Implementation language

**Rust is the default for the production interpreter, compiler and execution runtime.** A
different compiled language needs a documented reason and a maintainer decision. The Python
prototype is not grown into the production interpreter just because it exists.

Python remains the language for orchestration, developer tooling, fixtures, reference
behaviour and differential tests.

## Before substantial interpreter or compiler work

Record an ADR covering:

- the Rust boundary (what moves to Rust first, what stays in Python and why);
- incremental migration: a vertical slice through parser → checker → diagnostics against the
  existing corpus, not a rewrite;
- workspace and crate layout;
- the pinned toolchain (`rust-toolchain.toml`) and the minimum supported Rust version;
- dependency policy (allowed crates, auditing with `cargo audit`, licence compatibility);
- conformance strategy: shared fixtures, differential tests against the Python reference
  where it matches the specification, and the conformance metadata from M0.

The ADR is a decision task: agents prepare it; the maintainer records the decision.

The first such record is [0009: Rust implementation boundary, first slice and
toolchain](../decisions/0009-rust-implementation.md), decided by the maintainer on #9: the
syntax layer moves to Rust first (1A), the parser interprets the EBNF (3A), and vetted crates
are allowed but the standard library is preferred (6B). Later slices (checker, IR, evaluator,
runtime) each need their own task and follow the same record.

## Semantics belong to the specification

Weave semantics are defined by the specification, not by the host language. Rust machine
integers, ownership, panics, concurrency and error handling must not silently become Weave
semantics. Issue #5 controls language decisions, including integer and error semantics;
they are tested explicitly in Rust and against agreed reference fixtures. Python is a
reference only where its behaviour matches the specification.

## Existing prototypes

The v3 prototype exists in `inventory-proof/` (working copy) and as pinned snapshots in
`agent-kit/.agents/skills/weave/assets/prototype/` and `specification/reference/prototype/`.
Snapshots and provenance are preserved unless a task explicitly includes a reviewed refresh,
and the three are never replaced automatically. The agent kit's separate pure-function
extension is preserved until an explicit migration covers it.

## The workspace

The Cargo workspace exists since #9: a virtual workspace in the root `Cargo.toml` (resolver 3,
edition 2024, `rust-version` 1.89, MIT), a committed `Cargo.lock`, and `rust-toolchain.toml`
pinning channel 1.89.0 with `rustfmt` and `clippy`. It has four crates, all standard library
only, with no third-party dependencies. `crates/weave-syntax` (#9) is the syntax layer: lexer and
layout, the grammar-driven parser, the concrete syntax tree with spans and trivia, the printer
and syntax diagnostics. For the P0 pure computation profile (#10), `crates/weave-check` is the
static checker, `crates/weave-eval` the evaluator (in-house arbitrary-precision integers, an
explicit call-frame stack, fuel, depth and integer-size budgets) and `crates/weave-cli` the
`weave` command.

Because `Cargo.toml` exists, the workflow derives the Rust checks for every task: `cargo fmt
--all --check`, `cargo clippy --all-targets -- -D warnings` and `cargo test --all`, run from the
repository root; CI runs them in its `rust` job. The conformance and differential tests named
by the ADR are the crates' corpus tests, the Rust comparison in the specification's grammar
audit and the P0 differential (`specification/scripts/p0_differential.py`), which compares
the `weave` command with the Python P0 reference evaluator; both comparisons run in
`make validate-offline`. Rust 1.89.0 is installed in `~/.cargo/bin` but not on the
default `PATH`.
