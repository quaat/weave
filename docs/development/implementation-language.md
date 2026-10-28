# Implementation language

<!-- docs-audit: planned rust-toolchain.toml Cargo.toml -- created by the Rust ADR task -->

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

## Checks once a workspace exists

The workflow derives Rust checks from the actual workspace when `Cargo.toml` appears at the
repository root: `cargo fmt --all --check`, `cargo clippy --all-targets -- -D warnings`,
`cargo test --all`, plus negative, conformance and differential tests named by the ADR. At
bootstrap, Rust 1.89.0 is installed in `~/.cargo/bin` but not on the default `PATH`.
