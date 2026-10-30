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

/// Stack for lowering and checking. The AST is as deep as the parse tree,
/// which the parser bounds; a dedicated thread keeps the bound independent of
/// the caller's stack.
pub const CHECK_STACK_BYTES: usize = 64 << 20;

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
            "internal",
            "Internal checker error.",
            Span::at(0),
        )),
        Err(e) => Err(Diagnostic::new(
            weave_syntax::diagnostic::PURE_SYNTAX_CODE,
            "limit",
            format!("Could not start the checker thread: {e}"),
            Span::at(0),
        )),
    }
}
