// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The `weave` command: claims, outcomes, budgets, exit statuses and JSON output.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use weave_syntax::json::{self, Value};

fn example(rel: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../specification/examples/pure")
        .join(rel)
}

fn weave(args: &[&str], stdin: Option<&str>) -> Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_weave"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    if let Some(text) = stdin {
        child
            .stdin
            .take()
            .unwrap()
            .write_all(text.as_bytes())
            .unwrap();
    } else {
        drop(child.stdin.take());
    }
    child.wait_with_output().unwrap()
}

fn stdout(o: &Output) -> String {
    String::from_utf8(o.stdout.clone()).unwrap()
}

fn doc(o: &Output) -> Value {
    json::parse(&stdout(o)).unwrap_or_else(|e| panic!("{e:?}: {}", stdout(o)))
}

fn s<'a>(v: &'a Value, k: &str) -> &'a str {
    v.get(k).and_then(Value::as_str).unwrap_or_default()
}

#[test]
fn check_states_one_claim_labelled_checked_pure() {
    let file = example("valid/routing.weave");
    let out = weave(&["check", file.to_str().unwrap()], None);
    assert_eq!(out.status.code(), Some(0));
    let text = stdout(&out);
    assert!(text.starts_with("CHECKED pure "), "{text}");
    assert!(
        text.trim_end().ends_with("valid, better, select, route"),
        "{text}"
    );
    let out = weave(&["check", file.to_str().unwrap(), "--json"], None);
    let d = doc(&out);
    let claims = d.get("claims").and_then(Value::as_array).unwrap();
    assert_eq!(claims.len(), 1);
    assert_eq!(s(&claims[0], "label"), "CHECKED pure");
    assert_eq!(d.get("diagnostics"), Some(&Value::Array(Vec::new())));
    assert_eq!(
        (s(&d, "profile"), s(&d, "specification")),
        ("P0", "0.2-draft")
    );
}

#[test]
fn rejected_files_report_code_rule_and_span() {
    // AC-2 and AC-9 through the command line.
    for (file, code, rule, line, column) in [
        ("invalid/effect_call.weave", "E512", "P0-EFFECT-1", 2, 12),
        ("invalid/await_in_fn.weave", "E513", "P0-EFFECT-2", 2, 16),
        ("invalid/handle_parameter.weave", "E504", "P0-TYPE-1", 1, 15),
        ("invalid/fork.weave", "E514", "P0-FORK-1", 2, 5),
    ] {
        let path = example(file);
        let out = weave(&["check", path.to_str().unwrap(), "--json"], None);
        assert_eq!(out.status.code(), Some(1), "{file}");
        let d = doc(&out);
        assert_eq!(d.get("claims"), Some(&Value::Array(Vec::new())));
        let diag = &d.get("diagnostics").and_then(Value::as_array).unwrap()[0];
        assert_eq!(s(diag, "format"), "weave-diagnostic-v1");
        assert_eq!((s(diag, "code"), s(diag, "rule")), (code, rule), "{file}");
        let start = diag.get("span").and_then(|sp| sp.get("start")).unwrap();
        assert_eq!(
            (start.get("line"), start.get("column")),
            (
                Some(&Value::from_usize(line)),
                Some(&Value::from_usize(column))
            ),
            "{file}"
        );
        let text = stdout(&weave(&["check", path.to_str().unwrap()], None));
        assert!(
            text.contains(&format!(":{line}:{column}: {code} ({rule}) [static]")),
            "{text}"
        );
    }
}

