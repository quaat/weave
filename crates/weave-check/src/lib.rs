// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The P0 static checker (`specification/docs/chapters/pure.rst`).
//!
//! [`check`] parses a pure file with `weave-syntax` (start symbol
//! `pure-file`), lowers the concrete syntax tree to an AST ([`ast`]) that keeps
//! the source span of every node, and checks the static rules `P0-DECL-*`,
//! `P0-TYPE-*`, `P0-NAME-*`, `P0-CALL-1`, `P0-RECORD-*`, `P0-EFFECT-*`,
//! `P0-FORK-1`, `P0-PATH-1` and `P0-REC-1` in the order the chapter states.
//! The result is a typed program ([`typed`]) whose expressions keep their
//! spans, or the first diagnostic, with a code from `diagnostics.json`, the
//! code's principal rule and a span.
//!
//! The checker defines no semantics of its own: where this code and the
//! chapter differ, the chapter is right and the difference is a defect.

pub mod ast;
pub mod check;
pub mod lower;
pub mod typed;

pub use check::check_program;
pub use typed::{Prim, Program, Ty};
pub use weave_syntax::{Diagnostic, Span};

pub use lower::{EXPR_DEPTH_LIMIT, SYNTAX_DEPTH_LIMIT};

/// Stack for lowering and checking. Recursion follows the syntax tree and the
/// AST: the syntax depth is at most [`SYNTAX_DEPTH_LIMIT`] and the expression
/// depth at most [`EXPR_DEPTH_LIMIT`], both checked before any recursive pass
/// over the AST (a flat operator chain is shallow in the syntax tree but deep
/// in the AST, so the parser's limit alone would not bound it). The bounded
/// passes would fit a default thread; the dedicated thread keeps the bound
/// independent of the caller's stack.
pub const CHECK_STACK_BYTES: usize = 64 << 20;

/// Stage of a diagnostic that reports a defect of this implementation (or a
/// failure to start its thread), not a rejection of the source. Its code is
/// not a statement about the file; tools report it as an internal error.
pub const INTERNAL_STAGE: &str = "internal";

/// True when `d` reports a defect of the checker rather than a P0 rejection.
pub fn is_internal(d: &Diagnostic) -> bool {
    d.stage == INTERNAL_STAGE
}

/// Parse, lower and check a P0 pure file.
pub fn check(source: &str) -> Result<Program, Diagnostic> {
    let run = || {
        let cst = weave_syntax::parse(source, weave_syntax::Start::PureFile)?;
        let file = lower::lower(&cst)?;
        check_program(&file, source)
    };
    let joined = std::thread::scope(|scope| {
        std::thread::Builder::new()
            .name("weave-check".into())
            .stack_size(CHECK_STACK_BYTES)
            .spawn_scoped(scope, run)
            .map(|handle| handle.join())
    });
    match joined {
        Ok(Ok(result)) => result,
        Ok(Err(_)) => Err(Diagnostic::new(
            weave_syntax::diagnostic::PURE_SYNTAX_CODE,
            INTERNAL_STAGE,
            "Internal checker error.",
            Span::at(0),
        )),
        Err(e) => Err(Diagnostic::new(
            weave_syntax::diagnostic::PURE_SYNTAX_CODE,
            INTERNAL_STAGE,
            format!("Could not start the checker thread: {e}"),
            Span::at(0),
        )),
    }
}
