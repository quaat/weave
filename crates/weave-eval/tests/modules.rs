// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Evaluation across modules (modules-1, `MOD-RUN-1`): an imported function
//! runs with its own module's helpers, and a fault inside it is located in its
//! own file.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::{Path, PathBuf};
use weave_check::{Entry, FileId, Program, check_entry, project_root};
use weave_eval::{DEFAULT_BUDGETS, Fault, Outcome, outcome_diagnostic, run};
use weave_syntax::diagnostic::SourceMap;
use weave_syntax::json::{self, Value};
use weave_syntax::span::LineIndex;

fn project(name: &str, files: &[(&str, &str)]) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("eval-modules")
        .join(name);
    let _ = std::fs::remove_dir_all(&dir);
    for (rel, text) in files {
        let path = dir.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, text).unwrap();
    }
    dir
}

fn program(path: &Path) -> Program {
    let entry = Entry {
        name: path.display().to_string(),
        text: std::fs::read_to_string(path).unwrap(),
        path: Some(path.to_path_buf()),
    };
    let root = project_root(&entry, None).unwrap();
    check_entry(entry, root).unwrap_or_else(|f| panic!("{}", f.diagnostic.message))
}

const LIB: &str = "export fn ratio(a: Int, b: Int) -> Int:\n    return helper(a) + div(a, b)\n\nfn helper(a: Int) -> Int:\n    return a * 100\n";
const MAIN: &str = "from lib.arith import ratio\n\nfn helper(a: Int) -> Int:\n    return 0 - a\n\nfn main(a: Int, b: Int) -> Int:\n    return ratio(a, b) + helper(1)\n";

#[test]
fn an_imported_function_runs_with_its_own_helpers() {
    let dir = project("value", &[("lib/arith.weave", LIB), ("main.weave", MAIN)]);
    let p = program(&dir.join("main.weave"));
    let args = json::parse("[3, 2]").unwrap();
    let r = run(&p, "main", &args, DEFAULT_BUDGETS).unwrap();
    // lib.helper(3) = 300, div(3, 2) = 1, main.helper(1) = -1.
    let Outcome::Value(v) = &r.outcome else {
        panic!("{:?}", r.outcome)
    };
    assert_eq!(
        weave_eval::value::to_json(v, &p),
        Value::Number("300".into())
    );
}

#[test]
fn a_fault_inside_an_imported_function_is_located_in_its_file() {
    let dir = project("fault", &[("lib/arith.weave", LIB), ("main.weave", MAIN)]);
    let p = program(&dir.join("main.weave"));
    let args = json::parse("[3, 0]").unwrap();
    let r = run(&p, "main", &args, DEFAULT_BUDGETS).unwrap();
    let Outcome::Fault(Fault::DivisionByZero, span) = r.outcome else {
        panic!("{:?}", r.outcome)
    };
    assert_eq!(span.file, FileId(1));
    let text = p.sources.text(span.file);
    assert_eq!(text.get(span.start..span.end), Some("div(a, b)"));
    assert_eq!(LineIndex::new(text).position(span.start).line, 2);
    let d = outcome_diagnostic(&r).unwrap();
    let doc = d.to_json_in(&p.sources);
    let file = doc
        .get("span")
        .and_then(|s| s.get("file"))
        .and_then(Value::as_str)
        .unwrap();
    assert!(file.ends_with("lib/arith.weave"), "{file}");
    assert_eq!(doc.get("code").and_then(Value::as_str), Some("E520"));
}

#[test]
fn the_entry_is_a_function_of_the_entry_module() {
    let dir = project("entry", &[("lib/arith.weave", LIB), ("main.weave", MAIN)]);
    let p = program(&dir.join("main.weave"));
    let args = json::parse("[1, 1]").unwrap();
    let e = run(&p, "ratio", &args, DEFAULT_BUDGETS).unwrap_err();
    let weave_eval::RunError::Request(d) = e else {
        panic!("{e:?}")
    };
    assert_eq!(d.code, "E540");
}