#[test]
fn run_reports_value_fault_or_exhaustion_with_budgets() {
    let arith = example("valid/arithmetic.weave");
    let budgets = example("valid/budgets.weave");
    let a = arith.to_str().unwrap();
    let b = budgets.to_str().unwrap();
    let out = weave(&["run", a, "--entry", "power", "--args", "[2, 100]"], None);
    assert_eq!(out.status.code(), Some(0));
    let text = stdout(&out);
    assert!(
        text.contains("outcome: value\nresult: 1267650600228229401496703205376\n"),
        "{text}"
    );
    assert!(
        text.contains("budgets: fuel 101/1000000, depth 101/10000, int-bits 101/65536"),
        "{text}"
    );
    let out = weave(
        &[
            "run", a, "--entry", "quotient", "--args", "[1, 0]", "--json",
        ],
        None,
    );
    assert_eq!(out.status.code(), Some(3));
    let d = doc(&out);
    assert_eq!(
        (s(&d, "outcome"), s(&d, "fault")),
        ("fault", "division-by-zero")
    );
    assert_eq!(d.get("value"), Some(&Value::Null));
    let out = weave(
        &[
            "run", b, "--entry", "spin", "--args", "[0]", "--fuel", "1000", "--json",
        ],
        None,
    );
    assert_eq!(out.status.code(), Some(4));
    let d = doc(&out);
    assert_eq!(
        (s(&d, "outcome"), s(&d, "exhausted")),
        ("exhausted", "fuel")
    );
    let fuel = d.get("budgets").and_then(|b| b.get("fuel")).unwrap();
    assert_eq!(fuel.get("limit"), Some(&Value::from_usize(1000)));
    assert_eq!(fuel.get("used"), Some(&Value::from_usize(1000)));
    let diag = &d.get("diagnostics").and_then(Value::as_array).unwrap()[0];
    assert_eq!(
        (s(diag, "code"), s(diag, "rule"), s(diag, "stage")),
        ("E530", "P0-BUDGET-2", "runtime")
    );
    // A run carries the file's CHECKED pure claim; the run outcome itself has no label.
    assert_eq!(
        d.get("claims")
            .and_then(Value::as_array)
            .map(<[Value]>::len),
        Some(1)
    );
    assert!(d.get("label").is_none() && d.get("claim_label").is_none());
    let out = weave(
        &[
            "run",
            b,
            "--entry",
            "depth",
            "--args",
            "[100]",
            "--max-depth",
            "50",
        ],
        None,
    );
    assert_eq!(out.status.code(), Some(4));
    assert!(stdout(&out).contains("E531 (P0-BUDGET-3) [runtime]"));
    let out = weave(
        &[
            "run",
            b,
            "--entry",
            "doubling",
            "--args",
            "[100, 1]",
            "--int-bits",
            "32",
        ],
        None,
    );
    assert_eq!(out.status.code(), Some(4));
    assert!(stdout(&out).contains("E532"));
}

#[test]
fn invalid_requests_and_usage() {
    let b = example("valid/budgets.weave");
    let b = b.to_str().unwrap();
    let out = weave(&["run", b, "--entry", "nope"], None);
    assert_eq!(out.status.code(), Some(1));
    assert!(stdout(&out).contains("E540 (P0-RUN-1) [run]"));
    let out = weave(
        &["run", b, "--entry", "identity", "--args", "[\"1\"]"],
        None,
    );
    assert_eq!(out.status.code(), Some(1));
    for args in [
        &["check"][..],
        &["frobnicate", b][..],
        &["run", b][..],
        &["check", b, "--fuel", "3"][..],
        &["run", b, "--entry", "spin", "--fuel", "-1"][..],
        &["run", b, "--entry", "spin", "--args", "[1,"][..],
        &["check", "/nonexistent/file.weave"][..],
        &["check", b, b][..],
    ] {
        assert_eq!(weave(args, None).status.code(), Some(2), "{args:?}");
    }
    let out = weave(&["--version"], None);
    assert_eq!(out.status.code(), Some(0));
    assert!(stdout(&out).starts_with("weave 0.1.0"));
}

#[test]
fn standard_input_and_invalid_utf8() {
    let out = weave(&["check", "-"], Some("fn f() -> Int:\n    return 1\n"));
    assert_eq!(out.status.code(), Some(0));
    assert!(stdout(&out).starts_with("CHECKED pure <stdin>: f"));
    let mut child = Command::new(env!("CARGO_BIN_EXE_weave"))
        .args(["check", "-", "--json"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(b"fn f() -> Int:\n    return \xff\n")
        .unwrap();
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code(), Some(1));
    let d = doc(&out);
    let diag = &d.get("diagnostics").and_then(Value::as_array).unwrap()[0];
    assert_eq!(s(diag, "code"), "E500");
}
