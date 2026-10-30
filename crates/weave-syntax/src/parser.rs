// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Ordered-choice interpretation of the compiled grammar over the token stream.

use crate::cst::{Cst, Element, Leaf, Node};
use crate::diagnostic::{Diagnostic, FLOW_SYNTAX_CODE, NET_SYNTAX_CODE, PURE_SYNTAX_CODE};
use crate::grammar::{self, GExpr, Grammar, Symbol};
use crate::json::Value;
use crate::lexer::{self, LexCodes, Token, TokenClass};
use crate::span::Span;
use std::collections::BTreeSet;

/// Default limit on nested productions. Deeper input is rejected with a
/// diagnostic (stage `limit`), never with a stack overflow.
pub const DEFAULT_MAX_DEPTH: usize = 400;
/// Upper bound on [`Options::max_depth`]; larger requests are clamped.
pub const MAX_DEPTH_CAP: usize = 2_000;
/// The interpreter runs on its own thread with this stack, so the depth limit
/// holds whatever stack the caller has.
pub const PARSER_STACK_BYTES: usize = 64 << 20;

/// A start symbol of the portable grammar (SYN-01).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Start {
    FlowFile,
    N0File,
    N1File,
    /// A P0 pure file (`chapters/pure.rst`).
    PureFile,
}

impl Start {
    pub const ALL: [Start; 4] = [
        Start::FlowFile,
        Start::N0File,
        Start::N1File,
        Start::PureFile,
    ];

