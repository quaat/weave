// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Syntax diagnostics in the `weave-diagnostic-v1` shape
//! (`evidence/schemas/diagnostic.v1.schema.json`).
//!
//! Codes and their rule mapping come from the specification's
//! `diagnostics.json`, embedded at build time; this crate mints no code.

use crate::json::{self, Value};
use crate::span::{FileId, LineIndex, Span};
use std::sync::OnceLock;

/// The specification's code-to-rule map.
pub const DIAGNOSTICS_JSON: &str = include_str!("../../../specification/diagnostics.json");

pub const FORMAT: &str = "weave-diagnostic-v1";

/// Layout faults: tabs, indentation that is not a multiple of four spaces, a
/// skipped level, an indented first line, or a block after a line not ending in `:`.
pub const LAYOUT_CODE: &str = "E001";
/// Lexical or grammar faults in an `n0-file` or `n1-file`.
pub const NET_SYNTAX_CODE: &str = "E003";
/// Lexical or grammar faults in a `flow-file`.
pub const FLOW_SYNTAX_CODE: &str = "E200";
/// Lexical or grammar faults in a P0 `pure-file`.
pub const PURE_SYNTAX_CODE: &str = "E500";

/// One code's entry in `diagnostics.json`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CodeInfo {
    pub category: String,
    pub rule: Option<String>,
    pub secondary_rules: Vec<String>,
    pub meaning: String,
}

fn code_map() -> &'static Result<Value, json::JsonError> {
    static MAP: OnceLock<Result<Value, json::JsonError>> = OnceLock::new();
    MAP.get_or_init(|| json::parse(DIAGNOSTICS_JSON))
}

/// The entry for `code` in the embedded `diagnostics.json`, if any.
pub fn code_info(code: &str) -> Option<CodeInfo> {
    let entry = code_map().as_ref().ok()?.get("codes")?.get(code)?;
    Some(CodeInfo {
        category: entry.get("category")?.as_str()?.to_string(),
        rule: entry
            .get("rule")
            .and_then(Value::as_str)
            .map(str::to_string),
        secondary_rules: entry
            .get("secondary_rules")?
            .as_array()?
            .iter()
            .filter_map(|v| v.as_str().map(str::to_string))
            .collect(),
        meaning: entry.get("meaning")?.as_str()?.to_string(),
    })
}

/// The display name and text of each source file a diagnostic's spans can
/// refer to, indexed by [`FileId`].
pub trait SourceMap {
    /// The file's name as the user gave it or as it was resolved.
    fn name(&self, file: FileId) -> &str;
    /// The file's text.
    fn text(&self, file: FileId) -> &str;
}

/// One file, whatever the span's [`FileId`]: the single-file case.
pub struct SingleSource<'a> {
    pub name: &'a str,
    pub text: &'a str,
}

impl SourceMap for SingleSource<'_> {
    fn name(&self, _: FileId) -> &str {
        self.name
    }
    fn text(&self, _: FileId) -> &str {
        self.text
    }
}

/// A related span of a diagnostic (`weave-diagnostic-v1` `related`): its role
/// (one of the code's `related_roles` in `diagnostics.json`) and a label.
#[derive(Clone, Debug, PartialEq)]
pub struct Related {
    pub role: &'static str,
    pub label: String,
    pub span: Span,
}

/// A diagnostic over byte spans; `to_json` converts it to `weave-diagnostic-v1`.
#[derive(Clone, Debug, PartialEq)]
pub struct Diagnostic {
    pub code: &'static str,
    /// Checking stage: `lexical`, `layout`, `syntax`, `limit`, or a later
    /// stage of the tools built on this crate.
    pub stage: &'static str,
    pub message: String,
    pub span: Span,
    /// Related spans, possibly in other files (boxed, so a diagnostic stays
    /// small in the `Err` of every parser result).
    pub related: Box<[Related]>,
    /// Producer-specific structured data (`details`).
    pub details: Vec<(String, Value)>,
}

impl Diagnostic {
    pub fn new(
        code: &'static str,
        stage: &'static str,
        message: impl Into<String>,
        span: Span,
    ) -> Diagnostic {
        Diagnostic {
            code,
            stage,
            message: message.into(),
            span,
            related: Box::default(),
            details: Vec::new(),
        }
    }

    pub fn with_related(
        mut self,
        role: &'static str,
        label: impl Into<String>,
        span: Span,
    ) -> Diagnostic {
        let mut related = std::mem::take(&mut self.related).into_vec();
        related.push(Related {
            role,
            label: label.into(),
            span,
        });
        self.related = related.into_boxed_slice();
        self
    }

    pub fn with_detail(mut self, key: &str, value: Value) -> Diagnostic {
        self.details.push((key.to_string(), value));
        self
    }

    /// The principal rule of this diagnostic's code.
    pub fn rule(&self) -> Option<String> {
        code_info(self.code).and_then(|info| info.rule)
    }

