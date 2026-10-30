// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The P0 static rules, checked in the order of `pure.rst` ("Checking order"):
//!
//! 1. top-level names (`P0-DECL-1`, E501);
//! 2. records in file order: duplicate fields (`P0-DECL-2`, E502) and field
//!    types (`P0-TYPE-1`, E504);
//! 3. recursive records (`P0-DECL-3`, E503);
//! 4. function signatures in file order: parameter names (`P0-NAME-2`, E506)
//!    and types, then the result type (`P0-TYPE-1`, E504);
//! 5. function bodies in file order: first the block structure (`P0-FORK-1`
//!    E514, `P0-PATH-1` E515), then statements and expressions in evaluation
//!    order (E505 to E513);
//! 6. mutual recursion (`P0-REC-1`, E516).
//!
//! The first violation is reported. Signatures are registered before any body
//! is checked, and every body is checked whether or not it is called
//! (`P0-DECL-4`).

use crate::ast::{self, ArgAst, BinOp, ExprAst, ExprKind, FileAst, Item, Name, StmtKind, TypeAst};
use crate::typed::*;
use std::collections::BTreeMap;
use weave_syntax::{Diagnostic, Span};

/// Built-in type names and value names (`P0-DECL-1`, `P0-NAME-2`). P0 has one
/// namespace for types, functions, records, primitives and local bindings.
pub const BUILTIN_TYPES: [&str; 3] = ["Int", "Bool", "List"];
pub const BUILTIN_CONSTANTS: [&str; 2] = ["true", "false"];

pub fn is_builtin(name: &str) -> bool {
    BUILTIN_TYPES.contains(&name)
        || BUILTIN_CONSTANTS.contains(&name)
        || Prim::from_name(name).is_some()
}

fn err(code: &'static str, message: impl Into<String>, span: Span) -> Diagnostic {
    Diagnostic::new(code, "static", message, span)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Global {
    Record(usize),
    Function(usize),
}

struct Local {
    name: String,
    slot: usize,
    ty: Ty,
}

struct Checker<'a> {
    globals: BTreeMap<&'a str, Global>,
    records: Vec<Record>,
    signatures: Vec<(Vec<(String, Ty)>, Ty)>,
    scopes: Vec<Vec<Local>>,
    slots: usize,
    /// Calls to user functions from the body being checked: (callee, span).
    calls: Vec<(usize, Span)>,
}

