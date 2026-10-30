// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The `weave` command with modules-1: `--root`, independence from the working
//! directory, diagnostics in several files, and the modules corpus
//! (`specification/examples/modules/manifest.json`).

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use weave_syntax::json::{self, Value};

fn examples() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../specification/examples")
        .canonicalize()
        .unwrap()
}

fn weave_in(dir: &Path, args: &[&str], stdin: Option<&str>) -> Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_weave"))
        .args(args)
        .current_dir(dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    if let Some(text) = stdin {
        input.write_all(text.as_bytes()).unwrap();
    }
    drop(input);
    child.wait_with_output().unwrap()
}

fn doc(o: &Output) -> Value {
    let text = String::from_utf8(o.stdout.clone()).unwrap();
    json::parse(&text).unwrap_or_else(|e| panic!("{e:?}: {text}"))
}

fn project(name: &str, files: &[(&str, &str)]) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("cli-modules")
        .join(name);
    let _ = std::fs::remove_dir_all(&dir);
    for (rel, text) in files {
        let path = dir.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, text).unwrap();
    }
    dir.canonicalize().unwrap()
}

fn first_diagnostic(d: &Value) -> &Value {
    d.get("diagnostics")
        .and_then(Value::as_array)
        .and_then(|a| a.first())
        .unwrap_or_else(|| panic!("no diagnostic: {}", d.to_json()))
}

fn str_of<'a>(v: &'a Value, path: &[&str]) -> &'a str {
    let mut v = v;
    for k in path {
        v = v.get(k).unwrap_or_else(|| panic!("no {k}"));
    }
    v.as_str().unwrap_or_default()
}

fn line_of(v: &Value) -> usize {
    match v
        .get("span")
        .and_then(|s| s.get("start"))
        .and_then(|s| s.get("line"))
    {
        Some(Value::Number(n)) => n.parse().unwrap(),
        other => panic!("{other:?}"),
    }
}

const MAIN: &str = "from geo.shapes import area\n\nfn f(n: Int) -> Int:\n    return area(n)\n";
const SHAPES: &str = "export fn area(n: Int) -> Int:\n    return n * n\n";
/// A module that a working-directory-relative resolver would wrongly find.
const DECOY: &str = "export fn area(n: Int) -> Bool:\n    return true\n";

#[test]
fn results_do_not_depend_on_the_working_directory() {
    let dir = project(
        "cwd",
        &[
            ("proj/main.weave", MAIN),
            ("proj/geo/shapes.weave", SHAPES),
            ("elsewhere/geo/shapes.weave", DECOY),
        ],
    );
    let main = dir.join("proj/main.weave");
    let main = main.to_str().unwrap();
    let a = weave_in(
        &dir.join("proj"),
        &["run", main, "--entry", "f", "--args", "[7]", "--json"],
        None,
    );
    let b = weave_in(
        &dir.join("elsewhere"),
        &["run", main, "--entry", "f", "--args", "[7]", "--json"],
        None,
    );
    let c = weave_in(
        Path::new("/"),
        &["run", main, "--entry", "f", "--args", "[7]", "--json"],
        None,
    );
    assert_eq!(
        a.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&a.stderr)
    );
    assert_eq!(a.stdout, b.stdout);
    assert_eq!(a.stdout, c.stdout);
    assert_eq!(doc(&a).get("value"), Some(&Value::Number("49".into())));
    // Relative paths from two directories: the same claims, modules and value.
    let d = weave_in(&dir.join("proj"), &["check", "main.weave", "--json"], None);
    let e = weave_in(
        &dir.join("elsewhere"),
        &["check", "../proj/main.weave", "--root", "../proj", "--json"],
        None,
    );
    let modules = |o: &Output| -> Vec<String> {
        doc(o)
            .get("claims")
            .and_then(Value::as_array)
            .unwrap()
            .iter()
            .map(|c| str_of(c, &["module"]).to_string())
            .collect()
    };
    assert_eq!(d.status.code(), Some(0));
    assert_eq!(e.status.code(), Some(0));
    assert_eq!(modules(&d), ["main", "geo.shapes"]);
    assert_eq!(modules(&d), modules(&e));
}

