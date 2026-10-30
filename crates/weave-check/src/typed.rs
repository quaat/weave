// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The checked, typed P0 program. Names are resolved to indices (functions,
//! records, fields, local slots); every expression keeps its type and the span
//! of the AST node it came from. Every function and record also has a
//! [`Symbol`], its identity across modules (modules-1), and every span names
//! its source file ([`Sources`]).

use weave_syntax::diagnostic::SourceMap;
use weave_syntax::{FileId, Span};

/// The package a declaration belongs to. modules-1 has only the local
/// project; quaat/weave#13 adds named packages here, so a symbol identity
/// already has a place for it.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Package {
    /// The project being checked: the modules under one project root.
    Local,
}

/// The identity of a top-level declaration (`MOD-IDENT-1`): its package, its
/// module and its declared name. Two declarations are the same declaration,
/// and two records the same nominal type, exactly when their symbols are
/// equal; an import alias never changes a symbol.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Symbol {
    pub package: Package,
    /// The module's dotted path from the project root, or a name in angle
    /// brackets for an entry file that has no module path (such as `<stdin>`).
    pub module: String,
    pub name: String,
}

impl Symbol {
    /// `module.name`.
    pub fn qualified(&self) -> String {
        format!("{}.{}", self.module, self.name)
    }
}

/// One loaded source file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SourceFile {
    /// The file's name in reports: the entry as given, an imported module as
    /// the project root as given joined with the module's relative path.
    pub name: String,
    pub text: String,
    /// The module's dotted path, or the angle-bracket name of an entry file
    /// without one.
    pub module: String,
}

/// The source files of a program, indexed by [`FileId`]: the entry file
/// first, then the imported modules in the order they were loaded.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Sources {
    pub files: Vec<SourceFile>,
}

impl Sources {
    pub fn get(&self, file: FileId) -> Option<&SourceFile> {
        self.files.get(file.index())
    }
}

impl SourceMap for Sources {
    fn name(&self, file: FileId) -> &str {
        self.get(file).map_or("<input>", |f| f.name.as_str())
    }
    fn text(&self, file: FileId) -> &str {
        self.get(file).map_or("", |f| f.text.as_str())
    }
}

/// A P0 value type (`P0-TYPE-1`).
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum Ty {
    Int,
    Bool,
    List(Box<Ty>),
    /// Index into [`Program::records`].
    Record(usize),
}

impl Ty {
    pub fn list(element: Ty) -> Ty {
        Ty::List(Box::new(element))
    }

    /// The type as written in source. A record is spelled by its declared
    /// name, qualified with its module when another record of the program
    /// has the same name (modules-1: they are different types).
    pub fn spell(&self, records: &[Record]) -> String {
        match self {
            Ty::Int => "Int".into(),
            Ty::Bool => "Bool".into(),
            Ty::List(t) => format!("List[{}]", t.spell(records)),
            Ty::Record(i) => records.get(*i).map_or_else(
                || "?".into(),
                |r| {
                    if records.iter().filter(|o| o.name == r.name).count() > 1 {
                        r.symbol.qualified()
                    } else {
                        r.name.clone()
                    }
                },
            ),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Record {
    pub symbol: Symbol,
    /// Index into [`Program::modules`] of the defining module.
    pub module: usize,
    pub exported: bool,
    pub name: String,
    pub fields: Vec<(String, Ty)>,
    pub span: Span,
    pub name_span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Function {
    pub symbol: Symbol,
    /// Index into [`Program::modules`] of the defining module.
    pub module: usize,
    pub exported: bool,
    pub name: String,
    pub params: Vec<(String, Ty)>,
    pub ret: Ty,
    pub body: Block,
    /// Local slots: the parameters first, then one per `let`.
    pub locals: usize,
    pub span: Span,
    pub name_span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Block {
    /// `let` statements, then the terminal statement (`P0-PATH-1`).
    pub lets: Vec<(usize, Expr)>,
    pub end: Box<Terminal>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Terminal {
    Return(Expr),
    If {
        cond: Expr,
        then: Block,
        otherwise: Block,
    },
}

/// Built-in primitives (`P0-ARITH-2`, `P0-LIST-1`, `P0-EVAL-2`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Prim {
    Length,
    IsEmpty,
    Head,
    Tail,
    Cons,
    Div,
    Mod,
    Not,
}

impl Prim {
    pub const ALL: [Prim; 8] = [
        Prim::Length,
        Prim::IsEmpty,
        Prim::Head,
        Prim::Tail,
        Prim::Cons,
        Prim::Div,
        Prim::Mod,
        Prim::Not,
    ];

    pub fn name(self) -> &'static str {
        match self {
            Prim::Length => "length",
            Prim::IsEmpty => "is_empty",
            Prim::Head => "head",
            Prim::Tail => "tail",
            Prim::Cons => "cons",
            Prim::Div => "div",
            Prim::Mod => "mod",
            Prim::Not => "not",
        }
    }

    pub fn arity(self) -> usize {
        match self {
            Prim::Cons | Prim::Div | Prim::Mod => 2,
            _ => 1,
        }
    }

    pub fn from_name(name: &str) -> Option<Prim> {
        Prim::ALL.into_iter().find(|p| p.name() == name)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArithOp {
    Add,
    Sub,
    Mul,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CmpOp {
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ExprK {
    /// Nonnegative decimal digits without a leading zero (or `0`).
    Int(String),
    Bool(bool),
    Local(usize),
    /// Field access by declared field index.
    Field(Box<Expr>, usize),
    /// User function call by index into [`Program::functions`].
    Call(usize, Vec<Expr>),
    Prim(Prim, Vec<Expr>),
    /// Record construction: (declared field index, value) in written order.
    Construct(usize, Vec<(usize, Expr)>),
    List(Vec<Expr>),
    Neg(Box<Expr>),
    Arith(ArithOp, Box<Expr>, Box<Expr>),
    Compare(CmpOp, Box<Expr>, Box<Expr>),
    And(Box<Expr>, Box<Expr>),
    Or(Box<Expr>, Box<Expr>),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Expr {
    pub kind: ExprK,
    pub ty: Ty,
    pub span: Span,
}

/// One checked module (modules-1). A pure file is one module.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Module {
    /// The dotted path, or the angle-bracket name of an entry without one.
    pub name: String,
    pub file: FileId,
}

/// The entry module is [`Program::modules`]`[0]`, in [`FileId::ENTRY`].
pub const ENTRY_MODULE: usize = 0;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Program {
    /// The entry file's text.
    pub source: String,
    /// Every loaded file; a span's [`FileId`] indexes it.
    pub sources: Sources,
    /// Every loaded module, in load order (index = file index).
    pub modules: Vec<Module>,
    /// Records of every module, in checking order.
    pub records: Vec<Record>,
    /// Functions of every module, in checking order (each module's in file order).
    pub functions: Vec<Function>,
}

impl Program {
    /// The function named `name` declared in the entry module, exported or
    /// not (the run entry, `P0-RUN-1`).
    pub fn function(&self, name: &str) -> Option<usize> {
        self.functions
            .iter()
            .position(|f| f.module == ENTRY_MODULE && f.name == name)
    }

    /// Functions declared in `module`, in file order.
    pub fn functions_of(&self, module: usize) -> impl Iterator<Item = &Function> {
        self.functions.iter().filter(move |f| f.module == module)
    }
}