/// Check a lowered file; `source` is kept in the program for diagnostics.
pub fn check_program(file: &FileAst, source: &str) -> Result<Program, Diagnostic> {
    let mut c = Checker {
        globals: BTreeMap::new(),
        records: Vec::new(),
        signatures: Vec::new(),
        scopes: Vec::new(),
        slots: 0,
        calls: Vec::new(),
    };
    let record_asts: Vec<&ast::RecordAst> = file
        .items
        .iter()
        .filter_map(|i| match i {
            Item::Record(r) => Some(r),
            Item::Fn(_) => None,
        })
        .collect();
    let fn_asts: Vec<&ast::FnAst> = file
        .items
        .iter()
        .filter_map(|i| match i {
            Item::Fn(f) => Some(f),
            Item::Record(_) => None,
        })
        .collect();

    // 1. Top-level names.
    let (mut nrec, mut nfn) = (0, 0);
    for item in &file.items {
        let (name, global) = match item {
            Item::Record(r) => {
                nrec += 1;
                (&r.name, Global::Record(nrec - 1))
            }
            Item::Fn(f) => {
                nfn += 1;
                (&f.name, Global::Function(nfn - 1))
            }
        };
        if is_builtin(&name.text) {
            return Err(err(
                "E501",
                format!(
                    "'{}' is a built-in name; a function or record cannot be named like it.",
                    name.text
                ),
                name.span,
            ));
        }
        if c.globals.insert(name.text.as_str(), global).is_some() {
            return Err(err(
                "E501",
                format!("'{}' is declared more than once in this file.", name.text),
                name.span,
            ));
        }
    }

    // 2. Records: placeholders first so field types can name any record.
    for r in &record_asts {
        c.records.push(Record {
            name: r.name.text.clone(),
            fields: Vec::new(),
            span: r.span,
            name_span: r.name.span,
        });
    }
    for (i, r) in record_asts.iter().enumerate() {
        let mut fields: Vec<(String, Ty)> = Vec::new();
        for (fname, fty) in &r.fields {
            if fields.iter().any(|(n, _)| *n == fname.text) {
                return Err(err(
                    "E502",
                    format!(
                        "Record '{}' declares the field '{}' more than once.",
                        r.name.text, fname.text
                    ),
                    fname.span,
                ));
            }
            let ty = c.resolve_type(fty)?;
            fields.push((fname.text.clone(), ty));
        }
        if let Some(rec) = c.records.get_mut(i) {
            rec.fields = fields;
        }
    }

    // 3. Recursive records.
    for (i, r) in record_asts.iter().enumerate() {
        if c.record_reaches(i, i) {
            return Err(err(
                "E503",
                format!(
                    "Record '{}' contains itself through its field types; P0 has no recursive records.",
                    r.name.text
                ),
                r.name.span,
            ));
        }
    }

    // 4. Signatures.
    for f in &fn_asts {
        let mut params: Vec<(String, Ty)> = Vec::new();
        for (pname, pty) in &f.params {
            if params.iter().any(|(n, _)| *n == pname.text) {
                return Err(err(
                    "E506",
                    format!(
                        "Parameter '{}' of '{}' is declared twice.",
                        pname.text, f.name.text
                    ),
                    pname.span,
                ));
            }
            c.fresh_name(pname)?;
            params.push((pname.text.clone(), c.resolve_type(pty)?));
        }
        let ret = c.resolve_type(&f.ret)?;
        c.signatures.push((params, ret));
    }

    // 5. Bodies.
    let mut functions = Vec::new();
    let mut graph: Vec<Vec<(usize, Span)>> = Vec::new();
    for (index, f) in fn_asts.iter().enumerate() {
        structure(&f.body)?;
        let (params, ret) = c.signatures.get(index).cloned().unwrap_or_default_sig();
        c.scopes = vec![Vec::new()];
        c.slots = 0;
        c.calls = Vec::new();
        for (name, ty) in &params {
            c.bind(name, ty.clone());
        }
        let body = c.block(&f.body, &ret)?;
        let mut calls = std::mem::take(&mut c.calls);
        calls.sort_by_key(|(_, span)| span.start);
        graph.push(calls);
        functions.push(Function {
            name: f.name.text.clone(),
            params,
            ret,
            body,
            locals: c.slots,
            span: f.span,
            name_span: f.name.span,
        });
    }

    // 6. Mutual recursion.
    let n = graph.len();
    let reach: Vec<Vec<bool>> = (0..n).map(|f| reachable(&graph, f)).collect();
    let reaches = |a: usize, b: usize| reach.get(a).and_then(|r| r.get(b)).copied() == Some(true);
    for (f, calls) in graph.iter().enumerate() {
        for (g, span) in calls {
            if *g != f && reaches(*g, f) {
                let fname = functions.get(f).map_or("?", |x| x.name.as_str());
                let gname = functions.get(*g).map_or("?", |x| x.name.as_str());
                return Err(err(
                    "E516",
                    format!(
                        "'{fname}' calls '{gname}', which calls '{fname}' again: only direct self-recursion is allowed."
                    ),
                    *span,
                ));
            }
        }
    }

    Ok(Program {
        source: source.to_string(),
        records: c.records,
        functions,
    })
}

trait DefaultSig {
    fn unwrap_or_default_sig(self) -> (Vec<(String, Ty)>, Ty);
}

impl DefaultSig for Option<(Vec<(String, Ty)>, Ty)> {
    fn unwrap_or_default_sig(self) -> (Vec<(String, Ty)>, Ty) {
        self.unwrap_or((Vec::new(), Ty::Int))
    }
}

