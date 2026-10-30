// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The checked, typed P0 program. Names are resolved to indices (functions,
//! records, fields, local slots); every expression keeps its type and the span
//! of the AST node it came from.

use weave_syntax::Span;

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

    /// The type as written in source.
    pub fn spell(&self, records: &[Record]) -> String {
        match self {
            Ty::Int => "Int".into(),
            Ty::Bool => "Bool".into(),
            Ty::List(t) => format!("List[{}]", t.spell(records)),
            Ty::Record(i) => records
                .get(*i)
                .map_or_else(|| "?".into(), |r| r.name.clone()),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Record {
    pub name: String,
    pub fields: Vec<(String, Ty)>,
    pub span: Span,
    pub name_span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Function {
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

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Program {
    pub source: String,
    pub records: Vec<Record>,
    pub functions: Vec<Function>,
}

impl Program {
    pub fn function(&self, name: &str) -> Option<usize> {
        self.functions.iter().position(|f| f.name == name)
    }
}
