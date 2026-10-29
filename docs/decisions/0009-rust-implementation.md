<!--
SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
SPDX-License-Identifier: MIT
-->

# 0009: Rust implementation boundary, first slice and toolchain

- **Issue:** [quaat/weave#9](https://github.com/quaat/weave/issues/9), milestone M1
- **Status:** Proposed. Awaiting the maintainer's decision on #9. Nothing in the Rust
  workspace is built until the decision is recorded.
- **Prepared against:** base revision `e7c3f3cab1e25994b96a948cbe27c96bb061d5a8`, 30 October 2026
- **Decision owner:** the maintainer
  ([implementation-language policy](../development/implementation-language.md)).
- **Why now:** #9 is the first M1 task that needs a production front end. The policy requires
  this record before substantial interpreter or compiler work.

## Context

- The authoritative grammar is `specification/grammar/weave.ebnf` (110 lines, 68
  productions, as counted by the grammar audit), plus the target-only delta `weave-n2-delta.ebnf`. The specification shows it
  with `literalinclude` in `grammar.rst`.
- Two parsers exist today, and neither is a production front end:
  - `inventory-proof/checker.py` has a hand-written indentation and line parser. It keeps
    no comments and only line-level positions. It is pinned twice as a snapshot and must not
    change.
  - `specification/scripts/grammar_audit.py` generates a Lark Earley grammar from the EBNF.
    It parses the corpus to an acceptance verdict only, with no tree, spans or comments.
- #9 asks for one grammar that drives both the parser and the documentation. It also needs
  a concrete syntax tree with comments and full spans (needed by #14 and #6), and a
  parse–print round trip over the conformance corpus.
- Rust 1.89.0 with rustfmt, clippy, cargo-audit and cargo-deny is installed in
  `~/.cargo/bin` (see [capabilities](../development/capabilities.md)).
- The workflow already derives `cargo fmt`, `cargo clippy` and `cargo test` checks once a
  root `Cargo.toml` exists.

## Decision areas

### 1. Rust boundary

- **Option 1A (recommended).** The syntax layer moves to Rust first, as the first vertical
  slice: lexer, layout (INDENT/DEDENT), concrete syntax tree with spans and comments,
  printer, and syntax diagnostics.
  - Static checking, the IR (#15), the pure evaluator (#10) and the runtime follow as later
    slices, each through its own task.
  - Python stays as the reference behaviour (`inventory-proof/`, pinned snapshots), the
    generated grammar audit, specification tooling, the workflow tooling and differential
    tests.
- **Option 1B.** Build the CST parser in Python inside the specification tooling now, and
  move to Rust later. This is cheaper today, but it grows a second Python front end that
  the policy says not to grow, and the parser would be rewritten in M1/M2 anyway.

### 2. Migration

- Incremental, never a rewrite. The vertical slice is parser → (later) checker →
  diagnostics, always against the existing corpus in `specification/examples/`.
- Each slice must agree with the Python reference wherever that reference matches the
  specification. Disagreements are recorded as discrepancies with a rule ID. They are never
  silently resolved in favour of either side.
- The prototype and its snapshots are never replaced automatically. The agent kit's
  pure-function extension is preserved until an explicit migration task covers it.

### 3. How the grammar drives the parser (#9 AC-1)

- **Option 3A (recommended): grammar-driven.** The Rust crate embeds `weave.ebnf` at build
  time (`include_str!`), parses the EBNF and interprets it as an ordered-choice parser that
  builds the CST.
  - CST node kinds are the EBNF production names, so the grammar text is literally the
    single source of truth for both the parser and the documentation.
  - Lexical productions given as special sequences (`IDENT`, `UINT`, `POSINT`, `NL`,
    `INDENT`, `DEDENT`) are implemented by the lexer and the layout pass. The lexical
    chapter specifies them.
  - A normalisation check rejects undefined or unused productions and duplicate
    definitions. It also rejects alternatives that ordered choice would shadow, so the
    parser cannot silently differ from the EBNF reading.
- **Option 3B: hand-written recursive descent.** A conformance test checks the parser
  against the EBNF. Diagnostics would be better and parsing faster, but there would be two
  sources of syntax kept in step only by tests.

### 4. Workspace and crate layout

- A virtual workspace in the root `Cargo.toml`, with `Cargo.lock` committed.
  `resolver = "3"`, `edition = "2024"` and `rust-version = "1.89"` are set at workspace
  level.
- `crates/weave-syntax` (library) contains the lexer, layout, EBNF loader, CST with byte
  spans and line/column, comments as trivia, the printer and syntax diagnostics.
- `crates/weave-syntax` also builds a small binary target, `weave-syntax`. It is used by
  tests and the Python audit to dump the CST as JSON and to run the round trip. It is not a
  user-facing CLI. The user CLI comes with the checker slice.
- Later crates (`weave-check`, `weave-ir`, `weave-eval`, `weave-runtime`) are added by their
  own tasks. Names are indicative only.

### 5. Toolchain

- `rust-toolchain.toml` pins channel `1.89.0` with the `rustfmt` and `clippy` components.
  The minimum supported Rust version (MSRV) is 1.89.
- Raising the pin is an ordinary reviewed change that updates this record's appendix.
- CI installs the pinned toolchain and runs `cargo fmt --all --check`,
  `cargo clippy --all-targets -- -D warnings` and `cargo test --all`.

### 6. Dependency policy

- **Option 6A (recommended).** The first slice uses only the standard library: no runtime
  or dev dependencies, and no build scripts. That avoids a supply-chain review for the
  parser.
- Later dependencies need all of the following:
  - a licence compatible with MIT, as decided in #2: MIT, Apache-2.0, BSD-2/3-Clause, ISC,
    Zlib or Unicode-3.0, checked with `cargo deny check licenses` once a dependency exists;
  - `cargo audit` with no unwaived advisories;
  - a pinned version recorded in `Cargo.lock`;
  - a one-line justification in the PR;
  - safety review.
- Proc-macro and build-script dependencies need an explicit justification.
- **Option 6B.** Allow common parsing crates (for example `logos`, `serde_json`) now.

### 7. Conformance strategy

- **Shared fixtures.** Rust tests read `specification/examples/manifest.json` and the
  corpus files directly. There are no copies.
- **Differential tests.** For every corpus file and every mutation, the Rust parser's
  syntax verdict must agree with the generated Lark audit and with the reference checker's
  syntax classification (`E003`/`E200` versus anything else). The comparison runs from the
  specification's validation scripts, which call the `weave-syntax` binary.
- **Round trip.** Printing the CST reproduces the source byte for byte, including comments
  and blank lines, and re-parsing the output yields an equal tree. Normalised printing is
  the formatter's job (#14).
- **Diagnostics.** Every syntax diagnostic carries a code from `specification/diagnostics.json`,
  a rule ID and a source span, in the `diagnostic.v1` shape from #6.
- **Semantics belong to the specification.** The parser keeps integer literals as source
  text, so Rust machine-integer widths never become Weave semantics (#5, area 1A). Rust
  panics are bugs, never diagnostics: adversarial tests include deep nesting, very long
  lines, non-ASCII input, tabs and truncated files, and must produce diagnostics without
  panicking.

## Recommendation (not a decision)

Adopt **1A**, **3A** and **6A**, with the migration, layout, toolchain and conformance
strategy above. #9 then delivers:

- the `weave-syntax` crate;
- the normalised EBNF and the lexical/layout rules in the specification;
- the round trip and differential audit over the whole corpus;
- a discrepancy record for the hand parser.

## Consequences

- CI gains a Rust job, and contributors need the pinned toolchain for Rust changes.
- The Python generated-grammar audit stays as an independent second parser, so a
  grammar-interpreter bug cannot pass silently.
- #14 (formatter) and #15 (IR source maps) build on the CST and its spans.

## Rejected alternatives

The rejected alternatives are listed with each decision area above: 1B, 3B and 6B.
