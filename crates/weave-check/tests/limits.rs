// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Nesting limits (`pure.rst`, "Nesting limits"): just under each limit is
//! accepted, just over it is E500 at stage `limit`, and far over it is the
//! same diagnostic, never a stack overflow. Runs in the debug build.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use weave_check::{EXPR_DEPTH_LIMIT, SYNTAX_DEPTH_LIMIT, check};

fn chain(op: &str, operand: &str, n: usize) -> String {
    vec![operand; n].join(&format!(" {op} "))
}

fn int_fn(expr: &str) -> String {
    format!("fn f(x: Int) -> Int:\n    return {expr}\n")
}

fn bool_fn(expr: &str) -> String {
    format!("fn f(x: Bool) -> Bool:\n    return {expr}\n")
}

fn assert_limit(src: &str) {
    match check(src) {
        Ok(_) => panic!("accepted a source of {} bytes", src.len()),
        Err(d) => {
            assert_eq!((d.code, d.stage), ("E500", "limit"), "{}", d.message);
            assert_eq!(d.rule().as_deref(), Some("P0-FILE-1"));
            assert!(!weave_check::is_internal(&d));
        }
    }
}

#[test]
fn the_limits_are_the_documented_values() {
    assert_eq!((SYNTAX_DEPTH_LIMIT, EXPR_DEPTH_LIMIT), (300, 256));
}

#[test]
fn flat_operator_chains_are_bounded_by_the_expression_depth_limit() {
    // A chain of n operands is n deep: n - 1 binary nodes over one operand.
    for (op, operand, wrap) in [
        ("+", "x", int_fn as fn(&str) -> String),
        ("*", "x", int_fn),
        ("-", "1", int_fn),
        ("and", "x", bool_fn),
        ("or", "x", bool_fn),
    ] {
        let at = wrap(&chain(op, operand, EXPR_DEPTH_LIMIT));
        assert!(check(&at).is_ok(), "{op} at the limit");
        assert_limit(&wrap(&chain(op, operand, EXPR_DEPTH_LIMIT + 1)));
        // Far beyond the limit: a diagnostic, not a stack overflow (S-1).
        assert_limit(&wrap(&chain(op, operand, 100_000)));
    }
    // Mixed: x and x or x and x ... has depth about the number of operands.
    assert_limit(&bool_fn(&vec!["x and x"; 40_000].join(" or ")));
}

#[test]
fn unary_minus_and_parentheses_are_bounded() {
    let minus = |n: usize| int_fn(&format!("{}1", "-".repeat(n)));
    assert!(check(&minus(EXPR_DEPTH_LIMIT - 1)).is_ok());
    assert_limit(&minus(EXPR_DEPTH_LIMIT));
    // Each parenthesised level costs seven productions (expr, conjunction,
    // comparison, sum, product, unary, primary); around a literal (UINT is not
    // counted) k levels reach syntax depth 13 + 7k.
    let parens = |k: usize| int_fn(&format!("{}1{}", "(".repeat(k), ")".repeat(k)));
    assert!(check(&parens(41)).is_ok(), "13 + 7 * 41 = 300");
    assert_limit(&parens(42));
    assert_limit(&parens(10_000));
    // Nested calls reach the syntax depth limit first.
    let calls = |k: usize| {
        format!(
            "fn g(x: Int) -> Int:\n    return x\n\n{}",
            int_fn(&format!("{}x{}", "g(".repeat(k), ")".repeat(k)))
        )
    };
    assert!(check(&calls(25)).is_ok());
    assert_limit(&calls(40));
}

#[test]
fn deep_blocks_are_bounded_by_the_syntax_depth_limit() {
    let nested = |k: usize| {
        let mut src = String::from("fn f(x: Bool) -> Int:\n");
        for i in 0..k {
            let pad = "    ".repeat(i + 1);
            src.push_str(&format!("{pad}if x:\n{pad}    return 0\n{pad}else:\n"));
        }
        src.push_str(&format!("{}return 1\n", "    ".repeat(k + 1)));
        src
    };
    assert!(check(&nested(10)).is_ok());
    assert_limit(&nested(200));
}

#[test]
fn internal_errors_are_distinguished_from_rejections() {
    let d = check("fn f() -> Int:\n    return true\n").unwrap_err();
    assert!(!weave_check::is_internal(&d));
    let internal = weave_check::Diagnostic::new(
        "E500",
        weave_check::INTERNAL_STAGE,
        "x",
        weave_check::Span::at(0),
    );
    assert!(weave_check::is_internal(&internal));
}
