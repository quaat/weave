// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! modules-1 (`specification/docs/chapters/names.rst`, "P0 modules"):
//! resolution from one project root, symbol identity across modules,
//! visibility, diagnostics in several files, and bounded resolution. Each
//! test writes a small project into its own directory under Cargo's
//! per-target temporary directory.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::{Path, PathBuf};
use weave_check::{Entry, Failure, FileId, Program, Ty, check, check_entry, project_root};
use weave_syntax::diagnostic::SourceMap;

/// A fresh project directory named `name` with the given files.
fn project(name: &str, files: &[(&str, &str)]) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("modules")
        .join(name);
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    for (rel, text) in files {
        let path = dir.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, text).unwrap();
    }
    dir
}

fn entry(path: &Path) -> Entry {
    Entry {
        name: path.display().to_string(),
        text: std::fs::read_to_string(path).unwrap(),
        path: Some(path.to_path_buf()),
    }
}

fn load(path: &Path, root: Option<&Path>) -> Result<Program, Failure> {
    let e = entry(path);
    let r = project_root(&e, root).unwrap();
    check_entry(e, r)
}

fn accept(path: &Path, root: Option<&Path>) -> Program {
    match load(path, root) {
        Ok(p) => p,
        Err(f) => panic!(
            "{} {} in {}",
            f.diagnostic.code,
            f.diagnostic.message,
            f.sources.name(f.diagnostic.span.file)
        ),
    }
}

/// (code, rule, file name relative to the project, spanned text) of the rejection.
fn reject(dir: &Path, path: &Path, root: Option<&Path>) -> (&'static str, String, String, String) {
    let f = match load(path, root) {
        Ok(_) => panic!("accepted: {}", path.display()),
        Err(f) => f,
    };
    let d = &f.diagnostic;
    let text = f.sources.text(d.span.file);
    let spanned = text
        .get(d.span.start..d.span.end)
        .unwrap_or("?")
        .to_string();
    let file = relative(dir, f.sources.name(d.span.file));
    (d.code, d.rule().unwrap_or_default(), file, spanned)
}

fn relative(dir: &Path, name: &str) -> String {
    Path::new(name)
        .strip_prefix(dir)
        .map_or_else(|_| name.to_string(), |p| p.display().to_string())
}

const LIB: &str = "export record Point:\n    x: Int\n    y: Int\n\nexport fn norm(p: Point) -> Int:\n    return p.x + p.y\n\nfn hidden() -> Int:\n    return 0\n";

#[test]
fn imports_resolve_from_the_entry_directory_and_check_every_module() {
    let dir = project(
        "basic",
        &[
            (
                "main.weave",
                "from geo.shapes import norm, Point as P\n\nfn f(n: Int) -> Int:\n    return norm(P(x: n, y: 1))\n",
            ),
            ("geo/shapes.weave", LIB),
        ],
    );
    let p = accept(&dir.join("main.weave"), None);
    assert_eq!(p.modules.len(), 2);
    assert_eq!(p.modules[0].name, "main");
    assert_eq!(p.modules[1].name, "geo.shapes");
    assert_eq!(p.modules[1].file, FileId(1));
    // Every function of every module is in the program, with its module's identity.
    let names: Vec<String> = p.functions.iter().map(|f| f.symbol.qualified()).collect();
    assert_eq!(names, ["geo.shapes.norm", "geo.shapes.hidden", "main.f"]);
    // The run entry is looked up in the entry module only.
    assert!(p.function("f").is_some());
    assert!(p.function("norm").is_none());
}

#[test]
fn same_named_records_from_two_modules_are_distinct_types() {
    let rec = "export record Point:\n    x: Int\n    y: Int\n";
    let dir = project(
        "distinct",
        &[
            ("a.weave", rec),
            ("b.weave", rec),
            (
                "main.weave",
                "from a import Point as A\nfrom b import Point as B\n\nfn f(p: A) -> B:\n    return p\n",
            ),
            (
                "ok.weave",
                "from a import Point as A\nfrom b import Point as B\n\nfn f(p: A) -> B:\n    return B(x: p.x, y: p.y)\n",
            ),
        ],
    );
    let f = load(&dir.join("main.weave"), None).unwrap_err();
    assert_eq!(f.diagnostic.code, "E510");
    // The message tells the two Points apart by module.
    assert!(
        f.diagnostic.message.contains("b.Point") && f.diagnostic.message.contains("a.Point"),
        "{}",
        f.diagnostic.message
    );
    let p = accept(&dir.join("ok.weave"), None);
    let records: Vec<String> = p.records.iter().map(|r| r.symbol.qualified()).collect();
    assert_eq!(records, ["a.Point", "b.Point"]);
    assert_ne!(p.records[0].symbol, p.records[1].symbol);
}

