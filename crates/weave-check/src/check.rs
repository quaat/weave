// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The P0 static rules, checked in the order of `pure.rst` ("Checking order"):
//!
//! 1. top-level names (`P0-DECL-1`, E501);
//! 2. records in file order: duplicate fields (`P0-DECL-2`, E502) and field
//!    types (`P0-TYPE-1`, E504);
//! 3. recursive records (`P0-DECL-3`, E503), then record type depth (E500,
//!    stage `limit`, [`TYPE_DEPTH_LIMIT`]);
//! 4. function signatures in file order: parameter names (`P0-NAME-2`, E506)
//!    and types, then the result type (`P0-TYPE-1`, E504), each type's depth
//!    checked after it is resolved (E500 `limit`);
//! 5. function bodies in file order: first the block structure (`P0-FORK-1`
//!    E514, `P0-PATH-1` E515), then statements and expressions in evaluation
//!    order (E505 to E513), each expression's type depth checked when its
//!    type is known (E500 `limit`);
//! 6. mutual recursion (`P0-REC-1`, E516).
//!
//! The first violation is reported. Signatures are registered before any body
//! is checked, and every body is checked whether or not it is called
//! (`P0-DECL-4`).
//!
//! A program of several modules (modules-1, `chapters/names.rst`) is checked
//! module by module, each after the modules it imports ([`Builder`]); within a
//! module the imports are checked after step 1, and the export rule after step
//! 4 (`MOD-CHECK-1`). Records and functions of all modules share one index
//! space, so an imported name resolves to the declaration itself.

use crate::ast::{self, ArgAst, BinOp, ExprAst, ExprKind, FileAst, Item, Name, StmtKind, TypeAst};
use crate::typed::*;
use std::collections::BTreeMap;
use weave_syntax::FileId;
use weave_syntax::{Diagnostic, Span};

/// Built-in type names and value names (`P0-DECL-1`, `P0-NAME-2`). P0 has one
/// namespace for types, functions, records, primitives and local bindings.
pub const BUILTIN_TYPES: [&str; 3] = ["Int", "Bool", "List"];
pub const BUILTIN_CONSTANTS: [&str; 2] = ["true", "false"];

/// Largest type depth (`pure.rst`, "Nesting limits"): `Int` and `Bool` are 1,
/// `List[T]` is one more than `T`, a record one more than its deepest field
/// type. It applies to every record, every written type and the type of every
/// expression. A value is never deeper than its type (records are not
/// recursive, and a list's length is walked iteratively), so this bounds every
/// recursive walk over values: encoding, printing, decoding and dropping.
pub const TYPE_DEPTH_LIMIT: usize = 64;

fn type_limit(span: Span) -> Diagnostic {
    Diagnostic::new(
        weave_syntax::diagnostic::PURE_SYNTAX_CODE,
        "limit",
        format!("Type nesting exceeds the P0 type depth limit of {TYPE_DEPTH_LIMIT}."),
        span,
    )
    .with_detail(
        "limit",
        weave_syntax::json::Value::from_usize(TYPE_DEPTH_LIMIT),
    )
}

/// The record a type ends in, through any `List` wrappers.
fn base_record(ty: &Ty) -> Option<usize> {
    let mut t = ty;
    loop {
        match t {
            Ty::List(inner) => t = inner,
            Ty::Record(i) => return Some(*i),
            Ty::Int | Ty::Bool => return None,
        }
    }
}

/// Depth of `ty`, given the depths of the records (iterative).
fn ty_depth(ty: &Ty, records: &[usize]) -> usize {
    ty_depth_with(ty, |i| records.get(i).copied().unwrap_or(1))
}

fn ty_depth_with(ty: &Ty, record: impl Fn(usize) -> usize) -> usize {
    let mut lists = 0;
    let mut t = ty;
    loop {
        match t {
            Ty::List(inner) => {
                lists += 1;
                t = inner;
            }
            Ty::Record(i) => return lists + record(*i),
            Ty::Int | Ty::Bool => return lists + 1,
        }
    }
}