/// Functions reachable from `from` by one or more calls.
fn reachable(graph: &[Vec<(usize, Span)>], from: usize) -> Vec<bool> {
    let mut seen = vec![false; graph.len()];
    let mut work: Vec<usize> = graph
        .get(from)
        .map(|c| c.iter().map(|(g, _)| *g).collect())
        .unwrap_or_default();
    while let Some(g) = work.pop() {
        if let Some(s) = seen.get_mut(g)
            && !*s
        {
            *s = true;
            if let Some(next) = graph.get(g) {
                work.extend(next.iter().map(|(h, _)| *h));
            }
        }
    }
    seen
}

/// `P0-FORK-1` and `P0-PATH-1`, walking the body in source order.
fn structure(block: &ast::BlockAst) -> Result<(), Diagnostic> {
    let mut previous_terminal = false;
    for stmt in &block.stmts {
        if previous_terminal {
            return Err(err(
                "E515",
                "Statement after a return or a terminal if/else: it can never run.",
                stmt.span,
            ));
        }
        match &stmt.kind {
            StmtKind::Fork(_) => {
                return Err(err(
                    "E514",
                    "fork is not P0: pure code is sequential.",
                    stmt.keyword,
                ));
            }
            StmtKind::If {
                then, otherwise, ..
            } => {
                structure(then)?;
                match otherwise {
                    Some(b) => structure(b)?,
                    None => {
                        return Err(err(
                            "E515",
                            "if without else: every path must end in return.",
                            stmt.keyword,
                        ));
                    }
                }
                previous_terminal = true;
            }
            StmtKind::Return(_) => previous_terminal = true,
            StmtKind::Let { .. } => {}
        }
    }
    if previous_terminal {
        Ok(())
    } else {
        let at = block.stmts.last().map_or(block.span, |s| s.span);
        Err(err(
            "E515",
            "The block does not end in return or a terminal if/else.",
            at,
        ))
    }
}

impl<'a> Checker<'a> {
    fn record_reaches(&self, from: usize, target: usize) -> bool {
        fn mentions(ty: &Ty, out: &mut Vec<usize>) {
            match ty {
                Ty::Record(i) => out.push(*i),
                Ty::List(t) => mentions(t, out),
                Ty::Int | Ty::Bool => {}
            }
        }
        let mut seen = vec![false; self.records.len()];
        let mut work = Vec::new();
        if let Some(r) = self.records.get(from) {
            for (_, t) in &r.fields {
                mentions(t, &mut work);
            }
        }
        while let Some(i) = work.pop() {
            if i == target {
                return true;
            }
            if let Some(s) = seen.get_mut(i)
                && !*s
            {
                *s = true;
                if let Some(r) = self.records.get(i) {
                    for (_, t) in &r.fields {
                        mentions(t, &mut work);
                    }
                }
            }
        }
        false
    }

    fn resolve_type(&self, t: &TypeAst) -> Result<Ty, Diagnostic> {
        let name = t.name.text.as_str();
        match (name, &t.args) {
            ("Int", None) => Ok(Ty::Int),
            ("Bool", None) => Ok(Ty::Bool),
            ("List", Some(args)) if args.len() == 1 => match args.first() {
                Some(inner) => Ok(Ty::list(self.resolve_type(inner)?)),
                None => Err(err("E504", "List needs one element type.", t.span)),
            },
            ("List", _) => Err(err(
                "E504",
                "List takes exactly one element type, as in List[Int].",
                t.span,
            )),
            ("Int" | "Bool", Some(_)) => Err(err(
                "E504",
                format!("{name} takes no type arguments."),
                t.span,
            )),
            _ => match (self.globals.get(name), &t.args) {
                (Some(Global::Record(i)), None) => Ok(Ty::Record(*i)),
                (Some(Global::Record(_)), Some(_)) => Err(err(
                    "E504",
                    format!("Record type '{name}' takes no type arguments."),
                    t.span,
                )),
                (_, Some(_)) => Err(err(
                    "E504",
                    format!(
                        "'{name}[...]' is an indexed nominal type, such as a linear handle; pure code cannot receive, return or hold handles."
                    ),
                    t.span,
                )),
                _ => Err(err(
                    "E504",
                    format!(
                        "Unknown type '{name}': P0 types are Int, Bool, List[T] and records declared in this file."
                    ),
                    t.span,
                )),
            },
        }
    }