#[test]
fn aliases_of_one_record_are_one_type() {
    let dir = project(
        "aliases",
        &[
            ("a.weave", "export record Point:\n    x: Int\n    y: Int\n"),
            (
                "main.weave",
                "from a import Point as P, Point as Q\nfrom a import Point\n\nfn f(p: P) -> Q:\n    return p\n\nfn g(q: Q) -> Point:\n    return q\n",
            ),
        ],
    );
    let p = accept(&dir.join("main.weave"), None);
    assert_eq!(p.records.len(), 1);
    let f = &p.functions[0];
    assert_eq!(f.params[0].1, Ty::Record(0));
    assert_eq!(f.ret, Ty::Record(0));
}

#[test]
fn an_imported_function_uses_its_own_private_helper() {
    let dir = project(
        "private",
        &[
            (
                "lib.weave",
                "export fn api(n: Int) -> Int:\n    return helper(n)\n\nfn helper(n: Int) -> Int:\n    return n * 10\n",
            ),
            (
                "main.weave",
                "from lib import api\n\nfn helper(b: Bool) -> Bool:\n    return b\n\nfn f(n: Int) -> Int:\n    return api(n)\n",
            ),
        ],
    );
    let p = accept(&dir.join("main.weave"), None);
    let api = p.functions.iter().find(|f| f.name == "api").unwrap();
    let weave_check::typed::Terminal::Return(e) = &*api.body.end else {
        panic!("return")
    };
    let weave_check::typed::ExprK::Call(callee, _) = &e.kind else {
        panic!("call")
    };
    let callee = &p.functions[*callee];
    assert_eq!(callee.symbol.qualified(), "lib.helper");
    assert_eq!(callee.params[0].1, Ty::Int);
}

#[test]
fn a_check_error_inside_an_imported_file_keeps_its_p0_code_and_file() {
    let dir = project(
        "imported_error",
        &[
            (
                "main.weave",
                "from lib import ok\n\nfn f() -> Int:\n    return ok()\n",
            ),
            (
                "lib.weave",
                "export fn ok() -> Int:\n    return 1\n\nfn unused(flag: Bool) -> Int:\n    return flag + 1\n",
            ),
        ],
    );
    let (code, rule, file, text) = reject(&dir, &dir.join("main.weave"), None);
    assert_eq!(
        (code, rule.as_str(), file.as_str(), text.as_str()),
        ("E510", "P0-TYPE-2", "lib.weave", "flag")
    );
    let f = load(&dir.join("main.weave"), None).unwrap_err();
    assert_eq!(f.diagnostic.span.file, FileId(1));
    // The JSON diagnostic names the imported file and the line in it.
    let doc = f.diagnostic.to_json_in(&f.sources);
    let span = doc.get("span").unwrap();
    assert!(
        span.get("file")
            .and_then(|v| v.as_str())
            .unwrap()
            .ends_with("lib.weave")
    );
    let line = span.get("start").and_then(|s| s.get("line")).cloned();
    assert_eq!(line, Some(weave_syntax::json::Value::from_usize(5)));
}

