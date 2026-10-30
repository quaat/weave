// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The shared conformance corpus (`specification/examples/`), read in place.
//!
//! Every `.weave` file is parsed with the start symbol its manifest kind or
//! directory selects (`pure/` holds P0 pure files, start symbol `pure-file`); net-append mutations are attached to the manifest's net
//! as `scripts/grammar_audit.py` does. Syntactically valid files must round
//! trip and satisfy the span invariants; syntactically invalid files must give
//! the reference checker's code with a rule ID and a span.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use weave_syntax::json::{self, Value};
use weave_syntax::{Cst, Element, Node, Start, parse};

fn examples() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../specification/examples")
}

fn read(rel: &str) -> String {
    std::fs::read_to_string(examples().join(rel)).unwrap_or_else(|e| panic!("{rel}: {e}"))
}

/// Coloured (N1) nets of the corpus; other nets are N0.
const N1_NETS: [&str; 2] = [
    "nets/Inventory.coloured.weave",
    "nets/cross_order_read.weave",
];

/// Corpus files the grammar rejects, with the code the reference checker (F0)
/// or the P0 manifest (`pure/manifest.json`) requires.
const SYNTAX_INVALID: [(&str, &str); 4] = [
    ("invalid/unsupported_if.weave", "E200"),
    ("invalid/skipped_level.weave", "E001"),
    ("pure/invalid/chained_comparison.weave", "E500"),
    ("pure/invalid/flow_in_pure_file.weave", "E500"),
];

struct Case {
    file: String,
    start: Start,
    source: String,
}

fn manifest() -> Value {
    json::parse(&read("manifest.json")).expect("manifest.json is JSON")
}

fn all_weave_files(dir: &Path, rel: &str, out: &mut Vec<String>) {
    for entry in std::fs::read_dir(dir).unwrap() {
        let entry = entry.unwrap();
        let name = entry.file_name().into_string().unwrap();
        let rel = if rel.is_empty() {
            name.clone()
        } else {
            format!("{rel}/{name}")
        };
        if entry.file_type().unwrap().is_dir() {
            all_weave_files(&entry.path(), &rel, out);
        } else if name.ends_with(".weave") {
            out.push(rel);
        }
    }
}

/// Every `.weave` file of the corpus with its start symbol and the text to parse.
fn cases() -> Vec<Case> {
    let m = manifest();
    let base = m.get("net").and_then(Value::as_str).unwrap().to_string();
    let base_source = read(&base);
    let mut kinds: BTreeMap<String, String> = BTreeMap::new();
    for case in m.get("cases").and_then(Value::as_array).unwrap() {
        let file = case.get("file").and_then(Value::as_str).unwrap();
        let kind = case.get("kind").and_then(Value::as_str).unwrap();
        kinds.insert(file.to_string(), kind.to_string());
    }
    let mut files = Vec::new();
    all_weave_files(&examples(), "", &mut files);
    files.sort();
    files
        .into_iter()
        .map(|file| {
            let dir = file.split('/').next().unwrap_or_default();
            let kind = kinds.get(&file).cloned().unwrap_or_else(|| {
                match dir {
                    "valid" | "invalid" => "flow",
                    "pure" => "pure",
                    "mutations" => "net_append",
                    "nets" if N1_NETS.contains(&file.as_str()) => "n1",
                    "nets" => "net",
                    other => panic!("{file}: no start symbol for directory {other}"),
                }
                .to_string()
            });
            let source = read(&file);
            let (start, source) = match kind.as_str() {
                "flow" => (Start::FlowFile, source),
                "net" if N1_NETS.contains(&file.as_str()) => (Start::N1File, source),
                "net" => (Start::N0File, source),
                "n1" => (Start::N1File, source),
                "pure" => (Start::PureFile, source),
                "net_append" => (
                    Start::N0File,
                    format!("{}\n\n{}", base_source.trim_end(), source),
                ),
                other => panic!("{file}: unknown manifest kind {other}"),
            };
            Case {
                file,
                start,
                source,
            }
        })
        .collect()
}

/// Spans lie inside the source; every node's children are ordered, nested in
/// it, and start and end where it does; token trivia precede their token.
fn check_spans(cst: &Cst) {
    let len = cst.source.len();
    let mut previous_end = 0;
    for token in &cst.tokens {
        assert!(token.span.start <= token.span.end && token.span.end <= len);
        let mut at = token.full_start();
        assert!(at >= previous_end, "token overlaps its predecessor");
        for trivia in &token.trivia {
            assert_eq!(trivia.span.start, at, "trivia are contiguous");
            at = trivia.span.end;
        }
        assert_eq!(at, token.span.start, "trivia end where the token starts");
        assert!(
            cst.source.is_char_boundary(token.span.start)
                && cst.source.is_char_boundary(token.span.end)
        );
        previous_end = token.span.end;
    }
    assert_eq!(previous_end, len, "the EOF token ends the source");
    fn walk(cst: &Cst, node: &Node) {
        assert!(!node.kind.is_empty());
        assert!(node.span.start <= node.span.end && node.span.end <= cst.source.len());
        assert!(!node.children.is_empty(), "{} has children", node.kind);
        let spans: Vec<_> = node.children.iter().map(|c| c.span(&cst.tokens)).collect();
        assert_eq!(
            spans.first().map(|s| s.start),
            Some(node.span.start),
            "{} starts with its first child",
            node.kind
        );
        assert_eq!(
            spans.last().map(|s| s.end),
            Some(node.span.end),
            "{} ends with its last child",
            node.kind
        );
        for pair in spans.windows(2) {
            assert!(
                pair[0].end <= pair[1].start,
                "children of {} are ordered",
                node.kind
            );
        }
        for (child, span) in node.children.iter().zip(&spans) {
            assert!(node.span.contains(*span));
            if let Element::Node(n) = child {
                walk(cst, n);
            }
        }
    }
    walk(cst, &cst.root);
    let mut leaves = 0;
    for node in cst.nodes() {
        leaves += node
            .children
            .iter()
            .filter(|c| matches!(c, Element::Leaf(_)))
            .count();
    }
    assert_eq!(
        leaves,
        cst.tokens.len(),
        "every token is a leaf of the tree exactly once"
    );
}