/// The depth of every record from index `from` on, by an explicit-stack
/// post-order walk of the record graph, which is acyclic once `P0-DECL-3`
/// holds. `depths` holds the depths of the records before `from` (those of
/// modules checked earlier) and is extended to cover every record.
fn extend_record_depths(records: &[Record], depths: &mut Vec<usize>, from: usize) {
    let n = records.len();
    let known = depths.len().min(from);
    let mut depth: Vec<Option<usize>> = depths.iter().take(known).copied().map(Some).collect();
    depth.resize(n, None);
    for start in known..n {
        let mut stack = vec![start];
        while let Some(&i) = stack.last() {
            if depth.get(i).copied().flatten().is_some() || stack.len() > n + 1 {
                stack.pop();
                continue;
            }
            let fields = records.get(i).map_or(&[][..], |r| &r.fields[..]);
            let pending = fields
                .iter()
                .filter_map(|(_, t)| base_record(t))
                .find(|j| depth.get(*j).copied().flatten().is_none());
            match pending {
                Some(j) => stack.push(j),
                None => {
                    let known = |j: usize| depth.get(j).copied().flatten().unwrap_or(1);
                    let d = 1 + fields
                        .iter()
                        .map(|(_, t)| ty_depth_with(t, known))
                        .max()
                        .unwrap_or(0);
                    if let Some(slot) = depth.get_mut(i) {
                        *slot = Some(d);
                    }
                    stack.pop();
                }
            }
        }
    }
    *depths = depth.into_iter().map(|d| d.unwrap_or(1)).collect();
}

pub fn is_builtin(name: &str) -> bool {
    BUILTIN_TYPES.contains(&name)
        || BUILTIN_CONSTANTS.contains(&name)
        || Prim::from_name(name).is_some()
}

fn err(code: &'static str, message: impl Into<String>, span: Span) -> Diagnostic {
    Diagnostic::new(code, "static", message, span)
}

/// A top-level name of a module: a record or a function, by index into the
/// program's records or functions.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Global {
    Record(usize),
    Function(usize),
}

/// What a checked module offers to importers: each of its own top-level
/// declarations, with its index and whether it is marked `export`. Imported
/// names are not listed: modules-1 has no re-exports.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModuleScope {
    pub declared: BTreeMap<String, (Global, bool)>,
}

/// Code of a module-specific name failure: an imported name the module does
/// not declare (`MOD-IMPORT-1`).
pub const NOT_DECLARED_CODE: &str = "E606";
/// An imported declaration that is not exported (`MOD-IMPORT-2`).
pub const NOT_EXPORTED_CODE: &str = "E607";
/// An import name that collides with a built-in name, another import or a
/// declaration of the importing module (`MOD-NAME-1`).
pub const IMPORT_COLLISION_CODE: &str = "E608";
/// An exported declaration whose signature or fields expose a record that is
/// not exported (`MOD-EXPORT-1`).
pub const EXPOSED_RECORD_CODE: &str = "E609";

struct Local {
    name: String,
    slot: usize,
    ty: Ty,
}

/// A program under construction: the modules checked so far, in checking
/// order (every module after the modules it imports).
#[derive(Default)]
pub struct Builder {
    records: Vec<Record>,
    record_depths: Vec<usize>,
    signatures: Vec<(Vec<(String, Ty)>, Ty)>,
    functions: Vec<Function>,
    /// Calls of each function: (callee, span), by function index.
    graph: Vec<Vec<(usize, Span)>>,
    /// By module index; `None` until the module is checked.
    scopes: Vec<Option<ModuleScope>>,
}

struct Checker {
    /// The module's namespace: its declarations and its imported names.
    globals: BTreeMap<String, Global>,
    /// Names in `globals` that are imported.
    imported: BTreeMap<String, String>,
    records: Vec<Record>,
    record_depths: Vec<usize>,
    signatures: Vec<(Vec<(String, Ty)>, Ty)>,
    scopes: Vec<Vec<Local>>,
    slots: usize,
    /// Calls to user functions from the body being checked: (callee, span).
    calls: Vec<(usize, Span)>,
}

/// Check a lowered file on its own, as module 0 of a one-module program;
/// `source` is kept in the program for diagnostics. A file with imports
/// needs a project root (`MOD-ROOT-1`, E605); use [`crate::modules`].
pub fn check_program(file: &FileAst, source: &str) -> Result<Program, Diagnostic> {
    if let Some(import) = file.imports.first() {
        return Err(crate::modules::no_root(import.path_span));
    }
    let mut b = Builder::default();
    b.check_module(0, crate::modules::ANONYMOUS_MODULE, file, &[])?;
    let sources = Sources {
        files: vec![SourceFile {
            name: String::new(),
            text: source.to_string(),
            module: crate::modules::ANONYMOUS_MODULE.to_string(),
        }],
    };
    Ok(b.finish(sources, vec![crate::modules::ANONYMOUS_MODULE.to_string()]))
}