#[test]
fn import_cycles_are_rejected_with_every_import_location() {
    let dir = project(
        "cycle",
        &[
            (
                "a.weave",
                "from b import fb\n\nexport fn fa() -> Int:\n    return fb()\n",
            ),
            (
                "b.weave",
                "# b\nfrom c import fc\n\nexport fn fb() -> Int:\n    return fc()\n",
            ),
            (
                "c.weave",
                "from a import fa\n\nexport fn fc() -> Int:\n    return 1\n",
            ),
        ],
    );
    let f = load(&dir.join("a.weave"), None).unwrap_err();
    let d = &f.diagnostic;
    assert_eq!((d.code, d.rule().as_deref()), ("E604", Some("MOD-CYCLE-1")));
    assert!(f.sources.name(d.span.file).ends_with("c.weave"));
    let related: Vec<(String, usize, &str)> = d
        .related
        .iter()
        .map(|r| {
            let text = f.sources.text(r.span.file);
            let line = weave_syntax::span::LineIndex::new(text)
                .position(r.span.start)
                .line;
            (
                relative(&dir, f.sources.name(r.span.file)),
                line,
                text.get(r.span.start..r.span.end).unwrap(),
            )
        })
        .collect();
    assert_eq!(
        related,
        [
            ("a.weave".to_string(), 1, "b"),
            ("b.weave".to_string(), 2, "c"),
            ("c.weave".to_string(), 1, "a"),
        ]
    );
    assert!(d.related.iter().all(|r| r.role == "import"));
    // A module importing itself is the shortest cycle.
    let dir = project(
        "self_cycle",
        &[(
            "m.weave",
            "from m import f\n\nexport fn f() -> Int:\n    return 1\n",
        )],
    );
    let f = load(&dir.join("m.weave"), None).unwrap_err();
    assert_eq!((f.diagnostic.code, f.diagnostic.related.len()), ("E604", 1));
}

#[test]
fn cross_module_recursion_and_record_cycles_are_import_cycles() {
    let dir = project(
        "indirect",
        &[
            (
                "even.weave",
                "from odd import is_odd\n\nexport fn is_even(n: Int) -> Bool:\n    return is_odd(n)\n",
            ),
            (
                "odd.weave",
                "from even import is_even\n\nexport fn is_odd(n: Int) -> Bool:\n    return is_even(n)\n",
            ),
            (
                "tree.weave",
                "from forest import Forest\n\nexport record Tree:\n    kids: Forest\n",
            ),
            (
                "forest.weave",
                "from tree import Tree\n\nexport record Forest:\n    trees: List[Tree]\n",
            ),
        ],
    );
    assert_eq!(reject(&dir, &dir.join("even.weave"), None).0, "E604");
    assert_eq!(reject(&dir, &dir.join("tree.weave"), None).0, "E604");
    // Within one module the P0 rules still apply.
    let dir = project(
        "local_recursion",
        &[
            (
                "lib.weave",
                "export fn a(n: Int) -> Int:\n    return b(n)\n\nfn b(n: Int) -> Int:\n    return a(n)\n",
            ),
            (
                "main.weave",
                "from lib import a\n\nfn f() -> Int:\n    return a(1)\n",
            ),
            ("rec.weave", "export record T:\n    kids: List[T]\n"),
            (
                "main2.weave",
                "from rec import T\n\nfn f(t: T) -> Int:\n    return 1\n",
            ),
        ],
    );
    let (code, _, file, _) = reject(&dir, &dir.join("main.weave"), None);
    assert_eq!((code, file.as_str()), ("E516", "lib.weave"));
    let (code, _, file, _) = reject(&dir, &dir.join("main2.weave"), None);
    assert_eq!((code, file.as_str()), ("E503", "rec.weave"));
}

