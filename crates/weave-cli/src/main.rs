// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! `weave`: check and run P0 pure files (`specification/docs/chapters/pure.rst`).
//!
//! ```text
//! weave check FILE [--json]
//! weave run FILE --entry NAME [--args JSON] [--fuel N] [--max-depth N] [--int-bits N] [--json]
//! weave --version
//! ```
//!
//! `FILE` may be `-` for standard input. `check` states one claim per file,
//! labelled `CHECKED pure`, or prints the first diagnostic. `run` checks the
//! file, then calls the entry function with the JSON array `--args` (default
//! `[]`) and reports the value, the pure fault or the exhausted budget,
//! together with every budget and what the run used of it. A run's outcome is
//! runtime status, not evidence: it carries no result label. With `--json`
//! the report is one JSON object whose diagnostics are `weave-diagnostic-v1`
//! documents; the object itself is tool output, not a versioned evidence
//! format.
//!
//! Exit status: 0 checked, or a run that returned a value; 1 a rejected file
//! or an invalid run request (E540); 2 usage or input errors; 3 a pure fault;
//! 4 an exhausted budget.

use std::io::{Read, Write};
use std::process::ExitCode;
use weave_eval::{Budgets, DEFAULT_BUDGETS, Outcome, RunError};
use weave_syntax::Diagnostic;
use weave_syntax::json::{self, Value as Json};
use weave_syntax::span::LineIndex;

const USAGE: &str = "usage: weave check FILE [--json]\n       weave run FILE --entry NAME [--args JSON] [--fuel N] [--max-depth N] [--int-bits N] [--json]\n       weave --version";
const LABEL: &str = "CHECKED pure";
const PROFILE: &str = "P0";
const SPECIFICATION: &str = "0.2-draft";

fn emit(text: &str) {
    let mut out = std::io::stdout().lock();
    let _ = out.write_all(text.as_bytes());
    let _ = out.flush();
}

fn usage(message: &str) -> ExitCode {
    eprintln!("weave: {message}\n{USAGE}");
    ExitCode::from(2)
}

struct Options {
    command: String,
    file: String,
    json: bool,
    entry: Option<String>,
    args: String,
    budgets: Budgets,
}