    /// The `weave-diagnostic-v1` document for `file`, whose text is `source`.
    /// Every span is read in that one file.
    pub fn to_json(&self, file: &str, source: &str) -> Value {
        self.to_json_in(&SingleSource {
            name: file,
            text: source,
        })
    }

    /// The `weave-diagnostic-v1` document, each span located in the file of
    /// its [`FileId`] in `sources`.
    pub fn to_json_in(&self, sources: &dyn SourceMap) -> Value {
        // diagnostics.json lists every code this crate emits (tested); the
        // fallback keeps the function total rather than panicking.
        let info = code_info(self.code).unwrap_or(CodeInfo {
            category: "specification".into(),
            rule: None,
            secondary_rules: Vec::new(),
            meaning: String::new(),
        });
        let span_json = |span: Span| {
            let index = LineIndex::new(sources.text(span.file));
            let position = |offset: usize| {
                let p = index.position(offset);
                Value::Object(vec![
                    ("line".into(), Value::from_usize(p.line)),
                    ("column".into(), Value::from_usize(p.column)),
                ])
            };
            let file = sources.name(span.file);
            let file = if file.is_empty() { "<input>" } else { file };
            Value::Object(vec![
                ("file".into(), Value::str(file)),
                ("start".into(), position(span.start)),
                ("end".into(), position(span.end)),
            ])
        };
        let mut details = vec![
            ("byte_start".to_string(), Value::from_usize(self.span.start)),
            ("byte_end".to_string(), Value::from_usize(self.span.end)),
        ];
        details.extend(self.details.iter().cloned());
        let related = self
            .related
            .iter()
            .map(|r| {
                Value::Object(vec![
                    ("role".into(), Value::str(r.role)),
                    ("label".into(), Value::str(r.label.clone())),
                    ("span".into(), span_json(r.span)),
                ])
            })
            .collect();
        Value::Object(vec![
            ("format".into(), Value::str(FORMAT)),
            ("code".into(), Value::str(self.code)),
            ("category".into(), Value::str(info.category)),
            ("rule".into(), info.rule.map_or(Value::Null, Value::String)),
            (
                "secondary_rules".into(),
                Value::Array(
                    info.secondary_rules
                        .into_iter()
                        .map(Value::String)
                        .collect(),
                ),
            ),
            ("severity".into(), Value::str("error")),
            ("stage".into(), Value::str(self.stage)),
            ("message".into(), Value::str(self.message.clone())),
            ("span".into(), span_json(self.span)),
            ("related".into(), Value::Array(related)),
            ("details".into(), Value::Object(details)),
        ])
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn emitted_codes_are_specification_codes_with_rules() {
        for (code, rule) in [
            (LAYOUT_CODE, "LEX-REQ-1"),
            (NET_SYNTAX_CODE, "SYN-04"),
            (FLOW_SYNTAX_CODE, "CONF-REQ-1"),
            (PURE_SYNTAX_CODE, "P0-FILE-1"),
        ] {
            let info = code_info(code);
            assert_eq!(
                info.as_ref().map(|i| i.category.as_str()),
                Some("specification")
            );
            assert_eq!(info.and_then(|i| i.rule).as_deref(), Some(rule));
        }
        assert!(code_info("E999").is_none());
    }

    struct Two;

    impl SourceMap for Two {
        fn name(&self, file: FileId) -> &str {
            ["main.weave", "lib/a.weave"][file.index().min(1)]
        }
        fn text(&self, file: FileId) -> &str {
            ["from lib.a import f\n", "# a\nfrom main import g\n"][file.index().min(1)]
        }
    }

    #[test]
    fn spans_are_located_in_their_own_files() {
        let d = Diagnostic::new(
            "E604",
            "module",
            "cycle",
            Span::new(7, 9).in_file(FileId(1)),
        )
        .with_related("import", "main imports lib.a", Span::new(5, 10))
        .with_related(
            "import",
            "lib.a imports main",
            Span::new(9, 13).in_file(FileId(1)),
        );
        let doc = d.to_json_in(&Two);
        let at = |span: &Value| {
            let file = span.get("file").and_then(Value::as_str).map(str::to_string);
            let line = span.get("start").and_then(|s| s.get("line")).cloned();
            (file, line)
        };
        let primary = doc.get("span").map(at);
        assert_eq!(
            primary,
            Some((Some("lib/a.weave".into()), Some(Value::from_usize(2))))
        );
        let related: Vec<_> = doc
            .get("related")
            .and_then(Value::as_array)
            .map(|r| r.iter().filter_map(|x| x.get("span")).map(at).collect())
            .unwrap_or_default();
        assert_eq!(
            related,
            vec![
                (Some("main.weave".into()), Some(Value::from_usize(1))),
                (Some("lib/a.weave".into()), Some(Value::from_usize(2))),
            ]
        );
        // The single-file form reads every span in its one file, as before.
        let one = d.to_json("x.weave", "abc");
        let file = one
            .get("span")
            .and_then(|s| s.get("file"))
            .and_then(Value::as_str);
        assert_eq!(file, Some("x.weave"));
    }
}