#[test]
fn import_names_never_collide_silently() {
    let dir = project(
        "collisions",
        &[
            ("lib.weave", LIB),
            (
                "other.weave",
                "export fn norm(n: Int) -> Int:\n    return n\n",
            ),
            (
                "two.weave",
                "from lib import norm\nfrom other import norm\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "same.weave",
                "from lib import norm, norm\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "local.weave",
                "from lib import norm\n\nfn norm() -> Int:\n    return 1\n",
            ),
            (
                "builtin.weave",
                "from lib import norm as head\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "record.weave",
                "from lib import Point\n\nrecord Point:\n    z: Int\n",
            ),
            (
                "let.weave",
                "from lib import norm\n\nfn f() -> Int:\n    let norm = 1\n    return norm\n",
            ),
            (
                "param.weave",
                "from lib import Point\n\nfn f(Point: Int) -> Int:\n    return 1\n",
            ),
            (
                "renamed.weave",
                "from lib import norm as n1\nfrom other import norm as n2\n\nfn f() -> Int:\n    return n2(1)\n",
            ),
        ],
    );
    for (file, text) in [
        ("two.weave", "norm"),
        ("same.weave", "norm"),
        ("local.weave", "norm"),
        ("builtin.weave", "head"),
        ("record.weave", "Point"),
    ] {
        let (code, rule, f, t) = reject(&dir, &dir.join(file), None);
        assert_eq!(
            (code, rule.as_str(), f.as_str(), t.as_str()),
            ("E608", "MOD-NAME-1", file, text),
            "{file}"
        );
    }
    for file in ["let.weave", "param.weave"] {
        assert_eq!(reject(&dir, &dir.join(file), None).0, "E506", "{file}");
    }
    accept(&dir.join("renamed.weave"), None);
}

#[test]
fn only_exported_declarations_can_be_imported() {
    let dir = project(
        "visibility",
        &[
            ("lib.weave", LIB),
            (
                "hidden.weave",
                "from lib import hidden\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "typo.weave",
                "from lib import nrom\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "transitive.weave",
                "from mid import Point\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "mid.weave",
                "from lib import Point\n\nexport fn g(p: Point) -> Int:\n    return p.x\n",
            ),
        ],
    );
    assert_eq!(reject(&dir, &dir.join("hidden.weave"), None).0, "E607");
    assert_eq!(reject(&dir, &dir.join("typo.weave"), None).0, "E606");
    // No re-exports: an imported name is not declared by the importer.
    let (code, _, file, text) = reject(&dir, &dir.join("transitive.weave"), None);
    assert_eq!(
        (code, file.as_str(), text.as_str()),
        ("E606", "transitive.weave", "Point")
    );
}

#[test]
fn exported_declarations_expose_only_exported_records() {
    let dir = project(
        "export_rule",
        &[
            (
                "sig.weave",
                "record S:\n    v: Int\n\nexport fn f(s: S) -> Int:\n    return s.v\n",
            ),
            (
                "ret.weave",
                "record S:\n    v: Int\n\nexport fn f() -> List[List[S]]:\n    return []\n",
            ),
            (
                "field.weave",
                "record S:\n    v: Int\n\nexport record T:\n    s: S\n",
            ),
            (
                "ok.weave",
                "record S:\n    v: Int\n\nfn mk() -> S:\n    return S(v: 1)\n\nexport fn f() -> Int:\n    let s = mk()\n    return s.v\n",
            ),
            ("lib.weave", LIB),
            (
                "reexposed.weave",
                "from lib import Point\n\nexport fn f(p: Point) -> Int:\n    return p.x\n",
            ),
        ],
    );
    for (file, text) in [
        ("sig.weave", "S"),
        ("ret.weave", "List[List[S]]"),
        ("field.weave", "S"),
    ] {
        let (code, rule, _, t) = reject(&dir, &dir.join(file), None);
        assert_eq!(
            (code, rule.as_str(), t.as_str()),
            ("E609", "MOD-EXPORT-1", text),
            "{file}"
        );
    }
    accept(&dir.join("ok.weave"), None);
    accept(&dir.join("reexposed.weave"), None);
}

#[test]
fn import_syntax_faults_are_e600_and_body_faults_keep_e500() {
    let dir = project(
        "syntax",
        &[
            (
                "late.weave",
                "fn f() -> Int:\n    return 1\n\nfrom lib import g\n",
            ),
            (
                "dotdot.weave",
                "from ..lib import g\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "absolute.weave",
                "from /etc/lib import g\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "star.weave",
                "from lib import *\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "noname.weave",
                "from lib import\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "body.weave",
                "from lib import g\n\nfn f(x: Int) -> Bool:\n    return 0 < x < 3\n",
            ),
            ("exportlet.weave", "export let x = 1\n"),
        ],
    );
    for file in [
        "late.weave",
        "dotdot.weave",
        "absolute.weave",
        "star.weave",
        "noname.weave",
    ] {
        let (code, rule, _, _) = reject(&dir, &dir.join(file), None);
        assert_eq!((code, rule.as_str()), ("E600", "MOD-FILE-1"), "{file}");
    }
    for file in ["body.weave", "exportlet.weave"] {
        let (code, rule, _, _) = reject(&dir, &dir.join(file), None);
        assert_eq!((code, rule.as_str()), ("E500", "P0-FILE-1"), "{file}");
    }
}