fn parse_args(args: &[String]) -> Result<Options, String> {
    let mut it = args.iter();
    let command = it.next().cloned().ok_or("missing command")?;
    if command != "check" && command != "run" {
        return Err(format!("unknown command {command}"));
    }
    let mut o = Options {
        command,
        file: String::new(),
        json: false,
        entry: None,
        args: "[]".into(),
        budgets: DEFAULT_BUDGETS,
    };
    let mut file = None;
    let number = |flag: &str, v: Option<&String>| -> Result<u64, String> {
        v.ok_or(format!("{flag} needs a value"))?
            .parse::<u64>()
            .map_err(|_| format!("{flag} needs a nonnegative integer"))
    };
    while let Some(a) = it.next() {
        let run_only = |flag: &str| -> Result<(), String> {
            if o.command == "run" {
                Ok(())
            } else {
                Err(format!("{flag} applies only to run"))
            }
        };
        match a.as_str() {
            "--json" => o.json = true,
            "--entry" => {
                run_only(a)?;
                o.entry = Some(it.next().cloned().ok_or("--entry needs a name")?);
            }
            "--args" => {
                run_only(a)?;
                o.args = it.next().cloned().ok_or("--args needs a JSON array")?;
            }
            "--fuel" => {
                run_only(a)?;
                o.budgets.fuel = number(a, it.next())?;
            }
            "--max-depth" => {
                run_only(a)?;
                o.budgets.depth = number(a, it.next())?;
            }
            "--int-bits" => {
                run_only(a)?;
                o.budgets.int_bits = number(a, it.next())?;
            }
            flag if flag.starts_with("--") => return Err(format!("unknown option {flag}")),
            path => {
                if file.replace(path.to_string()).is_some() {
                    return Err("exactly one FILE".into());
                }
            }
        }
    }
    o.file = file.ok_or("missing FILE")?;
    if o.command == "run" && o.entry.is_none() {
        return Err("run needs --entry NAME".into());
    }
    Ok(o)
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

/// `FILE:line:col: CODE (RULE) [stage] message`.
fn render(d: &Diagnostic, file: &str, source: &str) -> String {
    let p = LineIndex::new(source).position(d.span.start);
    let rule = d.rule().unwrap_or_else(|| "no rule".into());
    format!(
        "{file}:{}:{}: {} ({rule}) [{}] {}\n",
        p.line, p.column, d.code, d.stage, d.message
    )
}

struct Report {
    file: String,
    source: String,
    json: bool,
    fields: Vec<(String, Json)>,
    text: String,
}

impl Report {
    fn new(command: &str, file: &str, source: &str, json: bool) -> Report {
        Report {
            file: file.to_string(),
            source: source.to_string(),
            json,
            fields: vec![
                ("tool".into(), Json::str("weave")),
                ("tool_version".into(), Json::str(env!("CARGO_PKG_VERSION"))),
                ("command".into(), Json::str(command)),
                ("profile".into(), Json::str(PROFILE)),
                ("specification".into(), Json::str(SPECIFICATION)),
                ("file".into(), Json::str(file)),
            ],
            text: String::new(),
        }
    }

    fn set(&mut self, key: &str, value: Json) {
        self.fields.push((key.into(), value));
    }

    fn diagnostics(&mut self, ds: &[Diagnostic]) {
        let docs = ds
            .iter()
            .map(|d| d.to_json(&self.file, &self.source))
            .collect();
        self.set("diagnostics", Json::Array(docs));
        for d in ds {
            let line = render(d, &self.file, &self.source);
            self.text.push_str(&line);
        }
    }

    fn finish(self, code: u8) -> ExitCode {
        if self.json {
            emit(&Json::Object(self.fields).to_json_pretty());
        } else {
            emit(&self.text);
        }
        ExitCode::from(code)
    }
}

fn claim(file: &str, program: &weave_check::Program) -> (Json, String) {
    let names: Vec<&str> = program.functions.iter().map(|f| f.name.as_str()).collect();
    let json = Json::Object(vec![
        ("label".into(), Json::str(LABEL)),
        ("subject".into(), Json::str(file)),
        (
            "statement".into(),
            Json::str(
                "P0 type, effect, path and recursion-shape checks passed for every function of the file",
            ),
        ),
        (
            "functions".into(),
            Json::Array(names.iter().map(|n| Json::str(*n)).collect()),
        ),
    ]);
    let text = format!("{LABEL} {file}: {}\n", names.join(", "));
    (json, text)
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("--version") {
        emit(&format!("weave {}\n", env!("CARGO_PKG_VERSION")));
        return ExitCode::SUCCESS;
    }
    let o = match parse_args(&args) {
        Ok(o) => o,
        Err(e) => return usage(&e),
    };
    let bytes = match read(&o.file) {
        Ok(b) => b,
        Err(e) => return usage(&e),
    };
    let name = if o.file == "-" {
        "<stdin>"
    } else {
        o.file.as_str()
    };
    let source = match String::from_utf8(bytes) {
        Ok(s) => s,
        Err(e) => {
            let at = e.utf8_error().valid_up_to();
            let lossy = String::from_utf8_lossy(e.as_bytes()).into_owned();
            let mut r = Report::new(&o.command, name, &lossy, o.json);
            r.set("claims", Json::Array(Vec::new()));
            r.diagnostics(&[Diagnostic::new(
                weave_syntax::diagnostic::PURE_SYNTAX_CODE,
                "lexical",
                "The source is not valid UTF-8.",
                weave_syntax::Span::new(at, at + 1),
            )]);
            return r.finish(1);
        }
    };
    let mut report = Report::new(&o.command, name, &source, o.json);
    let program = match weave_check::check(&source) {
        Ok(p) => p,
        Err(d) => {
            report.set("claims", Json::Array(Vec::new()));
            if o.command == "run" {
                report.set("outcome", Json::Null);
            }
            report.diagnostics(&[d]);
            return report.finish(1);
        }
    };
    let (claim_json, claim_text) = claim(name, &program);
    report.set("claims", Json::Array(vec![claim_json]));
    report.text.push_str(&claim_text);
    if o.command == "check" {
        report.diagnostics(&[]);
        return report.finish(0);
    }
    let entry = o.entry.clone().unwrap_or_default();
    report.set("entry", Json::str(entry.clone()));
    let args = match json::parse(&o.args) {
        Ok(v) => v,
        Err(e) => return usage(&format!("--args is not JSON: {e:?}")),
    };
    match weave_eval::run(&program, &entry, &args, o.budgets) {
        Err(RunError::Request(d)) => {
            report.set("outcome", Json::Null);
            report.diagnostics(&[d]);
            report.finish(1)
        }
        Err(RunError::Internal(e)) => {
            eprintln!("weave: {}", e.0);
            ExitCode::from(70)
        }
        Ok(run) => {
            let budgets = weave_eval::budgets_json(&run);
            let (outcome, value, fault, exhausted, code) = match &run.outcome {
                Outcome::Value(v) => (
                    "value",
                    weave_eval::value::to_json(v, &program),
                    Json::Null,
                    Json::Null,
                    0,
                ),
                Outcome::Fault(f, _) => ("fault", Json::Null, Json::str(f.name()), Json::Null, 3),
                Outcome::Exhausted(x, _) => {
                    ("exhausted", Json::Null, Json::Null, Json::str(x.name()), 4)
                }
            };
            report.text.push_str(&format!("outcome: {outcome}\n"));
            match &run.outcome {
                Outcome::Value(_) => report
                    .text
                    .push_str(&format!("result: {}\n", value.to_json())),
                Outcome::Fault(f, _) => report.text.push_str(&format!("fault: {}\n", f.name())),
                Outcome::Exhausted(x, _) => {
                    report.text.push_str(&format!("exhausted: {}\n", x.name()))
                }
            }
            report.text.push_str(&format!(
                "budgets: fuel {}/{}, depth {}/{}, int-bits {}/{}\n",
                run.usage.fuel,
                run.budgets.fuel,
                run.usage.depth,
                run.budgets.depth,
                run.usage.int_bits,
                run.budgets.int_bits
            ));
            report.set("outcome", Json::str(outcome));
            report.set("value", value);
            report.set("fault", fault);
            report.set("exhausted", exhausted);
            report.set("budgets", budgets);
            let diagnostics: Vec<Diagnostic> =
                weave_eval::outcome_diagnostic(&run).into_iter().collect();
            report.diagnostics(&diagnostics);
            report.finish(code)
        }
    }
}