    fn lookup(&self, name: &str) -> Option<&Local> {
        self.scopes
            .iter()
            .rev()
            .flat_map(|s| s.iter().rev())
            .find(|l| l.name == name)
    }

    /// `P0-NAME-2`: a new local name is not in scope, not top-level, not built-in.
    fn fresh_name(&self, name: &Name) -> Result<(), Diagnostic> {
        let text = name.text.as_str();
        let clash = if self.lookup(text).is_some() {
            Some("a binding already in scope")
        } else if self.globals.contains_key(text) {
            Some("a function or record of this file")
        } else if is_builtin(text) {
            Some("a built-in name")
        } else {
            None
        };
        match clash {
            Some(what) => Err(err(
                "E506",
                format!("'{text}' would shadow {what}; P0 has no shadowing."),
                name.span,
            )),
            None => Ok(()),
        }
    }

    fn bind(&mut self, name: &str, ty: Ty) -> usize {
        let slot = self.slots;
        self.slots += 1;
        if let Some(scope) = self.scopes.last_mut() {
            scope.push(Local {
                name: name.to_string(),
                slot,
                ty,
            });
        }
        slot
    }

    fn spell(&self, ty: &Ty) -> String {
        ty.spell(&self.records)
    }

    fn block(&mut self, block: &ast::BlockAst, ret: &Ty) -> Result<Block, Diagnostic> {
        self.scopes.push(Vec::new());
        let mut lets = Vec::new();
        let mut end = None;
        for stmt in &block.stmts {
            match &stmt.kind {
                StmtKind::Let { name, value } => {
                    let v = self.synth(value, None)?;
                    self.fresh_name(name)?;
                    let slot = self.bind(&name.text, v.ty.clone());
                    lets.push((slot, v));
                }
                StmtKind::Return(value) => {
                    end = Some(Terminal::Return(self.check(value, ret)?));
                }
                StmtKind::If {
                    cond,
                    then,
                    otherwise,
                } => {
                    let cond = self.check(cond, &Ty::Bool)?;
                    let then = self.block(then, ret)?;
                    let otherwise = match otherwise {
                        Some(b) => self.block(b, ret)?,
                        None => return Err(err("E515", "if without else.", stmt.keyword)),
                    };
                    end = Some(Terminal::If {
                        cond,
                        then,
                        otherwise,
                    });
                }
                StmtKind::Fork(_) => return Err(err("E514", "fork is not P0.", stmt.keyword)),
            }
        }
        self.scopes.pop();
        match end {
            Some(end) => Ok(Block {
                lets,
                end: Box::new(end),
            }),
            None => Err(err(
                "E515",
                "The block does not end in return or a terminal if/else.",
                block.span,
            )),
        }
    }

    /// Check `e` against `expected` (`P0-TYPE-2`, `P0-TYPE-3`).
    fn check(&mut self, e: &ExprAst, expected: &Ty) -> Result<Expr, Diagnostic> {
        let typed = self.synth(e, Some(expected))?;
        if typed.ty == *expected {
            Ok(typed)
        } else {
            Err(err(
                "E510",
                format!(
                    "Expected {}, found {}.",
                    self.spell(expected),
                    self.spell(&typed.ty)
                ),
                e.span,
            ))
        }
    }

    fn mk(kind: ExprK, ty: Ty, span: Span) -> Expr {
        Expr { kind, ty, span }
    }

    /// The type of `e`; `expected`, where present, types `[]`, list elements and
    /// `cons` (`P0-TYPE-3`). The caller compares the result with `expected`.
    fn synth(&mut self, e: &ExprAst, expected: Option<&Ty>) -> Result<Expr, Diagnostic> {
        match &e.kind {
            ExprKind::Int(text) => Ok(Self::mk(ExprK::Int(text.clone()), Ty::Int, e.span)),
            ExprKind::List(items) => self.list(items, expected, e.span),
            ExprKind::Neg(x) => {
                let x = self.check(x, &Ty::Int)?;
                Ok(Self::mk(ExprK::Neg(Box::new(x)), Ty::Int, e.span))
            }
            ExprKind::Binary(op, l, r) => self.binary(*op, l, r, e.span),
            ExprKind::Path {
                prefix,
                parts,
                call,
            } => {
                if prefix.is_some() {
                    return Err(err(
                        "E513",
                        "await in pure code: pure code does not wait for operations.",
                        e.span,
                    ));
                }
                match call {
                    Some(args) => self.call(parts, args, expected, e.span),
                    None => self.path(parts, e.span),
                }
            }
        }
    }

