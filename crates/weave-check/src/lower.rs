// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Lowering of a `pure-file` concrete syntax tree to the AST.
//!
//! Each AST node takes the span of the CST node (or token) it comes from, so
//! the lowering preserves the source mapping. Binary operators fold to the
//! left; parentheses disappear, leaving the inner expression's span.
//!
//! The diagnostics raised here are `E500` (`P0-FILE-1`): for a word other than
//! `await` before a qualified name, which the grammar admits only so that
//! `await` can be rejected statically, and, at stage `limit`, for a file
//! beyond the nesting limits of `pure.rst` ([`SYNTAX_DEPTH_LIMIT`],
//! [`EXPR_DEPTH_LIMIT`]). The expression depth is computed bottom-up while the
//! AST is built, so an over-deep expression (such as a long flat operator
//! chain) is rejected before any deep tree exists; every later recursive pass
//! (checking, lowering to instructions, dropping) is then bounded.

use crate::ast::*;
use weave_syntax::diagnostic::PURE_SYNTAX_CODE;
use weave_syntax::{Cst, Diagnostic, Element, Node, Span};

/// Largest syntax depth of a P0 file: nested production nodes of its
/// derivation tree from `pure-file`, the root counting 1, not counting the
/// lexical productions (`UINT` is a node in this parser and is not counted).
pub const SYNTAX_DEPTH_LIMIT: usize = 300;
/// Largest expression depth (see [`ExprAst::depth`]).
pub const EXPR_DEPTH_LIMIT: usize = 256;

fn limit(message: String, span: Span, limit: usize) -> Diagnostic {
    Diagnostic::new(PURE_SYNTAX_CODE, "limit", message, span)
        .with_detail("limit", weave_syntax::json::Value::from_usize(limit))
}

/// The first node (in pre-order) deeper than [`SYNTAX_DEPTH_LIMIT`], if any.
fn check_syntax_depth(cst: &Cst) -> Result<(), Diagnostic> {
    let mut stack: Vec<(&Node, usize)> = vec![(&cst.root, 1)];
    while let Some((node, depth)) = stack.pop() {
        if depth > SYNTAX_DEPTH_LIMIT {
            return Err(limit(
                format!(
                    "Nesting exceeds the P0 syntax depth limit of {SYNTAX_DEPTH_LIMIT} productions."
                ),
                node.span,
                SYNTAX_DEPTH_LIMIT,
            ));
        }
        for child in node.children.iter().rev() {
            if let Element::Node(n) = child
                && n.kind != "UINT"
            {
                stack.push((n, depth + 1));
            }
        }
    }
    Ok(())
}

pub fn lower(cst: &Cst) -> Result<FileAst, Diagnostic> {
    check_syntax_depth(cst)?;
    let l = Lowering { cst };
    let mut items = Vec::new();
    for item in l.nodes(&cst.root, "pure-item") {
        for child in l.all_nodes(item) {
            match child.kind.as_str() {
                "record-decl" => items.push(Item::Record(l.record(child)?)),
                "fn-decl" => items.push(Item::Fn(l.function(child)?)),
                other => return Err(l.shape(other, child.span)),
            }
        }
    }
    Ok(FileAst { items })
}

struct Lowering<'a> {
    cst: &'a Cst,
}

impl<'a> Lowering<'a> {
    /// An AST expression, rejected with `E500` at stage `limit` when its depth
    /// exceeds [`EXPR_DEPTH_LIMIT`].
    fn expr_node(&self, kind: ExprKind, span: Span) -> Result<ExprAst, Diagnostic> {
        let e = ExprAst::new(kind, span);
        if e.depth > EXPR_DEPTH_LIMIT {
            return Err(limit(
                format!(
                    "Expression nesting exceeds the P0 expression depth limit of {EXPR_DEPTH_LIMIT}."
                ),
                span,
                EXPR_DEPTH_LIMIT,
            ));
        }
        Ok(e)
    }