#[test]
fn a_pure_file_without_module_syntax_is_read_exactly_as_p0() {
    // No top-level from/export line: the pure-file grammar, P0's own message.
    let src = "fn f(x: Int) -> Bool:\n    return 0 < x < 3\n";
    let d = check(src).unwrap_err();
    assert_eq!(d.code, "E500");
    assert!(!d.message.contains("'export'"), "{}", d.message);
    // Contextual words stay usable as names.
    let p = check(
        "record from:\n    import: Int\n\nfn export(as: from) -> Int:\n    let use = as.import\n    return use\n",
    )
    .unwrap();
    assert_eq!(p.functions[0].name, "export");
    // A pure file given as text has no project root: an import is E605.
    let d = check("from lib import g\n\nfn f() -> Int:\n    return 1\n").unwrap_err();
    assert_eq!((d.code, d.rule().as_deref()), ("E605", Some("MOD-ROOT-1")));
}

#[test]
fn module_paths_name_files_exactly_and_stay_in_the_root() {
    let dir = project(
        "resolution",
        &[
            (
                "Geo/shapes.weave",
                "export fn area() -> Int:\n    return 1\n",
            ),
            ("lib/Math.weave", "export fn sq() -> Int:\n    return 1\n"),
            (
                "pkg/sub.weave/x.weave",
                "export fn x() -> Int:\n    return 1\n",
            ),
            (
                "case_dir.weave",
                "from geo.shapes import area\n\nfn f() -> Int:\n    return area()\n",
            ),
            (
                "case_file.weave",
                "from lib.math import sq\n\nfn f() -> Int:\n    return sq()\n",
            ),
            (
                "missing.weave",
                "from nowhere.shapes import area\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "dir_not_file.weave",
                "from pkg.sub import x\n\nfn f() -> Int:\n    return 1\n",
            ),
            (
                "package_dir.weave",
                "from pkg import x\n\nfn f() -> Int:\n    return 1\n",
            ),
        ],
    );
    assert_eq!(reject(&dir, &dir.join("case_dir.weave"), None).0, "E602");
    assert_eq!(reject(&dir, &dir.join("case_file.weave"), None).0, "E602");
    let (code, rule, file, text) = reject(&dir, &dir.join("missing.weave"), None);
    assert_eq!(
        (code, rule.as_str(), file.as_str(), text.as_str()),
        ("E601", "MOD-RESOLVE-1", "missing.weave", "nowhere.shapes")
    );
    assert_eq!(
        reject(&dir, &dir.join("dir_not_file.weave"), None).0,
        "E601"
    );
    assert_eq!(reject(&dir, &dir.join("package_dir.weave"), None).0, "E601");
}

#[cfg(unix)]
#[test]
fn symbolic_links_may_not_leave_the_root_and_one_file_is_one_module() {
    use std::os::unix::fs::symlink;
    let outside = project(
        "outside",
        &[("secret.weave", "export fn s() -> Int:\n    return 1\n")],
    );
    let dir = project(
        "links",
        &[
            (
                "geo/shapes.weave",
                "export record P:\n    x: Int\n\nexport fn mk() -> P:\n    return P(x: 1)\n",
            ),
            (
                "escape_file.weave",
                "from evil import s\n\nfn f() -> Int:\n    return s()\n",
            ),
            (
                "escape_dir.weave",
                "from away.secret import s\n\nfn f() -> Int:\n    return s()\n",
            ),
            (
                "twice.weave",
                "from geo.shapes import P, mk\nfrom alias import P as Q\n\nfn f() -> Q:\n    let p = mk()\n    return p\n",
            ),
        ],
    );
    symlink(outside.join("secret.weave"), dir.join("evil.weave")).unwrap();
    symlink(&outside, dir.join("away")).unwrap();
    symlink(dir.join("geo/shapes.weave"), dir.join("alias.weave")).unwrap();
    let (code, rule, _, text) = reject(&dir, &dir.join("escape_file.weave"), None);
    assert_eq!(
        (code, rule.as_str(), text.as_str()),
        ("E603", "MOD-RESOLVE-3", "evil")
    );
    assert_eq!(reject(&dir, &dir.join("escape_dir.weave"), None).0, "E603");
    // Two routes to one canonical file load one module: P and Q are one type.
    let p = accept(&dir.join("twice.weave"), None);
    assert_eq!(p.modules.len(), 2);
    assert_eq!(p.modules[1].name, "geo.shapes");
    assert_eq!(p.records.len(), 1);
    // A root given through a symbolic link is canonicalised the same way.
    let link_root = Path::new(env!("CARGO_TARGET_TMPDIR")).join("modules/links_root");
    let _ = std::fs::remove_file(&link_root);
    symlink(&dir, &link_root).unwrap();
    accept(&link_root.join("twice.weave"), Some(&link_root));
}