    fn list(
        &mut self,
        items: &[ExprAst],
        expected: Option<&Ty>,
        span: Span,
    ) -> Result<Expr, Diagnostic> {
        match expected {
            Some(Ty::List(element)) => {
                let element = (**element).clone();
                let typed = items
                    .iter()
                    .map(|i| self.check(i, &element))
                    .collect::<Result<Vec<_>, _>>()?;
                Ok(Self::mk(ExprK::List(typed), Ty::list(element), span))
            }
            Some(other) if items.is_empty() => Err(err(
                "E510",
                format!("Expected {}, found a list.", self.spell(other)),
                span,
            )),
            _ => {
                let Some((first, rest)) = items.split_first() else {
                    return Err(err(
                        "E511",
                        "[] needs an expected list type here; use it where a List type is expected.",
                        span,
                    ));
                };
                let first = self.synth(first, None)?;
                let element = first.ty.clone();
                let mut typed = vec![first];
                for i in rest {
                    typed.push(self.check(i, &element)?);
                }
                Ok(Self::mk(ExprK::List(typed), Ty::list(element), span))
            }
        }
    }

    fn binary(
        &mut self,
        op: BinOp,
        l: &ExprAst,
        r: &ExprAst,
        span: Span,
    ) -> Result<Expr, Diagnostic> {
        let b = Box::new;
        Ok(match op {
            BinOp::Add | BinOp::Sub | BinOp::Mul => {
                let (l, r) = (self.check(l, &Ty::Int)?, self.check(r, &Ty::Int)?);
                let a = match op {
                    BinOp::Add => ArithOp::Add,
                    BinOp::Sub => ArithOp::Sub,
                    _ => ArithOp::Mul,
                };
                Self::mk(ExprK::Arith(a, b(l), b(r)), Ty::Int, span)
            }
            BinOp::Lt | BinOp::Le | BinOp::Gt | BinOp::Ge => {
                let (l, r) = (self.check(l, &Ty::Int)?, self.check(r, &Ty::Int)?);
                let c = match op {
                    BinOp::Lt => CmpOp::Lt,
                    BinOp::Le => CmpOp::Le,
                    BinOp::Gt => CmpOp::Gt,
                    _ => CmpOp::Ge,
                };
                Self::mk(ExprK::Compare(c, b(l), b(r)), Ty::Bool, span)
            }
            BinOp::Eq | BinOp::Ne => {
                let lt = self.synth(l, None)?;
                if lt.ty != Ty::Int && lt.ty != Ty::Bool {
                    return Err(err(
                        "E510",
                        format!(
                            "{} compares Int or Bool values, not {}.",
                            op.spelling(),
                            self.spell(&lt.ty)
                        ),
                        l.span,
                    ));
                }
                let ty = lt.ty.clone();
                let rt = self.check(r, &ty)?;
                let c = if op == BinOp::Eq {
                    CmpOp::Eq
                } else {
                    CmpOp::Ne
                };
                Self::mk(ExprK::Compare(c, b(lt), b(rt)), Ty::Bool, span)
            }
            BinOp::And | BinOp::Or => {
                let (l, r) = (self.check(l, &Ty::Bool)?, self.check(r, &Ty::Bool)?);
                let k = if op == BinOp::And {
                    ExprK::And(b(l), b(r))
                } else {
                    ExprK::Or(b(l), b(r))
                };
                Self::mk(k, Ty::Bool, span)
            }
        })
    }