    fn text(&self, span: Span) -> &'a str {
        self.cst
            .source
            .get(span.start..span.end)
            .unwrap_or_default()
    }

    fn shape(&self, what: &str, span: Span) -> Diagnostic {
        Diagnostic::new(
            PURE_SYNTAX_CODE,
            "internal",
            format!("Internal error: unexpected syntax tree shape at {what}."),
            span,
        )
    }

    fn nodes<'n>(&self, node: &'n Node, kind: &'n str) -> impl Iterator<Item = &'n Node> + 'n {
        node.children.iter().filter_map(move |c| match c {
            Element::Node(n) if n.kind == kind => Some(n),
            _ => None,
        })
    }

    fn all_nodes<'n>(&self, node: &'n Node) -> impl Iterator<Item = &'n Node> + 'n {
        node.children.iter().filter_map(|c| match c {
            Element::Node(n) => Some(n),
            Element::Leaf(_) => None,
        })
    }

    fn node<'n>(&self, node: &'n Node, kind: &str) -> Result<&'n Node, Diagnostic> {
        node.children
            .iter()
            .find_map(|c| match c {
                Element::Node(n) if n.kind == kind => Some(n),
                _ => None,
            })
            .ok_or_else(|| self.shape(kind, node.span))
    }

    /// Leaves of `node` (direct children only) as (text, span).
    fn leaves(&self, node: &Node) -> Vec<(&'a str, Span)> {
        node.children
            .iter()
            .filter_map(|c| match c {
                Element::Leaf(l) => self
                    .cst
                    .tokens
                    .get(l.token)
                    .map(|t| (self.text(t.span), t.span)),
                Element::Node(_) => None,
            })
            .collect()
    }

    /// The `index`-th direct leaf of `node` as a name. Names are found by
    /// position, not by skipping keywords, because contextual words are
    /// valid names (`let let = 1`).
    fn leaf_name(&self, node: &Node, index: usize) -> Result<Name, Diagnostic> {
        self.leaves(node)
            .get(index)
            .map(|(t, span)| Name {
                text: t.to_string(),
                span: *span,
            })
            .ok_or_else(|| self.shape("identifier", node.span))
    }

    fn record(&self, node: &Node) -> Result<RecordAst, Diagnostic> {
        let name = self.leaf_name(node, 1)?;
        let mut fields = Vec::new();
        for field in self.nodes(node, "field-decl") {
            let fname = self.leaf_name(field, 0)?;
            let ty = self.pure_type(self.node(field, "pure-type")?)?;
            fields.push((fname, ty));
        }
        Ok(RecordAst {
            name,
            fields,
            span: node.span,
        })
    }

    fn function(&self, node: &Node) -> Result<FnAst, Diagnostic> {
        let name = self.leaf_name(node, 1)?;
        let mut params = Vec::new();
        for list in self.nodes(node, "fn-params") {
            for param in self.nodes(list, "fn-param") {
                let pname = self.leaf_name(param, 0)?;
                let ty = self.pure_type(self.node(param, "pure-type")?)?;
                params.push((pname, ty));
            }
        }
        let ret = self.pure_type(self.node(node, "pure-type")?)?;
        let body = self.block(self.node(node, "pure-block")?)?;
        Ok(FnAst {
            name,
            params,
            ret,
            body,
            span: node.span,
        })
    }

    fn pure_type(&self, node: &Node) -> Result<TypeAst, Diagnostic> {
        let name = self.leaf_name(node, 0)?;
        let bracket = self.leaves(node).iter().any(|(t, _)| *t == "[");
        let args = if bracket {
            Some(
                self.nodes(node, "pure-type")
                    .map(|n| self.pure_type(n))
                    .collect::<Result<Vec<_>, _>>()?,
            )
        } else {
            None
        };
        Ok(TypeAst {
            name,
            args,
            span: node.span,
        })
    }

    fn block(&self, node: &Node) -> Result<BlockAst, Diagnostic> {
        let mut stmts = Vec::new();
        for st in self.nodes(node, "statement") {
            let inner = self
                .all_nodes(st)
                .next()
                .ok_or_else(|| self.shape("statement", st.span))?;
            stmts.push(self.statement(inner)?);
        }
        // The block's span excludes the leading ':' and line end: it covers the statements.
        let span = match (stmts.first(), stmts.last()) {
            (Some(a), Some(b)) => Span::new(a.span.start, b.span.end),
            _ => node.span,
        };
        Ok(BlockAst { stmts, span })
    }

    fn keyword_span(&self, node: &Node) -> Span {
        self.leaves(node)
            .first()
            .map_or(Span::at(node.span.start), |(_, s)| *s)
    }

    /// A `let` or `return` statement's span without its line end: it ends with its expression.
    fn stmt_span(&self, node: &Node) -> Span {
        let end = self
            .all_nodes(node)
            .last()
            .map_or(node.span.end, |n| n.span.end);
        Span::new(node.span.start, end)
    }

    fn statement(&self, node: &Node) -> Result<StmtAst, Diagnostic> {
        let keyword = self.keyword_span(node);
        let kind = match node.kind.as_str() {
            "let-stmt" => StmtKind::Let {
                name: self.leaf_name(node, 1)?,
                value: self.expr(self.node(node, "expr")?)?,
            },
            "return-stmt" => StmtKind::Return(self.expr(self.node(node, "expr")?)?),
            "if-stmt" => {
                let blocks: Vec<&Node> = self.nodes(node, "pure-block").collect();
                let then = self.block(
                    blocks
                        .first()
                        .ok_or_else(|| self.shape("if-stmt", node.span))?,
                )?;
                let otherwise = match blocks.get(1) {
                    Some(b) => Some(self.block(b)?),
                    None => None,
                };
                StmtKind::If {
                    cond: self.expr(self.node(node, "expr")?)?,
                    then,
                    otherwise,
                }
            }
            "fork-stmt" => StmtKind::Fork(self.block(self.node(node, "pure-block")?)?),
            other => return Err(self.shape(other, node.span)),
        };
        let span = match &kind {
            StmtKind::If {
                then, otherwise, ..
            } => Span::new(node.span.start, otherwise.as_ref().unwrap_or(then).span.end),
            StmtKind::Fork(block) => Span::new(node.span.start, block.span.end),
            StmtKind::Let { .. } | StmtKind::Return(_) => self.stmt_span(node),
        };
        Ok(StmtAst {
            kind,
            span,
            keyword,
        })
    }

    /// Fold `operand { op operand }` to the left.
    fn fold(
        &self,
        node: &Node,
        operand: &str,
        op: impl Fn(&str) -> Option<BinOp>,
    ) -> Result<ExprAst, Diagnostic> {
        let mut acc: Option<ExprAst> = None;
        let mut pending: Option<BinOp> = None;
        // A binary expression spans its operands' syntax nodes, so a
        // parenthesised operand keeps its parentheses inside the span.
        let mut start = node.span.start;
        for child in &node.children {
            match child {
                Element::Node(n) if n.kind == operand => {
                    let rhs = self.dispatch(n)?;
                    if acc.is_none() {
                        start = n.span.start;
                    }
                    acc = Some(match (acc, pending.take()) {
                        (None, _) => rhs,
                        (Some(lhs), Some(o)) => {
                            let span = Span::new(start, n.span.end);
                            self.expr_node(ExprKind::Binary(o, Box::new(lhs), Box::new(rhs)), span)?
                        }
                        (Some(_), None) => return Err(self.shape(operand, n.span)),
                    });
                }
                Element::Node(n) if n.kind == "compare-op" => {
                    let text = self.leaves(n).first().map_or("", |(t, _)| *t);
                    pending = op(text);
                }
                Element::Leaf(l) => {
                    let text = self
                        .cst
                        .tokens
                        .get(l.token)
                        .map_or("", |t| self.text(t.span));
                    if let Some(o) = op(text) {
                        pending = Some(o);
                    }
                }
                Element::Node(n) => return Err(self.shape(&n.kind, n.span)),
            }
        }
        acc.ok_or_else(|| self.shape(&node.kind, node.span))
    }

    fn dispatch(&self, node: &Node) -> Result<ExprAst, Diagnostic> {
        match node.kind.as_str() {
            "expr" => self.expr(node),
            "conjunction" => self.fold(node, "comparison", |t| (t == "and").then_some(BinOp::And)),
            "comparison" => self.fold(node, "sum", |t| match t {
                "<" => Some(BinOp::Lt),
                "<=" => Some(BinOp::Le),
                ">" => Some(BinOp::Gt),
                ">=" => Some(BinOp::Ge),
                "==" => Some(BinOp::Eq),
                "!=" => Some(BinOp::Ne),
                _ => None,
            }),
            "sum" => self.fold(node, "product", |t| match t {
                "+" => Some(BinOp::Add),
                "-" => Some(BinOp::Sub),
                _ => None,
            }),
            "product" => self.fold(node, "unary", |t| (t == "*").then_some(BinOp::Mul)),
            "unary" => self.unary(node),
            "primary" => self.primary(node),
            other => Err(self.shape(other, node.span)),
        }
    }

    pub fn expr(&self, node: &Node) -> Result<ExprAst, Diagnostic> {
        self.fold(node, "conjunction", |t| (t == "or").then_some(BinOp::Or))
    }

    fn unary(&self, node: &Node) -> Result<ExprAst, Diagnostic> {
        if let Some(inner) = self.nodes(node, "unary").next() {
            let operand = self.unary(inner)?;
            return self.expr_node(ExprKind::Neg(Box::new(operand)), node.span);
        }
        self.primary(self.node(node, "primary")?)
    }

    fn primary(&self, node: &Node) -> Result<ExprAst, Diagnostic> {
        let child = self
            .all_nodes(node)
            .next()
            .ok_or_else(|| self.shape("primary", node.span))?;
        match child.kind.as_str() {
            "UINT" => {
                let text = self.text(child.span).to_string();
                self.expr_node(ExprKind::Int(text), child.span)
            }
            // "(", expr, ")": the inner expression keeps its own span.
            "expr" => self.expr(child),
            "list-literal" => {
                let items = self
                    .nodes(child, "expr")
                    .map(|n| self.expr(n))
                    .collect::<Result<Vec<_>, _>>()?;
                self.expr_node(ExprKind::List(items), child.span)
            }
            "name-expr" => self.name_expr(child),
            other => Err(self.shape(other, child.span)),
        }
    }

    fn name_expr(&self, node: &Node) -> Result<ExprAst, Diagnostic> {
        let mut prefix = None;
        let mut parts = Vec::new();
        let mut call = None;
        let mut in_call = false;
        for child in &node.children {
            match child {
                Element::Leaf(l) => {
                    let Some(token) = self.cst.tokens.get(l.token) else {
                        continue;
                    };
                    let text = self.text(token.span);
                    match text {
                        "(" => {
                            in_call = true;
                            call = Some(Vec::new());
                        }
                        ")" | "." => {}
                        word if !in_call => parts.push(Name {
                            text: word.to_string(),
                            span: token.span,
                        }),
                        _ => {}
                    }
                }
                Element::Node(n) if n.kind == "prefixed" => {
                    // `word X.y`: `parts` holds the word; the prefixed node the first two names.
                    let word = parts.pop().ok_or_else(|| self.shape("prefixed", n.span))?;
                    if word.text != "await" {
                        return Err(Diagnostic::new(
                            PURE_SYNTAX_CODE,
                            "syntax",
                            format!(
                                "'{}' before a qualified name is not P0 syntax; only 'await' is recognised there, and pure code rejects it (P0-EFFECT-2).",
                                word.text
                            ),
                            word.span,
                        ));
                    }
                    prefix = Some(word);
                    for (text, span) in self.leaves(n) {
                        if text != "." {
                            parts.push(Name {
                                text: text.to_string(),
                                span,
                            });
                        }
                    }
                }
                Element::Node(n) if n.kind == "call-args" => {
                    let mut args = Vec::new();
                    for arg in self.nodes(n, "call-arg") {
                        let exprs: Vec<&Node> = self.nodes(arg, "expr").collect();
                        let (label, value) = match exprs.as_slice() {
                            [value] => (None, self.expr(value)?),
                            [label, value] => (Some(self.expr(label)?), self.expr(value)?),
                            _ => return Err(self.shape("call-arg", arg.span)),
                        };
                        args.push(ArgAst {
                            label,
                            value,
                            span: arg.span,
                        });
                    }
                    call = Some(args);
                }
                Element::Node(n) => return Err(self.shape(&n.kind, n.span)),
            }
        }
        if parts.is_empty() {
            return Err(self.shape("name-expr", node.span));
        }
        self.expr_node(
            ExprKind::Path {
                prefix,
                parts,
                call,
            },
            node.span,
        )
    }
}