fn local_items(file: &FileAst) -> (Vec<&ast::RecordAst>, Vec<&ast::FnAst>) {
    let records = file
        .items
        .iter()
        .filter_map(|i| match i {
            Item::Record(r) => Some(r),
            Item::Fn(_) => None,
        })
        .collect();
    let functions = file
        .items
        .iter()
        .filter_map(|i| match i {
            Item::Fn(f) => Some(f),
            Item::Record(_) => None,
        })
        .collect();
    (records, functions)
}

impl Builder {
    /// The checked program, with its sources and the names of its modules
    /// (index = file index).
    pub fn finish(self, sources: Sources, modules: Vec<String>) -> Program {
        let modules = modules
            .into_iter()
            .enumerate()
            .map(|(i, name)| Module {
                name,
                file: FileId(u32::try_from(i).unwrap_or(u32::MAX)),
            })
            .collect();
        Program {
            source: sources
                .files
                .first()
                .map(|f| f.text.clone())
                .unwrap_or_default(),
            sources,
            modules,
            records: self.records,
            functions: self.functions,
        }
    }

    /// Check module `module` (named `name`), whose imports have already been
    /// checked: `targets[i]` is the module index that `file.imports[i]` names.
    ///
    /// Order (`MOD-CHECK-1`): the module's top-level declaration names
    /// (`P0-DECL-1`); its imports, name by name in source order
    /// (`MOD-IMPORT-1`, `MOD-IMPORT-2`, `MOD-NAME-1`); then the P0 steps 2 to
    /// 4 of `pure.rst`; the export rule (`MOD-EXPORT-1`) in file order; the
    /// bodies (P0 step 5); and mutual recursion among the module's functions
    /// (P0 step 6). A call cycle or record cycle through two modules would need
    /// an import cycle, which loading rejects first (`MOD-CYCLE-1`).
    pub fn check_module(
        &mut self,
        module: usize,
        name: &str,
        file: &FileAst,
        targets: &[usize],
    ) -> Result<(), Diagnostic> {
        let mut c = Checker {
            globals: BTreeMap::new(),
            imported: BTreeMap::new(),
            records: std::mem::take(&mut self.records),
            record_depths: std::mem::take(&mut self.record_depths),
            signatures: std::mem::take(&mut self.signatures),
            scopes: Vec::new(),
            slots: 0,
            calls: Vec::new(),
        };
        let result = self.check_module_with(&mut c, module, name, file, targets);
        self.records = c.records;
        self.record_depths = c.record_depths;
        self.signatures = c.signatures;
        result
    }

    fn check_module_with(
        &mut self,
        c: &mut Checker,
        module: usize,
        module_name: &str,
        file: &FileAst,
        targets: &[usize],
    ) -> Result<(), Diagnostic> {
        let (record_asts, fn_asts) = local_items(file);
        let rec_base = c.records.len();
        let fn_base = c.signatures.len();
        let symbol = |name: &str| Symbol {
            package: Package::Local,
            module: module_name.to_string(),
            name: name.to_string(),
        };

        // 1. Top-level names.
        let (mut nrec, mut nfn) = (rec_base, fn_base);
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
            if c.globals.insert(name.text.clone(), global).is_some() {
                return Err(err(
                    "E501",
                    format!("'{}' is declared more than once in this file.", name.text),
                    name.span,
                ));
            }
        }

