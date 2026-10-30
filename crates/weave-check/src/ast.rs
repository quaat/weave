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
    /// The `export` marker (modules-1); always false in a pure file.
    pub exported: bool,
    pub name: Name,
    pub fields: Vec<(Name, TypeAst)>,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FnAst {
    /// The `export` marker (modules-1); always false in a pure file.
    pub exported: bool,
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

impl Item {
    pub fn name(&self) -> &Name {
        match self {
            Item::Record(r) => &r.name,
            Item::Fn(f) => &f.name,
        }
    }

    pub fn exported(&self) -> bool {
        match self {
            Item::Record(r) => r.exported,
            Item::Fn(f) => f.exported,
        }
    }
}

/// One imported name of an `import-decl`: `name` or `name as alias`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImportName {
    pub name: Name,
    pub alias: Option<Name>,
    pub span: Span,
}

impl ImportName {
    /// The name the import introduces into the importing module.
    pub fn local(&self) -> &Name {
        self.alias.as_ref().unwrap_or(&self.name)
    }
}

/// `from a.b import x, y as z` (modules-1).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImportAst {
    /// The dotted module path, one name per segment.
    pub path: Vec<Name>,
    /// The span of the whole dotted path.
    pub path_span: Span,
    pub names: Vec<ImportName>,
    /// The whole declaration, without its line end.
    pub span: Span,
}

impl ImportAst {
    pub fn dotted(&self) -> String {
        self.path
            .iter()
            .map(|n| n.text.as_str())
            .collect::<Vec<_>>()
            .join(".")
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FileAst {
    /// Imports (modules-1); empty in a pure file.
    pub imports: Vec<ImportAst>,
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
    /// Expression depth (`pure.rst`, "Nesting limits"): 1 for a literal; one
    /// more than the deepest operand, element or argument; a name with `k`
    /// dotted parts counts `k`, plus its deepest argument.
    pub depth: usize,
}

impl ExprAst {
    /// A node with its depth computed from its children, without recursion.
    pub fn new(kind: ExprKind, span: Span) -> ExprAst {
        let depth = match &kind {
            ExprKind::Int(_) => 1,
            ExprKind::List(items) => 1 + items.iter().map(|e| e.depth).max().unwrap_or(0),
            ExprKind::Path { parts, call, .. } => {
                let args = call.as_ref().map_or(0, |args| {
                    args.iter()
                        .map(|a| a.value.depth.max(a.label.as_ref().map_or(0, |l| l.depth)))
                        .max()
                        .unwrap_or(0)
                });
                parts.len().max(1) + args
            }
            ExprKind::Neg(x) => 1 + x.depth,
            ExprKind::Binary(_, l, r) => 1 + l.depth.max(r.depth),
        };
        ExprAst { kind, span, depth }
    }

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
