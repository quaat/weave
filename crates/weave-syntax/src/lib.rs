// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Weave syntax layer: the first Rust slice of `docs/decisions/0009-rust-implementation.md`.
//!
//! The parser is driven by `specification/grammar/weave.ebnf`, embedded with
//! `include_str!` and interpreted at run time (no generated code, no build
//! script). It produces a concrete syntax tree whose node kinds are the EBNF
//! production names, with byte spans, lines and columns on every node, and
//! with comments and blank lines kept as trivia, so printing the tree
//! reproduces the source exactly. Faults are `weave-diagnostic-v1` diagnostics
//! with codes from `specification/diagnostics.json`.
//!
//! The parser checks syntax only. It keeps integer literals as source text and
//! defines no Weave semantics; static rules apply after parsing.

pub mod cst;
pub mod diagnostic;
pub mod ebnf;
pub mod grammar;
pub mod json;
pub mod lexer;
pub mod parser;
pub mod span;

pub use cst::{Cst, Element, Leaf, Node};
pub use diagnostic::{Diagnostic, Related, SingleSource, SourceMap};
pub use parser::{Options, Start, parse, parse_bytes, parse_with};
pub use span::{FileId, Span};

/// Parse, print and re-parse `source`; true when the print equals the source and
/// the re-parsed tree equals the first.
pub fn round_trips(source: &str, start: Start) -> Result<bool, Diagnostic> {
    let first = parse(source, start)?;
    let printed = first.print();
    if printed != source {
        return Ok(false);
    }
    let second = parse(&printed, start)?;
    Ok(first == second)
}