#[test]
fn diagnostics_name_the_file_they_are_in() {
    let dir = project(
        "files",
        &[
            (
                "main.weave",
                "from lib import ok, ratio\n\nfn f(a: Int) -> Int:\n    return ratio(a, 0) + ok()\n",
            ),
            (
                "lib.weave",
                "export fn ok() -> Int:\n    return 1\n\nexport fn ratio(a: Int, b: Int) -> Int:\n    return mod(a, b)\n",
            ),
            (
                "bad.weave",
                "from badlib import ok\n\nfn f() -> Int:\n    return ok()\n",
            ),
            ("badlib.weave", "export fn ok() -> Int:\n    return true\n"),
        ],
    );
    let main = dir.join("main.weave");
    let out = weave_in(
        &dir,
        &[
            "run",
            main.to_str().unwrap(),
            "--entry",
            "f",
            "--args",
            "[5]",
            "--json",
        ],
        None,
    );
    assert_eq!(out.status.code(), Some(3));
    let d = doc(&out);
    let diag = first_diagnostic(&d);
    assert_eq!(str_of(diag, &["code"]), "E520");
    assert!(str_of(diag, &["span", "file"]).ends_with("lib.weave"));
    assert_eq!(line_of(diag), 5);
    // Text output: FILE:line:col of the imported file.
    let out = weave_in(
        &dir,
        &["run", "main.weave", "--entry", "f", "--args", "[5]"],
        None,
    );
    let text = String::from_utf8(out.stdout).unwrap();
    assert!(text.contains("lib.weave:5:12: E520 (P0-ARITH-2)"), "{text}");
    // A check error in an imported file keeps its P0 code.
    let out = weave_in(&dir, &["check", "bad.weave", "--json"], None);
    assert_eq!(out.status.code(), Some(1));
    let d = doc(&out);
    let diag = first_diagnostic(&d);
    assert_eq!(
        (str_of(diag, &["code"]), str_of(diag, &["rule"])),
        ("E510", "P0-TYPE-2")
    );
    assert_eq!(str_of(diag, &["span", "file"]), "./badlib.weave");
    assert_eq!(d.get("claims"), Some(&Value::Array(Vec::new())));
}

#[test]
fn standard_input_resolves_imports_only_with_a_root() {
    let dir = project("stdin", &[("geo/shapes.weave", SHAPES)]);
    let out = weave_in(&dir, &["check", "-", "--json"], Some(MAIN));
    assert_eq!(out.status.code(), Some(1));
    assert_eq!(str_of(first_diagnostic(&doc(&out)), &["code"]), "E605");
    let root = dir.to_str().unwrap();
    let out = weave_in(
        Path::new("/"),
        &["check", "-", "--root", root, "--json"],
        Some(MAIN),
    );
    assert_eq!(
        out.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&out.stdout)
    );
    // A P0 file without imports reads from standard input exactly as before.
    let out = weave_in(
        &dir,
        &["run", "-", "--entry", "f", "--args", "[2]"],
        Some(SHAPES.replace("export ", "").replace("area", "f").as_str()),
    );
    assert_eq!(out.status.code(), Some(0));
}

#[test]
fn root_usage_errors_exit_2() {
    let dir = project(
        "usage",
        &[("main.weave", MAIN), ("geo/shapes.weave", SHAPES)],
    );
    let main = dir.join("main.weave");
    let main = main.to_str().unwrap();
    for args in [
        vec!["check", main, "--root"],
        vec!["check", main, "--root", "/no/such/dir"],
        vec!["check", main, "--root", main],
        vec!["check", main, "--root", ".", "--root", "."],
    ] {
        assert_eq!(
            weave_in(&dir, &args, None).status.code(),
            Some(2),
            "{args:?}"
        );
    }
}

