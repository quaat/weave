// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The P0 abstract syntax tree. Every node keeps the byte span of the source
//! text it was lowered from, so diagnostics and run-time faults point at
//! source (source mapping, `pure.rst`).

use weave_syntax::Span;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Name {
    pub text: String,
    pub span: Span,
}

/// `IDENT [ "[" type { "," type } "]" ]`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TypeAst {
    pub name: Name,
    /// `None` without brackets; `Some` (possibly with several entries) with them.
    pub args: Option<Vec<TypeAst>>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RecordAst {
    pub name: Name,
    pub fields: Vec<(Name, TypeAst)>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FnAst {
    pub name: Name,
    pub params: Vec<(Name, TypeAst)>,
    pub ret: TypeAst,
    pub body: BlockAst,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Item {
    Record(RecordAst),
    Fn(FnAst),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FileAst {
    pub items: Vec<Item>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BlockAst {
    pub stmts: Vec<StmtAst>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StmtKind {
    Let {
        name: Name,
        value: ExprAst,
    },
    Return(ExprAst),
    If {
        cond: ExprAst,
        then: BlockAst,
        otherwise: Option<BlockAst>,
    },
    Fork(BlockAst),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StmtAst {
    pub kind: StmtKind,
    /// The whole statement; for `if` it ends at the end of its last block.
    pub span: Span,
    /// The leading keyword.
    pub keyword: Span,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BinOp {
    Or,
    And,
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
    Add,
    Sub,
    Mul,
}

impl BinOp {
    pub fn spelling(self) -> &'static str {
        match self {
            BinOp::Or => "or",
            BinOp::And => "and",
            BinOp::Lt => "<",
            BinOp::Le => "<=",
            BinOp::Gt => ">",
            BinOp::Ge => ">=",
            BinOp::Eq => "==",
            BinOp::Ne => "!=",
            BinOp::Add => "+",
            BinOp::Sub => "-",
            BinOp::Mul => "*",
        }
    }
}

/// One call argument: `expr` or `label: expr`. The grammar admits any
/// expression as a label; static checking requires a plain identifier.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ArgAst {
    pub label: Option<ExprAst>,
    pub value: ExprAst,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ExprKind {
    /// A decimal integer token (`UINT`), as source text.
    Int(String),
    List(Vec<ExprAst>),
    /// `name-expr`: an optional prefix word (only `await` survives lowering),
    /// one or more dotted parts and an optional argument list.
    Path {
        prefix: Option<Name>,
        parts: Vec<Name>,
        call: Option<Vec<ArgAst>>,
    },
    Neg(Box<ExprAst>),
    Binary(BinOp, Box<ExprAst>, Box<ExprAst>),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExprAst {
    pub kind: ExprKind,
    pub span: Span,
}

impl ExprAst {
    /// The identifier if this expression is a single undotted, uncalled name.
    pub fn as_plain_name(&self) -> Option<&Name> {
        match &self.kind {
            ExprKind::Path {
                prefix: None,
                parts,
                call: None,
            } if parts.len() == 1 => parts.first(),
            _ => None,
        }
    }
}