        // 1b. Imports, name by name.
        for (import, target) in file.imports.iter().zip(targets) {
            let dotted = import.dotted();
            let scope = self.scopes.get(*target).and_then(Option::as_ref);
            for n in &import.names {
                let found = scope.and_then(|s| s.declared.get(&n.name.text)).copied();
                let global = match found {
                    None => {
                        return Err(err(
                            NOT_DECLARED_CODE,
                            format!(
                                "Module '{dotted}' declares no function or record named '{}'.",
                                n.name.text
                            ),
                            n.name.span,
                        ));
                    }
                    Some((_, false)) => {
                        return Err(err(
                            NOT_EXPORTED_CODE,
                            format!(
                                "'{}' is not exported by module '{dotted}': only declarations marked export can be imported.",
                                n.name.text
                            ),
                            n.name.span,
                        ));
                    }
                    Some((g, true)) => g,
                };
                let local = n.local();
                let clash = if is_builtin(&local.text) {
                    Some("a built-in name".to_string())
                } else if let Some(from) = c.imported.get(&local.text) {
                    Some(format!("a name already imported from '{from}'"))
                } else if c.globals.contains_key(&local.text) {
                    Some("a function or record declared in this module".to_string())
                } else {
                    None
                };
                if let Some(what) = clash {
                    return Err(err(
                        IMPORT_COLLISION_CODE,
                        format!(
                            "The import name '{}' collides with {what}; imports never shadow and are never shadowed (use 'as' to rename).",
                            local.text
                        ),
                        local.span,
                    ));
                }
                c.globals.insert(local.text.clone(), global);
                c.imported.insert(local.text.clone(), dotted.clone());
            }
        }

