// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Concrete syntax tree: production nodes and token leaves with trivia.
//!
//! A node's kind is the EBNF production name; lexical productions (`IDENT`,
//! `POSINT`, `NL`, `INDENT`, `DEDENT`) appear as leaves, not nodes. Every node
//! and token has a byte span, convertible to 1-based lines and columns. A
//! node's span runs from the start of its first token to the end of its last
//! token, excluding the first token's leading trivia. The root node of a start
//! symbol additionally ends with the `EOF` leaf, which carries the trailing
//! trivia, so printing the tree reproduces the source byte for byte.
//!
//! Printing and dropping a tree never recurse. Comparison, cloning and JSON
//! output recurse once per nesting level, which the parser bounds by its depth
//! limit (`parser::Options::max_depth`).

use crate::grammar::Symbol;
use crate::json::Value;
use crate::lexer::Token;
use crate::span::{LineIndex, Span};

pub const FORMAT: &str = "weave-cst-v1";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Leaf {
    /// Index into [`Cst::tokens`].
    pub token: usize,
    /// The grammar symbol that matched the token.
    pub symbol: Symbol,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Element {
    Node(Node),
    Leaf(Leaf),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Node {
    /// The production name.
    pub kind: String,
    pub span: Span,
    pub children: Vec<Element>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Cst {
    pub source: String,
    pub start: String,
    pub tokens: Vec<Token>,
    pub root: Node,
}

impl Drop for Node {
    /// Iterative, so releasing a deeply nested tree never recurses.
    fn drop(&mut self) {
        let mut stack = std::mem::take(&mut self.children);
        while let Some(element) = stack.pop() {
            if let Element::Node(mut node) = element {
                stack.append(&mut node.children);
            }
        }
    }
}

impl Element {
    pub fn span(&self, tokens: &[Token]) -> Span {
        match self {
            Element::Node(n) => n.span,
            Element::Leaf(l) => tokens.get(l.token).map_or(Span::default(), |t| t.span),
        }
    }
}

impl Cst {
    fn text(&self, span: Span) -> &str {
        self.source.get(span.start..span.end).unwrap_or_default()
    }

    /// Print the tree: each leaf's trivia and text, in tree order.
    pub fn print(&self) -> String {
        let mut out = String::with_capacity(self.source.len());
        // Explicit stack: printing never recurses, whatever the depth.
        let mut stack: Vec<&Element> = self.root.children.iter().rev().collect();
        while let Some(element) = stack.pop() {
            match element {
                Element::Node(n) => stack.extend(n.children.iter().rev()),
                Element::Leaf(l) => {
                    if let Some(t) = self.tokens.get(l.token) {
                        for trivia in &t.trivia {
                            out.push_str(self.text(trivia.span));
                        }
                        out.push_str(self.text(t.span));
                    }
                }
            }
        }
        out
    }

    /// Every node, outermost first (pre-order).
    pub fn nodes(&self) -> Vec<&Node> {
        let mut out = Vec::new();
        let mut stack = vec![&self.root];
        while let Some(n) = stack.pop() {
            out.push(n);
            for child in n.children.iter().rev() {
                if let Element::Node(c) = child {
                    stack.push(c);
                }
            }
        }
        out
    }

    /// The tree as `weave-cst-v1` JSON for `file`.
    pub fn to_json(&self, file: &str) -> Value {
        let index = LineIndex::new(&self.source);
        Value::Object(vec![
            ("format".into(), Value::str(FORMAT)),
            ("file".into(), Value::str(file)),
            ("start".into(), Value::str(self.start.clone())),
            ("root".into(), self.node_json(&self.root, &index)),
        ])
    }

    fn span_json(span: Span, index: &LineIndex) -> Value {
        let point = |offset: usize| {
            let p = index.position(offset);
            Value::Object(vec![
                ("offset".into(), Value::from_usize(offset)),
                ("line".into(), Value::from_usize(p.line)),
                ("column".into(), Value::from_usize(p.column)),
            ])
        };
        Value::Object(vec![
            ("start".into(), point(span.start)),
            ("end".into(), point(span.end)),
        ])
    }

    fn node_json(&self, node: &Node, index: &LineIndex) -> Value {
        let children = node
            .children
            .iter()
            .map(|c| match c {
                Element::Node(n) => self.node_json(n, index),
                Element::Leaf(l) => self.leaf_json(l, index),
            })
            .collect();
        Value::Object(vec![
            ("kind".into(), Value::str(node.kind.clone())),
            ("span".into(), Self::span_json(node.span, index)),
            ("children".into(), Value::Array(children)),
        ])
    }

    fn leaf_json(&self, leaf: &Leaf, index: &LineIndex) -> Value {
        let Some(t) = self.tokens.get(leaf.token) else {
            return Value::Null;
        };
        let trivia = t
            .trivia
            .iter()
            .map(|tr| {
                Value::Object(vec![
                    ("kind".into(), Value::str(tr.kind.name())),
                    ("text".into(), Value::str(self.text(tr.span))),
                    ("span".into(), Self::span_json(tr.span, index)),
                ])
            })
            .collect();
        Value::Object(vec![
            ("kind".into(), Value::str("token")),
            ("class".into(), Value::str(t.class.name())),
            ("symbol".into(), Value::str(leaf.symbol.name())),
            ("text".into(), Value::str(self.text(t.span))),
            ("span".into(), Self::span_json(t.span, index)),
            ("trivia".into(), Value::Array(trivia)),
        ])
    }
}