#[test]
fn an_import_cycle_lists_every_import() {
    let dir = project(
        "cycle",
        &[
            (
                "a.weave",
                "from b import g\n\nexport fn f() -> Int:\n    return g()\n",
            ),
            (
                "b.weave",
                "from a import f\n\nexport fn g() -> Int:\n    return 1\n",
            ),
        ],
    );
    let out = weave_in(&dir, &["check", "a.weave", "--json"], None);
    assert_eq!(out.status.code(), Some(1));
    let d = doc(&out);
    let diag = first_diagnostic(&d);
    assert_eq!(
        (str_of(diag, &["code"]), str_of(diag, &["rule"])),
        ("E604", "MOD-CYCLE-1")
    );
    let related = diag.get("related").and_then(Value::as_array).unwrap();
    let files: Vec<&str> = related
        .iter()
        .map(|r| str_of(r, &["span", "file"]))
        .collect();
    assert_eq!(files, ["a.weave", "./b.weave"]);
    assert!(related.iter().all(|r| str_of(r, &["role"]) == "import"));
    let out = weave_in(&dir, &["check", "a.weave"], None);
    let text = String::from_utf8(out.stdout).unwrap();
    assert!(
        text.contains("  a.weave:1:6: import: 'a' imports 'b'"),
        "{text}"
    );
}

/// Every check and run case of the modules corpus, through the binary.
#[test]
fn the_modules_corpus() {
    let ex = examples();
    let manifest =
        json::parse(&std::fs::read_to_string(ex.join("modules/manifest.json")).unwrap()).unwrap();
    assert_eq!(
        str_of(&manifest, &["format"]),
        "weave-modules-conformance-v1"
    );
    let mut seen = 0;
    for case in manifest.get("cases").and_then(Value::as_array).unwrap() {
        let kind = str_of(case, &["kind"]);
        if kind == "flow" {
            continue;
        }
        let id = str_of(case, &["id"]);
        let entry = ex.join(str_of(case, &["entry"]));
        let mut args = vec![
            kind.to_string(),
            entry.display().to_string(),
            "--json".into(),
        ];
        if let Some(root) = case.get("root").and_then(Value::as_str) {
            args.push("--root".into());
            args.push(ex.join(root).display().to_string());
        }
        if kind == "run" {
            args.push("--entry".into());
            args.push(str_of(case, &["function"]).to_string());
            args.push("--args".into());
            args.push(case.get("args").unwrap().to_json());
        }
        let argv: Vec<&str> = args.iter().map(String::as_str).collect();
        let out = weave_in(&ex, &argv, None);
        let d = doc(&out);
        let expect = str_of(case, &["expect"]);
        let diags = d.get("diagnostics").and_then(Value::as_array).unwrap();
        let actual = match diags.first() {
            Some(diag) => str_of(diag, &["code"]).to_string(),
            None if kind == "run" => "VALUE".into(),
            None => "ACCEPT".into(),
        };
        assert_eq!(actual, expect, "{id}");
        if expect == "VALUE" {
            assert_eq!(d.get("value"), case.get("value"), "{id}");
        }
        if let Some(file) = case.get("file").and_then(Value::as_str) {
            let diag = diags.first().unwrap();
            let named = PathBuf::from(str_of(diag, &["span", "file"]))
                .canonicalize()
                .unwrap();
            assert_eq!(named, ex.join(file).canonicalize().unwrap(), "{id}");
            assert_eq!(
                Value::from_usize(line_of(diag)),
                *case.get("line").unwrap(),
                "{id}"
            );
        }
        if let Some(related) = case.get("related").and_then(Value::as_array) {
            let got = diags
                .first()
                .unwrap()
                .get("related")
                .and_then(Value::as_array)
                .unwrap();
            assert_eq!(got.len(), related.len(), "{id}");
            for (g, want) in got.iter().zip(related) {
                let want = want.as_array().unwrap();
                let named = PathBuf::from(str_of(g, &["span", "file"]))
                    .canonicalize()
                    .unwrap();
                assert_eq!(
                    named,
                    ex.join(want[0].as_str().unwrap()).canonicalize().unwrap(),
                    "{id}"
                );
                assert_eq!(Value::from_usize(line_of(g)), want[1], "{id}");
            }
        }
        seen += 1;
    }
    assert!(seen >= 30, "{seen}");
}
