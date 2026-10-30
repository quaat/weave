// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The `weave-syntax` binary: exit codes and output documents.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::io::Write;
use std::process::{Command, Output, Stdio};
use weave_syntax::json::{self, Value};

const BIN: &str = env!("CARGO_BIN_EXE_weave-syntax");

fn example(rel: &str) -> String {
    format!(
        "{}/../../specification/examples/{rel}",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn run(args: &[&str], stdin: Option<&[u8]>) -> Output {
    let mut child = Command::new(BIN)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    if let Some(bytes) = stdin {
        child.stdin.take().unwrap().write_all(bytes).unwrap();
    }
    drop(child.stdin.take());
    child.wait_with_output().unwrap()
}

fn stdout_json(out: &Output) -> Value {
    json::parse(&String::from_utf8_lossy(&out.stdout)).unwrap()
}

#[test]
fn parse_prints_the_tree_with_spans() {
    let file = example("valid/checkout.weave");
    let out = run(&["parse", "--start", "flow-file", &file], None);
    assert_eq!(out.status.code(), Some(0));
    let doc = stdout_json(&out);
    assert_eq!(
        doc.get("format").and_then(Value::as_str),
        Some("weave-cst-v1")
    );
    let root = doc.get("root").unwrap();
    assert_eq!(root.get("kind").and_then(Value::as_str), Some("flow-file"));
    assert!(
        root.get("span")
            .and_then(|s| s.get("end"))
            .and_then(|e| e.get("line"))
            .is_some()
    );
}

#[test]
fn parse_reports_diagnostics_and_exits_one() {
    let file = example("invalid/unsupported_if.weave");
    let out = run(&["parse", "--start", "flow-file", &file], None);
    assert_eq!(out.status.code(), Some(1));
    let doc = stdout_json(&out);
    let d = doc.as_array().and_then(|a| a.first()).unwrap();
    assert_eq!(
        d.get("format").and_then(Value::as_str),
        Some("weave-diagnostic-v1")
    );
    assert_eq!(d.get("code").and_then(Value::as_str), Some("E200"));
    assert_eq!(d.get("rule").and_then(Value::as_str), Some("CONF-REQ-1"));
    let start = d.get("span").and_then(|s| s.get("start")).unwrap();
    assert_eq!(start.get("line"), Some(&Value::from_usize(3)));
    for key in [
        "category",
        "secondary_rules",
        "severity",
        "stage",
        "message",
        "related",
        "details",
    ] {
        assert!(d.get(key).is_some(), "{key}");
    }
}

#[test]
fn roundtrip_exit_codes() {
    let ok = run(
        &[
            "roundtrip",
            "--start",
            "n1-file",
            &example("nets/Inventory.coloured.weave"),
        ],
        None,
    );
    assert_eq!(ok.status.code(), Some(0));
    let bad = run(
        &[
            "roundtrip",
            "--start",
            "flow-file",
            &example("invalid/skipped_level.weave"),
        ],
        None,
    );
    assert_eq!(bad.status.code(), Some(1));
    let stdin = run(
        &["roundtrip", "--start", "flow-file", "-"],
        Some(b"flow f():\r\n    return\r\n"),
    );
    assert_eq!(stdin.status.code(), Some(0));
}

#[test]
fn invalid_utf8_on_stdin_is_a_diagnostic() {
    let out = run(&["parse", "--start", "n0-file", "-"], Some(b"net \xff"));
    assert_eq!(out.status.code(), Some(1));
    let d = stdout_json(&out);
    assert_eq!(
        d.as_array()
            .and_then(|a| a.first())
            .and_then(|d| d.get("code"))
            .and_then(Value::as_str),
        Some("E003")
    );
}

#[test]
fn usage_errors_exit_two() {
    for args in [
        &[][..],
        &["parse"][..],
        &["parse", "--start", "f0-file", "x.weave"][..],
        &["frobnicate"][..],
        &["parse", "--start", "flow-file", "/nonexistent/file.weave"][..],
        &["grammar", "extra"][..],
    ] {
        assert_eq!(run(args, None).status.code(), Some(2), "{args:?}");
    }
}

#[test]
fn grammar_reports_no_problems() {
    let out = run(&["grammar"], None);
    assert_eq!(out.status.code(), Some(0));
    let doc = stdout_json(&out);
    assert_eq!(doc.get("problems"), Some(&Value::Array(Vec::new())));
    // 68 F0/N0/N1 productions (quaat/weave#9), 27 P0 productions (quaat/weave#10)
    // and 5 modules-1 productions (quaat/weave#12: use-net, module-file,
    // import-decl, import-name, module-item).
    assert_eq!(doc.get("productions"), Some(&Value::from_usize(100)));
    let starts = doc
        .get("start_symbols")
        .and_then(Value::as_array)
        .map(<[Value]>::len);
    assert_eq!(starts, Some(5));
}
