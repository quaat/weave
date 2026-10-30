// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! `weave`: check and run P0 pure files (`specification/docs/chapters/pure.rst`)
//! and P0 programs of several modules (modules-1, `chapters/names.rst`).
//!
//! ```text
//! weave check FILE [--root DIR] [--json]
//! weave run FILE --entry NAME [--root DIR] [--args JSON] [--fuel N] [--max-depth N] [--int-bits N] [--json]
//! weave --version
//! ```
//!
//! `FILE` may be `-` for standard input. Imports resolve from the project
//! root: `--root DIR`, or else the directory of `FILE`; standard input has no
//! root unless `--root` is given. The working directory never affects
//! resolution. `check` states one claim per loaded file (the entry first),
//! labelled `CHECKED pure`, or prints the first diagnostic, located in the
//! file it is in. `run` checks the program, then calls the entry function,
//! declared in the entry file, with the JSON array `--args` (default
//! `[]`) and reports the value, the pure fault or the exhausted budget,
//! together with every budget and what the run used of it. A run's outcome is
//! runtime status, not evidence: it carries no result label. With `--json`
//! the report is one JSON object whose diagnostics are `weave-diagnostic-v1`
//! documents; the object itself is tool output, not a versioned evidence
//! format.
//!
//! Exit status: 0 checked, or a run that returned a value; 1 a rejected file
//! or an invalid run request (E540); 2 usage or input errors; 3 a pure fault;
//! 4 an exhausted budget; 70 an internal error of the checker or evaluator.

use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::ExitCode;
use weave_check::{Entry, Sources};
use weave_eval::{Budgets, DEFAULT_BUDGETS, Outcome, RunError};
use weave_syntax::Diagnostic;
use weave_syntax::diagnostic::SourceMap;
use weave_syntax::json::{self, Value as Json};
use weave_syntax::span::LineIndex;

const USAGE: &str = "usage: weave check FILE [--root DIR] [--json]\n       weave run FILE --entry NAME [--root DIR] [--args JSON] [--fuel N] [--max-depth N] [--int-bits N] [--json]\n       weave --version";
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
    root: Option<PathBuf>,
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
        root: None,
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
            "--root" => {
                let dir = it.next().ok_or("--root needs a directory")?;
                if o.root.replace(PathBuf::from(dir)).is_some() {
                    return Err("--root is given more than once".into());
                }
            }
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

fn position(sources: &dyn SourceMap, span: weave_syntax::Span) -> String {
    let p = LineIndex::new(sources.text(span.file)).position(span.start);
    format!("{}:{}:{}", sources.name(span.file), p.line, p.column)
}

/// `FILE:line:col: CODE (RULE) [stage] message`, then one indented line per
/// related span.
fn render(d: &Diagnostic, sources: &dyn SourceMap) -> String {
    let rule = d.rule().unwrap_or_else(|| "no rule".into());
    let mut out = format!(
        "{}: {} ({rule}) [{}] {}\n",
        position(sources, d.span),
        d.code,
        d.stage,
        d.message
    );
    for r in &d.related {
        out.push_str(&format!(
            "  {}: {}: {}\n",
            position(sources, r.span),
            r.role,
            r.label
        ));
    }
    out
}

struct Report {
    sources: Sources,
    json: bool,
    fields: Vec<(String, Json)>,
    text: String,
}

impl Report {
    fn new(command: &str, file: &str, root: Option<&weave_check::Root>, json: bool) -> Report {
        Report {
            sources: Sources::default(),
            json,
            fields: vec![
                ("tool".into(), Json::str("weave")),
                ("tool_version".into(), Json::str(env!("CARGO_PKG_VERSION"))),
                ("command".into(), Json::str(command)),
                ("profile".into(), Json::str(PROFILE)),
                ("specification".into(), Json::str(SPECIFICATION)),
                ("file".into(), Json::str(file)),
                (
                    "root".into(),
                    root.map_or(Json::Null, |r| Json::str(r.display.display().to_string())),
                ),
            ],
            text: String::new(),
        }
    }

    fn set(&mut self, key: &str, value: Json) {
        self.fields.push((key.into(), value));
    }

    fn diagnostics(&mut self, ds: &[Diagnostic]) {
        let docs = ds.iter().map(|d| d.to_json_in(&self.sources)).collect();
        self.set("diagnostics", Json::Array(docs));
        for d in ds {
            let line = render(d, &self.sources);
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

/// One `CHECKED pure` claim per loaded file, the entry first.
fn claims(program: &weave_check::Program) -> (Json, String) {
    let mut json = Vec::new();
    let mut text = String::new();
    for (index, module) in program.modules.iter().enumerate() {
        let file = program.sources.name(module.file);
        let names: Vec<&str> = program
            .functions_of(index)
            .map(|f| f.name.as_str())
            .collect();
        json.push(Json::Object(vec![
            ("label".into(), Json::str(LABEL)),
            ("subject".into(), Json::str(file)),
            ("module".into(), Json::str(module.name.clone())),
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
        ]));
        text.push_str(&format!("{LABEL} {file}: {}\n", names.join(", ")));
    }
    (Json::Array(json), text)
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
            let mut r = Report::new(&o.command, name, None, o.json);
            r.sources.files.push(weave_check::SourceFile {
                name: name.to_string(),
                text: lossy,
                module: String::new(),
            });
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
    let entry = Entry {
        name: name.to_string(),
        text: source,
        path: (o.file != "-").then(|| PathBuf::from(&o.file)),
    };
    let root = match weave_check::project_root(&entry, o.root.as_deref()) {
        Ok(r) => r,
        Err(e) => return usage(&e),
    };
    let mut report = Report::new(&o.command, name, root.as_ref(), o.json);
    let program = match weave_check::check_entry(entry, root) {
        Ok(p) => p,
        // A checker defect is not a rejection of the file: no claim, no diagnostic.
        Err(f) if weave_check::is_internal(&f.diagnostic) => {
            eprintln!("weave: internal checker error: {}", f.diagnostic.message);
            return ExitCode::from(70);
        }
        Err(f) => {
            report.sources = f.sources;
            report.set("claims", Json::Array(Vec::new()));
            if o.command == "run" {
                report.set("outcome", Json::Null);
            }
            report.diagnostics(&[*f.diagnostic]);
            return report.finish(1);
        }
    };
    report.sources = program.sources.clone();
    let (claim_json, claim_text) = claims(&program);
    report.set("claims", claim_json);
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