    /// A name or field access without a call.
    fn path(&mut self, parts: &[Name], span: Span) -> Result<Expr, Diagnostic> {
        let Some((root, fields)) = parts.split_first() else {
            return Err(err("E505", "Empty name.", span));
        };
        let mut current = match self.lookup(&root.text) {
            Some(local) => Self::mk(ExprK::Local(local.slot), local.ty.clone(), root.span),
            None if fields.is_empty() && BUILTIN_CONSTANTS.contains(&root.text.as_str()) => {
                Self::mk(ExprK::Bool(root.text == "true"), Ty::Bool, root.span)
            }
            None => {
                let what = if self.globals.contains_key(root.text.as_str()) {
                    format!(
                        "'{}' is a function or record of this file, not a value; functions are not values in P0.",
                        root.text
                    )
                } else if is_builtin(&root.text) {
                    format!("'{}' is a built-in name, not a value.", root.text)
                } else {
                    format!("Unknown name '{}'.", root.text)
                };
                return Err(err("E505", what, root.span));
            }
        };
        for field in fields {
            let Ty::Record(r) = current.ty else {
                return Err(err(
                    "E509",
                    format!(
                        "'.{}' needs a record, but the value has type {}.",
                        field.text,
                        self.spell(&current.ty)
                    ),
                    field.span,
                ));
            };
            let record = self.records.get(r);
            let found = record.and_then(|rec| {
                rec.fields
                    .iter()
                    .position(|(n, _)| *n == field.text)
                    .and_then(|i| rec.fields.get(i).map(|(_, t)| (i, t.clone())))
            });
            let Some((index, ty)) = found else {
                return Err(err(
                    "E509",
                    format!(
                        "Record '{}' has no field '{}'.",
                        record.map_or("?", |rec| rec.name.as_str()),
                        field.text
                    ),
                    field.span,
                ));
            };
            let s = Span::new(current.span.start, field.span.end);
            current = Self::mk(ExprK::Field(Box::new(current), index), ty, s);
        }
        Ok(current)
    }

    fn call(
        &mut self,
        parts: &[Name],
        args: &[ArgAst],
        expected: Option<&Ty>,
        span: Span,
    ) -> Result<Expr, Diagnostic> {
        if parts.len() > 1 {
            let name: Vec<&str> = parts.iter().map(|p| p.text.as_str()).collect();
            return Err(err(
                "E512",
                format!(
                    "'{}(...)' is a qualified call: a net, foreign or flow operation, which pure code cannot perform.",
                    name.join(".")
                ),
                span,
            ));
        }
        let Some(target) = parts.first() else {
            return Err(err("E507", "Empty call target.", span));
        };
        let name = target.text.as_str();
        if let Some(prim) = Prim::from_name(name) {
            self.positional(name, args, prim.arity(), span)?;
            return self.primitive(prim, args, expected, span);
        }
        match self.globals.get(name).copied() {
            Some(Global::Function(f)) => {
                let (params, ret) = self.signatures.get(f).cloned().unwrap_or_default_sig();
                self.positional(name, args, params.len(), span)?;
                let mut typed = Vec::new();
                for (arg, (_, ty)) in args.iter().zip(params.iter()) {
                    typed.push(self.check(&arg.value, ty)?);
                }
                self.calls.push((f, span));
                Ok(Self::mk(ExprK::Call(f, typed), ret, span))
            }
            Some(Global::Record(r)) => self.construct(r, args, span),
            None => Err(err(
                "E507",
                if self.lookup(name).is_some() {
                    format!("'{name}' is a local value, not a function.")
                } else {
                    format!("Unknown function '{name}'.")
                },
                target.span,
            )),
        }
    }

    fn positional(
        &self,
        name: &str,
        args: &[ArgAst],
        arity: usize,
        span: Span,
    ) -> Result<(), Diagnostic> {
        if let Some(arg) = args.iter().find(|a| a.label.is_some()) {
            return Err(err(
                "E507",
                format!("'{name}' takes positional arguments; named arguments construct records."),
                arg.span,
            ));
        }
        if args.len() != arity {
            return Err(err(
                "E507",
                format!(
                    "'{name}' takes {arity} argument{}, not {}.",
                    if arity == 1 { "" } else { "s" },
                    args.len()
                ),
                span,
            ));
        }
        Ok(())
    }

