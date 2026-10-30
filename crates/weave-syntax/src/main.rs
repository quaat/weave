// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! `weave-syntax`: a small driver for tests and the specification's
//! differential audit. It is not the user-facing Weave CLI.
//!
//! ```text
//! weave-syntax parse --start <flow-file|n0-file|n1-file|pure-file> FILE
//! weave-syntax roundtrip --start <flow-file|n0-file|n1-file|pure-file> FILE
//! weave-syntax grammar
//! ```
//!
//! `FILE` may be `-` for standard input. `parse` prints the `weave-cst-v1` tree
//! (exit 0) or a JSON array of `weave-diagnostic-v1` diagnostics (exit 1).
//! `roundtrip` exits 0 if and only if printing the tree reproduces the source
//! and re-parsing gives an equal tree. `grammar` prints the normalisation report
//! of the embedded grammar (exit 0 when it has no problems). Usage and input
//! errors exit 2.

use std::io::{Read, Write};
use std::process::ExitCode;
use weave_syntax::grammar;
use weave_syntax::json::Value;
use weave_syntax::{Options, Start, parse_bytes};

const USAGE: &str = "usage: weave-syntax parse|roundtrip --start <flow-file|n0-file|n1-file|pure-file> FILE\n       weave-syntax grammar";

fn emit(text: &str) {
    let mut out = std::io::stdout().lock();
    let _ = out.write_all(text.as_bytes());
    let _ = out.flush();
}

fn fail(message: &str) -> ExitCode {
    eprintln!("weave-syntax: {message}");
    ExitCode::from(2)
}

fn read(path: &str) -> Result<Vec<u8>, String> {
    if path == "-" {
        let mut bytes = Vec::new();
        std::io::stdin()
            .read_to_end(&mut bytes)
            .map_err(|e| format!("cannot read standard input: {e}"))?;
        Ok(bytes)
    } else {
        std::fs::read(path).map_err(|e| format!("cannot read {path}: {e}"))
    }
}

fn grammar_report() -> ExitCode {
    let productions = match weave_syntax::ebnf::parse(grammar::WEAVE_EBNF) {
        Ok(p) => p,
        Err(e) => return fail(&e.to_string()),
    };
    let report = grammar::check(&productions, &grammar::START_SYMBOLS);
    let problems = report
        .problems
        .iter()
        .map(|p| {
            Value::Object(vec![
                ("check".into(), Value::str(p.check)),
                ("production".into(), Value::str(p.production.clone())),
                ("line".into(), Value::from_usize(p.line)),
                ("message".into(), Value::str(p.message.clone())),
            ])
        })
        .collect();
    let doc = Value::Object(vec![
        (
            "format".into(),
            Value::str("weave-grammar-normalisation-v1"),
        ),
        ("productions".into(), Value::from_usize(report.productions)),
        (
            "lexical_productions".into(),
            Value::from_usize(report.lexical_productions),
        ),
        (
            "start_symbols".into(),
            Value::Array(
                grammar::START_SYMBOLS
                    .iter()
                    .map(|s| Value::str(*s))
                    .collect(),
            ),
        ),
        (
            "choices_checked".into(),
            Value::from_usize(report.choices_checked),
        ),
        (
            "greedy_checked".into(),
            Value::from_usize(report.greedy_checked),
        ),
        (
            "max_lookahead".into(),
            Value::from_usize(grammar::MAX_LOOKAHEAD),
        ),
        (
            "max_lookahead_used".into(),
            Value::from_usize(report.max_lookahead_used),
        ),
        ("problems".into(), Value::Array(problems)),
    ]);
    emit(&doc.to_json_pretty());
    if report.problems.is_empty() {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let Some(command) = args.first().map(String::as_str) else {
        return fail(USAGE);
    };
    if command == "grammar" {
        return if args.len() == 1 {
            grammar_report()
        } else {
            fail(USAGE)
        };
    }
    if command != "parse" && command != "roundtrip" {
        return fail(USAGE);
    }
    let (start, file) = match args.get(1..) {
        Some([flag, start, file]) if flag == "--start" => (start.as_str(), file.as_str()),
        Some([file, flag, start]) if flag == "--start" => (start.as_str(), file.as_str()),
        _ => return fail(USAGE),
    };
    let Some(start) = Start::from_name(start) else {
        return fail(&format!("unknown start symbol {start}\n{USAGE}"));
    };
    let bytes = match read(file) {
        Ok(b) => b,
        Err(e) => return fail(&e),
    };
    let name = if file == "-" { "<stdin>" } else { file };
    let lossy = String::from_utf8_lossy(&bytes);
    match parse_bytes(&bytes, start, Options::default()) {
        Err(diagnostic) => {
            let doc = Value::Array(vec![diagnostic.to_json(name, &lossy)]);
            emit(&doc.to_json_pretty());
            ExitCode::from(1)
        }
        Ok(cst) if command == "parse" => {
            emit(&cst.to_json(name).to_json());
            emit("\n");
            ExitCode::SUCCESS
        }
        Ok(cst) => {
            let printed = cst.print();
            let same_text = printed == cst.source;
            let same_tree =
                same_text && weave_syntax::parse(&printed, start).is_ok_and(|again| again == cst);
            if same_tree {
                emit(&format!(
                    "round trip: {name}: {} bytes reproduced, tree equal\n",
                    printed.len()
                ));
                ExitCode::SUCCESS
            } else {
                emit(&format!(
                    "round trip failed: {name}: {}\n",
                    if same_text {
                        "re-parsed tree differs"
                    } else {
                        "printed text differs from the source"
                    }
                ));
                ExitCode::from(1)
            }
        }
    }
}