#[test]
fn an_explicit_root_overrides_the_entry_directory() {
    let dir = project(
        "rooted",
        &[
            (
                "app/main.weave",
                "from lib.math import sq\n\nfn f() -> Int:\n    return sq()\n",
            ),
            ("lib/math.weave", "export fn sq() -> Int:\n    return 4\n"),
            ("other/x.weave", "fn x() -> Int:\n    return 1\n"),
        ],
    );
    assert_eq!(reject(&dir, &dir.join("app/main.weave"), None).0, "E601");
    let p = accept(&dir.join("app/main.weave"), Some(&dir));
    assert_eq!(p.modules[0].name, "app.main");
    // An entry outside the given root is rejected.
    let (code, rule, _, _) = reject(&dir, &dir.join("app/main.weave"), Some(&dir.join("other")));
    assert_eq!((code, rule.as_str()), ("E605", "MOD-ROOT-1"));
    // A root that is not a directory is a usage error, not a diagnostic.
    let e = entry(&dir.join("app/main.weave"));
    assert!(project_root(&e, Some(&dir.join("lib/math.weave"))).is_err());
    assert!(project_root(&e, Some(&dir.join("nowhere"))).is_err());
}

#[test]
fn a_diamond_loads_the_shared_module_once() {
    let dir = project(
        "diamond",
        &[
            (
                "base.weave",
                "export record R:\n    v: Int\n\nexport fn mk() -> R:\n    return R(v: 1)\n",
            ),
            (
                "left.weave",
                "from base import R, mk\n\nexport fn l() -> R:\n    return mk()\n",
            ),
            (
                "right.weave",
                "from base import R\n\nexport fn r(x: R) -> Int:\n    return x.v\n",
            ),
            (
                "main.weave",
                "from left import l\nfrom right import r\n\nfn f() -> Int:\n    return r(l())\n",
            ),
        ],
    );
    let p = accept(&dir.join("main.weave"), None);
    let names: Vec<&str> = p.modules.iter().map(|m| m.name.as_str()).collect();
    assert_eq!(names, ["main", "left", "base", "right"]);
    assert_eq!(p.records.len(), 1);
}

/// A chain of `n` modules, each importing the next: resolution and checking
/// are iterative, so the length is bounded by memory, not by the stack.
#[test]
fn a_chain_of_ten_thousand_modules_checks_without_overflow() {
    let n = 10_000;
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join("modules/chain");
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    for i in 0..n {
        let text = if i + 1 < n {
            format!(
                "from m{next} import f{next}\n\nexport fn f{i}(x: Int) -> Int:\n    return f{next}(x) + 1\n",
                next = i + 1
            )
        } else {
            format!("export fn f{i}(x: Int) -> Int:\n    return x\n")
        };
        std::fs::write(dir.join(format!("m{i}.weave")), text).unwrap();
    }
    let p = accept(&dir.join("m0.weave"), None);
    assert_eq!(p.modules.len(), n);
    assert_eq!(p.functions.len(), n);
    // Closing the chain into a cycle is found without overflow too.
    std::fs::write(
        dir.join(format!("m{}.weave", n - 1)),
        format!(
            "from m0 import f0\n\nexport fn f{}(x: Int) -> Int:\n    return x\n",
            n - 1
        ),
    )
    .unwrap();
    let f = load(&dir.join("m0.weave"), None).unwrap_err();
    assert_eq!((f.diagnostic.code, f.diagnostic.related.len()), ("E604", n));
}