    pub fn name(self) -> &'static str {
        match self {
            Start::FlowFile => "flow-file",
            Start::N0File => "n0-file",
            Start::N1File => "n1-file",
            Start::PureFile => "pure-file",
        }
    }

    pub fn from_name(name: &str) -> Option<Start> {
        Start::ALL.into_iter().find(|s| s.name() == name)
    }

    /// The syntax code: the reference checker's E200 for flows and E003 for
    /// nets; E500 for P0 pure files.
    pub fn syntax_code(self) -> &'static str {
        match self {
            Start::FlowFile => FLOW_SYNTAX_CODE,
            Start::N0File | Start::N1File => NET_SYNTAX_CODE,
            Start::PureFile => PURE_SYNTAX_CODE,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Options {
    pub max_depth: usize,
}

impl Default for Options {
    fn default() -> Options {
        Options {
            max_depth: DEFAULT_MAX_DEPTH,
        }
    }
}

/// Parse `source` from `start` with the embedded grammar.
pub fn parse(source: &str, start: Start) -> Result<Cst, Diagnostic> {
    parse_with(source, start, Options::default())
}

/// Parse raw bytes; invalid UTF-8 is a lexical diagnostic at the first invalid byte.
pub fn parse_bytes(bytes: &[u8], start: Start, options: Options) -> Result<Cst, Diagnostic> {
    match std::str::from_utf8(bytes) {
        Ok(source) => parse_with(source, start, options),
        Err(e) => {
            let at = e.valid_up_to();
            Err(Diagnostic::new(
                start.syntax_code(),
                "lexical",
                "The source is not valid UTF-8.",
                Span::new(at, at + e.error_len().unwrap_or(1)),
            ))
        }
    }
}

pub fn parse_with(source: &str, start: Start, options: Options) -> Result<Cst, Diagnostic> {
    let grammar = match grammar::builtin() {
        Ok(g) => g,
        Err(report) => {
            let first = report
                .problems
                .first()
                .map(ToString::to_string)
                .unwrap_or_default();
            return Err(Diagnostic::new(
                start.syntax_code(),
                "grammar",
                format!("The embedded grammar failed its normalisation check: {first}"),
                Span::at(0),
            ));
        }
    };
    parse_grammar(grammar, source, start.name(), start.syntax_code(), options)
}

/// Parse with an explicit grammar and start production.
pub fn parse_grammar(
    grammar: &Grammar,
    source: &str,
    start: &str,
    code: &'static str,
    options: Options,
) -> Result<Cst, Diagnostic> {
    let tokens = lexer::lex(source, LexCodes { syntax: code })?;
    let Some(rule) = grammar.rule(start) else {
        return Err(Diagnostic::new(
            code,
            "syntax",
            format!("Unknown start symbol {start}."),
            Span::at(0),
        ));
    };
    let depth = options.max_depth.min(MAX_DEPTH_CAP);
    let interpreted = std::thread::scope(|scope| {
        std::thread::Builder::new()
            .name("weave-syntax".into())
            .stack_size(PARSER_STACK_BYTES)
            .spawn_scoped(scope, || {
                interpret(grammar, source, &tokens, rule, start, code, depth)
            })
            .map(|handle| handle.join())
    });
    match interpreted {
        Ok(Ok(Ok(root))) => Ok(Cst {
            source: source.to_string(),
            start: start.to_string(),
            tokens,
            root,
        }),
        Ok(Ok(Err(diagnostic))) => Err(diagnostic),
        // A panic is a parser bug; it is still reported, never propagated.
        Ok(Err(_)) => Err(Diagnostic::new(
            code,
            "internal",
            "Internal parser error.",
            Span::at(0),
        )),
        Err(e) => Err(spawn_failure(code, &e)),
    }
}

/// A failure to start the parser thread is a host failure, not a statement
/// about the source: stage `internal`, which tools report as an internal
/// error rather than a rejection.
fn spawn_failure(code: &'static str, e: &std::io::Error) -> Diagnostic {
    Diagnostic::new(
        code,
        "internal",
        format!("Could not start the parser thread: {e}"),
        Span::at(0),
    )
}

fn interpret(
    grammar: &Grammar,
    source: &str,
    tokens: &[Token],
    rule: usize,
    start: &str,
    code: &'static str,
    max_depth: usize,
) -> Result<Node, Diagnostic> {
    let mut p = Interp {
        g: grammar,
        src: source,
        toks: tokens,
        depth: 0,
        max_depth,
        too_deep: None,
        farthest: 0,
        expected: BTreeSet::new(),
    };
    let mut out = Vec::new();
    let end = p.expr(&GExpr::Rule(rule), 0, &mut out);
    if let Some(at) = p.too_deep {
        let span = tokens.get(at).map_or(Span::at(source.len()), |t| t.span);
        return Err(Diagnostic::new(
            code,
            "limit",
            format!("Nesting exceeds this parser's limit of {max_depth} productions; the input is not checked further."),
            span,
        )
        .with_detail("limit", Value::from_usize(max_depth)));
    }
    if let Some(end) = end {
        if let (Some(eof), Some(Element::Node(mut root))) = (tokens.get(end), out.pop())
            && eof.class == TokenClass::Eof
        {
            root.children.push(Element::Leaf(Leaf {
                token: end,
                symbol: Symbol::Eof,
            }));
            root.span.end = eof.span.end;
            return Ok(root);
        }
        p.expect(end, &Symbol::Eof);
    }
    Err(p.error(code, start))
}

struct Interp<'a> {
    g: &'a Grammar,
    src: &'a str,
    toks: &'a [Token],
    depth: usize,
    max_depth: usize,
    too_deep: Option<usize>,
    farthest: usize,
    expected: BTreeSet<String>,
}

