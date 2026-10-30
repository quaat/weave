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
//! [`check_entry`] checks a program of several module files (modules-1,
//! `chapters/names.rst`): [`modules`] loads and resolves the imports from one
//! project root, and every span carries its file ([`weave_syntax::FileId`]).
//!
//! The checker defines no semantics of its own: where this code and the
//! chapter differ, the chapter is right and the difference is a defect.

pub mod ast;
pub mod check;
pub mod lower;
pub mod modules;
pub mod typed;

pub use check::{TYPE_DEPTH_LIMIT, check_program};
pub use modules::{Entry, Failure, Root, project_root};
pub use typed::{Package, Prim, Program, SourceFile, Sources, Symbol, Ty};
pub use weave_syntax::{Diagnostic, FileId, Span};

pub use lower::{EXPR_DEPTH_LIMIT, SYNTAX_DEPTH_LIMIT};

/// Stack for lowering and checking. Recursion follows the syntax tree, the
/// AST and types: the syntax depth is at most [`SYNTAX_DEPTH_LIMIT`], the
/// expression depth at most [`EXPR_DEPTH_LIMIT`], both checked before any
/// recursive pass over the AST, and every type is at most
/// [`TYPE_DEPTH_LIMIT`] deep, which also bounds the depth of every value (a flat operator chain is shallow in the syntax tree but deep
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

/// Parse, lower and check a P0 pure file (or a module file without imports)
/// given as text, with no project root: an import is E605 (`MOD-ROOT-1`).
pub fn check(source: &str) -> Result<Program, Diagnostic> {
    check_entry(
        Entry {
            name: String::new(),
            text: source.to_string(),
            path: None,
        },
        None,
    )
    .map_err(|f| *f.diagnostic)
}

/// Load, resolve and check the program whose entry is `entry`, resolving
/// imports from `root` (modules-1; see [`modules`]). On failure the
/// [`Failure`] holds the first diagnostic and the files loaded so far.
pub fn check_entry(entry: Entry, root: Option<Root>) -> Result<Program, Failure> {
    let internal = |message: String| Failure {
        diagnostic: Box::new(Diagnostic::new(
            weave_syntax::diagnostic::PURE_SYNTAX_CODE,
            INTERNAL_STAGE,
            message,
            Span::at(0),
        )),
        sources: Sources::default(),
    };
    let joined = std::thread::scope(|scope| {
        std::thread::Builder::new()
            .name("weave-check".into())
            .stack_size(CHECK_STACK_BYTES)
            .spawn_scoped(scope, move || modules::check_program_from(entry, root))
            .map(|handle| handle.join())
    });
    match joined {
        Ok(Ok(result)) => result,
        Ok(Err(_)) => Err(internal("Internal checker error.".into())),
        Err(e) => Err(internal(format!("Could not start the checker thread: {e}"))),
    }
}