/// MOD-ROOT-1: without `--root`, the root is the directory of the entry path
/// as written, so a symbolic link's own directory counts and the entry is
/// never outside it; only an explicit root can exclude the entry (E605).
#[cfg(unix)]
#[test]
fn a_symlinked_entry_uses_the_directory_of_its_link() {
    use std::os::unix::fs::symlink;
    const PURE: &str =
        "record R:\n    v: Int\n\nfn f(n: Int) -> Int:\n    let r = R(v: n)\n    return r.v\n";
    let target = project(
        "link_target",
        &[
            ("real.weave", PURE),
            (
                "importing.weave",
                "from lib import g\n\nfn f(n: Int) -> Int:\n    return g(n)\n",
            ),
            // Next to the target, not the link: never used.
            (
                "lib.weave",
                "export fn g(n: Int) -> Int:\n    return true\n",
            ),
        ],
    );
    let dir = project(
        "link_dir",
        &[(
            "lib.weave",
            "export fn g(n: Int) -> Int:\n    return n + 1\n",
        )],
    );
    symlink(target.join("real.weave"), dir.join("main.weave")).unwrap();
    symlink(target.join("importing.weave"), dir.join("app.weave")).unwrap();

    // No imports: exactly the program of the target file checked directly,
    // except that the module is named by the link, its path as written.
    let linked = accept(&dir.join("main.weave"), None);
    let direct = accept(&target.join("real.weave"), None);
    let renamed = |p: &Program| {
        let mut p = p.clone();
        for f in &mut p.functions {
            f.symbol.module = "-".into();
        }
        for r in &mut p.records {
            r.symbol.module = "-".into();
        }
        (p.functions, p.records)
    };
    assert_eq!(renamed(&linked), renamed(&direct));
    assert_eq!(linked.modules.len(), 1);
    assert_eq!(linked.modules[0].name, "main");

    // With imports: `lib` resolves from the link's directory, not the target's.
    let p = accept(&dir.join("app.weave"), None);
    assert_eq!(p.modules[0].name, "app");
    let lib = p.sources.get(FileId(1)).unwrap();
    assert!(Path::new(&lib.name).starts_with(&dir), "{}", lib.name);
    let g = p.functions.iter().find(|f| f.name == "g").unwrap();
    assert_eq!(g.ret, Ty::Int);

    // An explicit root that does not contain the link's target still excludes it.
    let (code, rule, _, _) = reject(&dir, &dir.join("main.weave"), Some(&dir));
    assert_eq!((code, rule.as_str()), ("E605", "MOD-ROOT-1"));
    // An explicit root that contains the target accepts it.
    accept(&dir.join("main.weave"), Some(&target));
}

/// MOD-RESOLVE-4: identity is the canonical path, so two hard links to one
/// file are two modules, and their records are two types.
#[cfg(unix)]
#[test]
fn hard_links_to_one_file_are_two_modules() {
    let dir = project(
        "hard_links",
        &[
            ("a.weave", "export record P:\n    x: Int\n"),
            (
                "main.weave",
                "from a import P as A\nfrom b import P as B\n\nfn f(p: A) -> Int:\n    return p.x\n",
            ),
            (
                "mixed.weave",
                "from a import P as A\nfrom b import P as B\n\nfn f(p: A) -> B:\n    return p\n",
            ),
        ],
    );
    std::fs::hard_link(dir.join("a.weave"), dir.join("b.weave")).unwrap();
    let p = accept(&dir.join("main.weave"), None);
    let modules: Vec<&str> = p.modules.iter().map(|m| m.name.as_str()).collect();
    assert_eq!(modules, ["main", "a", "b"]);
    assert_eq!(p.records.len(), 2);
    assert_eq!(reject(&dir, &dir.join("mixed.weave"), None).0, "E510");
}
