// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The conformance applications (quaat/weave#11) through the ordinary `weave`
//! command, exactly as the specification's tooling chapter writes them.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::Path;
use std::process::{Command, Output};
use weave_syntax::json::{self, Value};

fn weave(args: &[&str]) -> Output {
    // From the repository root, as documented.
    Command::new(env!("CARGO_BIN_EXE_weave"))
        .current_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
        .args(args)
        .output()
        .unwrap()
}

fn text(o: &Output) -> String {
    String::from_utf8(o.stdout.clone()).unwrap()
}

fn doc(o: &Output) -> Value {
    json::parse(&text(o)).unwrap_or_else(|e| panic!("{e:?}: {}", text(o)))
}

const MERGE_SORT: &str = "specification/examples/pure/valid/merge_sort.weave";
const ROUTING: &str = "specification/examples/pure/valid/routing.weave";

#[test]
fn both_programs_run_as_documented() {
    let out = weave(&[
        "run",
        MERGE_SORT,
        "--entry",
        "merge_sort",
        "--args",
        "[[5, -2, 5, 0, -2]]",
    ]);
    assert_eq!(out.status.code(), Some(0));
    assert!(
        text(&out).contains("result: [-2,-2,0,5,5]\n"),
        "{}",
        text(&out)
    );
    let out = weave(&[
        "run",
        MERGE_SORT,
        "--entry",
        "sort_items",
        "--args",
        r#"[[{"key": 2, "id": 1}, {"key": 1, "id": 2}, {"key": 2, "id": 3}]]"#,
    ]);
    assert_eq!(out.status.code(), Some(0));
    assert!(
        text(&out).contains(r#"result: [{"key":1,"id":2},{"key":2,"id":1},{"key":2,"id":3}]"#),
        "{}",
        text(&out)
    );
    let out = weave(&[
        "run",
        ROUTING,
        "--entry",
        "route",
        "--args",
        r#"[[{"dest": 1, "cost": 5, "hops": 2}, {"dest": 3, "cost": 3, "hops": 17}], 10]"#,
    ]);
    assert_eq!(out.status.code(), Some(0));
    assert!(
        text(&out).contains(r#"result: {"accepted":true,"dest":1,"cost":5}"#),
        "{}",
        text(&out)
    );
    let out = weave(&[
        "run",
        ROUTING,
        "--entry",
        "route",
        "--args",
        r#"[[{"dest": 1, "cost": 2}], 10]"#,
    ]);
    assert_eq!(out.status.code(), Some(1));
    assert!(
        text(&out).contains("E540 (P0-RUN-1) [run]"),
        "{}",
        text(&out)
    );
    assert!(!text(&out).contains("budgets"), "{}", text(&out));
}

#[test]
fn malformed_route_records_are_invalid_run_requests() {
    for args in [
        r#"[[{"dest": 1, "cost": 2}], 10]"#,
        r#"[[{"dest": 1, "cost": 2, "hops": 1, "via": 3}], 10]"#,
        r#"[[{"dest": 1, "cost": "2", "hops": 1}], 10]"#,
    ] {
        let out = weave(&["run", ROUTING, "--entry", "route", "--args", args, "--json"]);
        assert_eq!(out.status.code(), Some(1), "{args}");
        let d = doc(&out);
        assert!(matches!(d.get("outcome"), Some(Value::Null)), "{args}");
        assert!(d.get("budgets").is_none(), "{args}: no budget is used");
        let first = match d.get("diagnostics") {
            Some(Value::Array(ds)) => ds[0].clone(),
            other => panic!("{other:?}"),
        };
        assert_eq!(first.get("code").and_then(Value::as_str), Some("E540"));
        assert_eq!(first.get("stage").and_then(Value::as_str), Some("run"));
    }
    // The same record with every field, once, is a value.
    let out = weave(&[
        "run",
        ROUTING,
        "--entry",
        "route",
        "--args",
        r#"[[{"dest": 1, "cost": 2, "hops": 1}], 10]"#,
    ]);
    assert_eq!(out.status.code(), Some(0));
}