        // 2. Records: placeholders first so field types can name any record.
        for r in &record_asts {
            c.records.push(Record {
                symbol: symbol(&r.name.text),
                module,
                exported: r.exported,
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
            if let Some(rec) = c.records.get_mut(rec_base + i) {
                rec.fields = fields;
            }
        }

        // 3. Recursive records (only this module's records can form a cycle:
        // an imported record never mentions a record of its importer).
        for (i, r) in record_asts.iter().enumerate() {
            if c.record_reaches(rec_base + i, rec_base + i, rec_base) {
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

        // 3b. Record type depth.
        extend_record_depths(&c.records, &mut c.record_depths, rec_base);
        for (i, r) in record_asts.iter().enumerate() {
            if c.record_depths.get(rec_base + i).copied().unwrap_or(1) > TYPE_DEPTH_LIMIT {
                return Err(type_limit(r.name.span));
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
                let ty = c.resolve_type(pty)?;
                c.depth_ok(&ty, pty.span)?;
                params.push((pname.text.clone(), ty));
            }
            let ret = c.resolve_type(&f.ret)?;
            c.depth_ok(&ret, f.ret.span)?;
            c.signatures.push((params, ret));
        }

        // 4b. The export rule: an exported declaration exposes only exported records.
        for item in file.items.iter().filter(|i| i.exported()) {
            let types: Vec<&TypeAst> = match item {
                Item::Record(r) => r.fields.iter().map(|(_, t)| t).collect(),
                Item::Fn(f) => f
                    .params
                    .iter()
                    .map(|(_, t)| t)
                    .chain(std::iter::once(&f.ret))
                    .collect(),
            };
            for t in types {
                let ty = c.resolve_type(t)?;
                if let Some(r) = base_record(&ty)
                    .and_then(|r| c.records.get(r))
                    .filter(|r| !r.exported)
                {
                    return Err(err(
                        EXPOSED_RECORD_CODE,
                        format!(
                            "Exported '{}' exposes the record '{}', which is not exported: export '{}' too.",
                            item.name().text,
                            r.name,
                            r.name
                        ),
                        t.span,
                    ));
                }
            }
        }

        // 5. Bodies.
        for (index, f) in fn_asts.iter().enumerate() {
            structure(&f.body)?;
            let (params, ret) = c
                .signatures
                .get(fn_base + index)
                .cloned()
                .unwrap_or_default_sig();
            c.scopes = vec![Vec::new()];
            c.slots = 0;
            c.calls = Vec::new();
            for (name, ty) in &params {
                c.bind(name, ty.clone());
            }
            let body = c.block(&f.body, &ret)?;
            let mut calls = std::mem::take(&mut c.calls);
            calls.sort_by_key(|(_, span)| span.start);
            self.graph.push(calls);
            self.functions.push(Function {
                symbol: symbol(&f.name.text),
                module,
                exported: f.exported,
                name: f.name.text.clone(),
                params,
                ret,
                body,
                locals: c.slots,
                span: f.span,
                name_span: f.name.span,
            });
        }

        // 6. Mutual recursion among this module's functions (an imported
        // function never calls a function of its importer).
        let n = self.graph.len();
        let reach: Vec<Vec<bool>> = (fn_base..n)
            .map(|f| reachable(&self.graph, f, fn_base))
            .collect();
        let reaches = |a: usize, b: usize| {
            a >= fn_base
                && reach
                    .get(a - fn_base)
                    .and_then(|r| r.get(b.wrapping_sub(fn_base)))
                    .copied()
                    == Some(true)
        };
        for f in fn_base..n {
            for (g, span) in self.graph.get(f).map_or(&[][..], |v| &v[..]) {
                if *g != f && reaches(*g, f) {
                    let fname = self.functions.get(f).map_or("?", |x| x.name.as_str());
                    let gname = self.functions.get(*g).map_or("?", |x| x.name.as_str());
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

        // What importers may name.
        let mut scope = ModuleScope::default();
        for item in &file.items {
            if let Some(g) = c.globals.get(&item.name().text) {
                scope
                    .declared
                    .insert(item.name().text.clone(), (*g, item.exported()));
            }
        }
        if self.scopes.len() <= module {
            self.scopes.resize(module + 1, None);
        }
        if let Some(slot) = self.scopes.get_mut(module) {
            *slot = Some(scope);
        }
        Ok(())
    }
}

trait DefaultSig {
    fn unwrap_or_default_sig(self) -> (Vec<(String, Ty)>, Ty);
}

impl DefaultSig for Option<(Vec<(String, Ty)>, Ty)> {
    fn unwrap_or_default_sig(self) -> (Vec<(String, Ty)>, Ty) {
        self.unwrap_or((Vec::new(), Ty::Int))
    }
}

/// Functions with index `base` or more reachable from `from` by one or more
/// calls through such functions; entry `i` is function `base + i`.
fn reachable(graph: &[Vec<(usize, Span)>], from: usize, base: usize) -> Vec<bool> {
    let mut seen = vec![false; graph.len().saturating_sub(base)];
    let local = |calls: &Vec<(usize, Span)>| -> Vec<usize> {
        calls
            .iter()
            .filter(|(g, _)| *g >= base)
            .map(|(g, _)| *g - base)
            .collect()
    };
    let mut work: Vec<usize> = graph.get(from).map(local).unwrap_or_default();
    while let Some(g) = work.pop() {
        if let Some(s) = seen.get_mut(g)
            && !*s
        {
            *s = true;
            if let Some(next) = graph.get(base + g) {
                work.extend(local(next));
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

impl Checker {
    /// Does record `from` contain record `target` through its field types,
    /// following only records with index `base` or more?
    fn record_reaches(&self, from: usize, target: usize, base: usize) -> bool {
        fn mentions(ty: &Ty, out: &mut Vec<usize>) {
            match ty {
                Ty::Record(i) => out.push(*i),
                Ty::List(t) => mentions(t, out),
                Ty::Int | Ty::Bool => {}
            }
        }
        let mut seen = vec![false; self.records.len().saturating_sub(base)];
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
            if i < base {
                continue;
            }
            if let Some(s) = seen.get_mut(i - base)
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
            _ => match (self.globals.get(name).copied(), &t.args) {
                (Some(Global::Record(i)), None) => Ok(Ty::Record(i)),
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
        } else if self.imported.contains_key(text) {
            Some("an imported name")
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
    /// E500 at `span` when `ty` is deeper than [`TYPE_DEPTH_LIMIT`].
    fn depth_ok(&self, ty: &Ty, span: Span) -> Result<(), Diagnostic> {
        if ty_depth(ty, &self.record_depths) > TYPE_DEPTH_LIMIT {
            return Err(type_limit(span));
        }
        Ok(())
    }

    /// [`Self::synth_inner`], then the type depth of the result.
    fn synth(&mut self, e: &ExprAst, expected: Option<&Ty>) -> Result<Expr, Diagnostic> {
        let typed = self.synth_inner(e, expected)?;
        self.depth_ok(&typed.ty, e.span)?;
        Ok(typed)
    }

    fn synth_inner(&mut self, e: &ExprAst, expected: Option<&Ty>) -> Result<Expr, Diagnostic> {
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
                let what = if self.imported.contains_key(root.text.as_str()) {
                    format!(
                        "'{}' is an imported function or record, not a value; functions are not values in P0.",
                        root.text
                    )
                } else if self.globals.contains_key(root.text.as_str()) {
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
            let s = current.span.to(field.span);
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