impl Interp<'_> {
    fn expect(&mut self, pos: usize, symbol: &Symbol) {
        if pos > self.farthest {
            self.farthest = pos;
            self.expected.clear();
        }
        if pos == self.farthest {
            self.expected.insert(symbol.describe());
        }
    }

    fn found(&self, t: &Token) -> String {
        match t.class {
            TokenClass::Word | TokenClass::Int | TokenClass::Punct => {
                format!(
                    "'{}'",
                    self.src.get(t.span.start..t.span.end).unwrap_or_default()
                )
            }
            TokenClass::Newline if t.span.is_empty() => "the end of the file".into(),
            TokenClass::Newline => "the end of the line".into(),
            TokenClass::Indent => "an indented block".into(),
            TokenClass::Dedent => "the end of the block".into(),
            TokenClass::Eof => "the end of the file".into(),
        }
    }

    fn error(&self, code: &'static str, start: &str) -> Diagnostic {
        let token = self.toks.get(self.farthest).or_else(|| self.toks.last());
        let span = token.map_or(Span::at(self.src.len()), |t| t.span);
        let found = token.map_or_else(|| "the end of the file".to_string(), |t| self.found(t));
        let expected: Vec<String> = self.expected.iter().cloned().collect();
        let list = match expected.as_slice() {
            [] => "valid syntax".to_string(),
            [one] => one.clone(),
            [init @ .., last] => format!("{} or {}", init.join(", "), last),
        };
        Diagnostic::new(
            code,
            "syntax",
            format!("Expected {list}; found {found}."),
            span,
        )
        .with_detail("start_symbol", Value::str(start))
        .with_detail(
            "expected",
            Value::Array(expected.into_iter().map(Value::String).collect()),
        )
        .with_detail("found", Value::str(found))
    }

    fn expr(&mut self, e: &GExpr, pos: usize, out: &mut Vec<Element>) -> Option<usize> {
        if self.too_deep.is_some() {
            return None;
        }
        match e {
            GExpr::Sym(symbol) => {
                let token = self.toks.get(pos)?;
                let text = self
                    .src
                    .get(token.span.start..token.span.end)
                    .unwrap_or_default();
                if symbol.matches(token, text) {
                    out.push(Element::Leaf(Leaf {
                        token: pos,
                        symbol: symbol.clone(),
                    }));
                    Some(pos + 1)
                } else {
                    self.expect(pos, symbol);
                    None
                }
            }
            GExpr::Rule(i) => {
                let rule = self.g.rules.get(*i)?;
                if self.depth >= self.max_depth {
                    self.too_deep = Some(pos);
                    return None;
                }
                self.depth += 1;
                let mut children = Vec::new();
                let end = self.expr(&rule.body, pos, &mut children);
                self.depth -= 1;
                let end = end?;
                let at = self.toks.get(pos).map_or(self.src.len(), |t| t.span.start);
                let span = match (children.first(), children.last()) {
                    (Some(first), Some(last)) => {
                        Span::new(first.span(self.toks).start, last.span(self.toks).end)
                    }
                    _ => Span::at(at),
                };
                out.push(Element::Node(Node {
                    kind: rule.name.clone(),
                    span,
                    children,
                }));
                Some(end)
            }
            GExpr::Seq(items) => {
                let mark = out.len();
                let mut p = pos;
                for item in items {
                    match self.expr(item, p, out) {
                        Some(q) => p = q,
                        None => {
                            out.truncate(mark);
                            return None;
                        }
                    }
                }
                Some(p)
            }
            GExpr::Alt(items) => {
                for item in items {
                    let mark = out.len();
                    if let Some(q) = self.expr(item, pos, out) {
                        return Some(q);
                    }
                    out.truncate(mark);
                    if self.too_deep.is_some() {
                        return None;
                    }
                }
                None
            }
            GExpr::Opt(x) => {
                let mark = out.len();
                match self.expr(x, pos, out) {
                    Some(q) => Some(q),
                    None => {
                        out.truncate(mark);
                        if self.too_deep.is_some() {
                            None
                        } else {
                            Some(pos)
                        }
                    }
                }
            }
            GExpr::Rep(x) => {
                let mut p = pos;
                loop {
                    let mark = out.len();
                    match self.expr(x, p, out) {
                        Some(q) if q > p => p = q,
                        Some(_) => {
                            out.truncate(mark);
                            break;
                        }
                        None => {
                            out.truncate(mark);
                            break;
                        }
                    }
                }
                if self.too_deep.is_some() {
                    None
                } else {
                    Some(p)
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn a_thread_spawn_failure_is_internal() {
        let e = std::io::Error::other("no threads");
        let d = super::spawn_failure("E500", &e);
        assert_eq!(d.stage, "internal");
        assert!(d.message.contains("no threads"));
    }
}