#[test]
fn corpus_round_trips_with_spans_or_reports_the_reference_code() {
    let cases = cases();
    assert!(cases.len() >= 59, "corpus has {} files", cases.len());
    assert!(
        cases.iter().filter(|c| c.start == Start::PureFile).count() >= 27,
        "P0 files"
    );
    let mut accepted = 0;
    for case in &cases {
        let expected = SYNTAX_INVALID
            .iter()
            .find(|(f, _)| *f == case.file)
            .map(|(_, c)| *c);
        match (parse(&case.source, case.start), expected) {
            (Ok(cst), None) => {
                assert_eq!(
                    cst.print(),
                    case.source,
                    "{}: print(parse(src)) == src",
                    case.file
                );
                let again = parse(&cst.print(), case.start).unwrap();
                assert_eq!(again, cst, "{}: re-parse gives an equal tree", case.file);
                assert_eq!(cst.root.kind, case.start.name());
                check_spans(&cst);
                accepted += 1;
            }
            (Err(d), Some(code)) => {
                assert_eq!(d.code, code, "{}: {}", case.file, d.message);
                assert!(d.rule().is_some(), "{}: rule ID", case.file);
                let doc = d.to_json(&case.file, &case.source);
                let span = doc.get("span").unwrap();
                assert!(span.get("start").and_then(|p| p.get("line")).is_some());
                assert!(d.span.end <= case.source.len());
            }
            (Ok(_), Some(code)) => {
                panic!("{}: accepted, but the reference reports {code}", case.file)
            }
            (Err(d), None) => panic!("{}: {} {} at {:?}", case.file, d.code, d.message, d.span),
        }
    }
    assert_eq!(accepted, cases.len() - SYNTAX_INVALID.len());
}

#[test]
fn every_manifest_case_is_in_the_corpus_walk() {
    let files: Vec<String> = cases().into_iter().map(|c| c.file).collect();
    for case in manifest().get("cases").and_then(Value::as_array).unwrap() {
        let file = case.get("file").and_then(Value::as_str).unwrap();
        assert!(files.iter().any(|f| f == file), "{file}");
    }
    for (file, _) in SYNTAX_INVALID {
        assert!(files.iter().any(|f| f == file), "{file}");
    }
}

#[test]
fn trivia_keep_comments_and_blank_lines() {
    let source = read("valid/commented_blocks.weave");
    let cst = parse(&source, Start::FlowFile).unwrap();
    let comments = cst
        .tokens
        .iter()
        .flat_map(|t| &t.trivia)
        .filter(|t| t.kind == weave_syntax::lexer::TriviaKind::Comment)
        .count();
    assert_eq!(comments, source.lines().filter(|l| l.contains('#')).count());
    let kinds: Vec<&str> = cst.nodes().iter().map(|n| n.kind.as_str()).collect();
    for kind in [
        "flow-file",
        "flow",
        "body",
        "match",
        "branch",
        "unit-call",
        "call",
        "qname",
        "return",
        "type",
    ] {
        assert!(kinds.contains(&kind), "{kind}");
    }
}

#[test]
fn the_p0_manifest_syntax_cases_are_the_grammar_rejections() {
    let pure = json::parse(&read("pure/manifest.json")).expect("pure manifest is JSON");
    let mut required: Vec<String> = pure
        .get("cases")
        .and_then(Value::as_array)
        .unwrap()
        .iter()
        .filter(|c| {
            c.get("kind").and_then(Value::as_str) == Some("check")
                && matches!(
                    c.get("expect").and_then(Value::as_str),
                    Some("E500" | "E001")
                )
        })
        .map(|c| c.get("file").and_then(Value::as_str).unwrap().to_string())
        .collect();
    required.sort();
    let mut listed: Vec<String> = SYNTAX_INVALID
        .iter()
        .filter(|(f, _)| f.starts_with("pure/"))
        .map(|(f, _)| f.to_string())
        .collect();
    listed.sort();
    assert_eq!(required, listed);
}

#[test]
fn pure_files_are_not_flows_or_nets_and_flows_are_not_pure_files() {
    let sort = read("pure/valid/merge_sort.weave");
    assert!(parse(&sort, Start::PureFile).is_ok());
    for start in [Start::FlowFile, Start::N0File, Start::N1File] {
        assert!(parse(&sort, start).is_err(), "{start:?}");
    }
    assert!(parse(&read("valid/checkout.weave"), Start::PureFile).is_err());
    assert!(parse(&read("nets/Inventory.weave"), Start::PureFile).is_err());
    let d = parse(
        &read("pure/invalid/chained_comparison.weave"),
        Start::PureFile,
    )
    .unwrap_err();
    assert_eq!((d.code, d.rule().as_deref()), ("E500", Some("P0-FILE-1")));
}

#[test]
fn reference_nets_parse_with_their_profiles_only() {
    // An N1 net is not an N0 file and the N0 inventory is not an N1 file.
    assert!(parse(&read("nets/Inventory.coloured.weave"), Start::N0File).is_err());
    assert!(parse(&read("nets/Inventory.weave"), Start::N1File).is_err());
    assert!(parse(&read("nets/Inventory.weave"), Start::FlowFile).is_err());
    assert!(parse(&read("valid/checkout.weave"), Start::N0File).is_err());
}