    fn primitive(
        &mut self,
        prim: Prim,
        args: &[ArgAst],
        expected: Option<&Ty>,
        span: Span,
    ) -> Result<Expr, Diagnostic> {
        let arg = |i: usize| args.get(i).map(|a| &a.value);
        let mut typed = Vec::new();
        let ty = match prim {
            Prim::Div | Prim::Mod => {
                for i in 0..2 {
                    if let Some(a) = arg(i) {
                        typed.push(self.check(a, &Ty::Int)?);
                    }
                }
                Ty::Int
            }
            Prim::Not => {
                if let Some(a) = arg(0) {
                    typed.push(self.check(a, &Ty::Bool)?);
                }
                Ty::Bool
            }
            Prim::Length | Prim::IsEmpty | Prim::Head | Prim::Tail => {
                let Some(a) = arg(0) else {
                    return Err(err("E507", "Missing argument.", span));
                };
                let list = self.synth(a, None)?;
                let Ty::List(element) = list.ty.clone() else {
                    return Err(err(
                        "E510",
                        format!(
                            "{} needs a list, found {}.",
                            prim.name(),
                            self.spell(&list.ty)
                        ),
                        a.span,
                    ));
                };
                let ty = match prim {
                    Prim::Length => Ty::Int,
                    Prim::IsEmpty => Ty::Bool,
                    Prim::Head => *element,
                    _ => list.ty.clone(),
                };
                typed.push(list);
                ty
            }
            Prim::Cons => {
                let (Some(x), Some(xs)) = (arg(0), arg(1)) else {
                    return Err(err("E507", "cons takes 2 arguments.", span));
                };
                match expected {
                    Some(Ty::List(element)) => {
                        let element = (**element).clone();
                        typed.push(self.check(x, &element)?);
                        typed.push(self.check(xs, &Ty::list(element.clone()))?);
                        Ty::list(element)
                    }
                    _ => {
                        let head = self.synth(x, None)?;
                        let element = head.ty.clone();
                        typed.push(head);
                        typed.push(self.check(xs, &Ty::list(element.clone()))?);
                        Ty::list(element)
                    }
                }
            }
        };
        Ok(Self::mk(ExprK::Prim(prim, typed), ty, span))
    }

    fn construct(&mut self, r: usize, args: &[ArgAst], span: Span) -> Result<Expr, Diagnostic> {
        let (rname, fields) = match self.records.get(r) {
            Some(rec) => (rec.name.clone(), rec.fields.clone()),
            None => return Err(err("E507", "Unknown record.", span)),
        };
        let mut labels: Vec<(usize, &ArgAst)> = Vec::new();
        for arg in args {
            let Some(label) = &arg.label else {
                return Err(err(
                    "E507",
                    format!(
                        "Record '{rname}' is constructed with named arguments, as in {rname}(field: value)."
                    ),
                    arg.span,
                ));
            };
            let Some(name) = label.as_plain_name() else {
                return Err(err(
                    "E507",
                    "Before ':' a record construction names a field.",
                    label.span,
                ));
            };
            let Some(index) = fields.iter().position(|(n, _)| *n == name.text) else {
                return Err(err(
                    "E508",
                    format!("Record '{rname}' has no field '{}'.", name.text),
                    name.span,
                ));
            };
            if labels.iter().any(|(i, _)| *i == index) {
                return Err(err(
                    "E508",
                    format!("Field '{}' is given more than once.", name.text),
                    name.span,
                ));
            }
            labels.push((index, arg));
        }
        let missing: Vec<&str> = fields
            .iter()
            .enumerate()
            .filter(|(i, _)| !labels.iter().any(|(j, _)| j == i))
            .map(|(_, (n, _))| n.as_str())
            .collect();
        if !missing.is_empty() {
            return Err(err(
                "E508",
                format!(
                    "Record '{rname}' construction is missing field{} {}.",
                    if missing.len() == 1 { "" } else { "s" },
                    missing.join(", ")
                ),
                span,
            ));
        }
        let mut typed = Vec::new();
        for (index, arg) in labels {
            let ty = fields.get(index).map_or(Ty::Int, |(_, t)| t.clone());
            typed.push((index, self.check(&arg.value, &ty)?));
        }
        Ok(Self::mk(ExprK::Construct(r, typed), Ty::Record(r), span))
    }
}
