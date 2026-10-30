// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The compiled grammar and its normalisation check.
//!
//! The parser interprets `specification/grammar/weave.ebnf`, embedded at build
//! time, as an ordered-choice (PEG-style) grammar: alternatives are tried in
//! order with backtracking to the choice point, and options and repetitions
//! are greedy. The normalisation check establishes that, for the checked
//! grammar, this reading accepts exactly the language of the EBNF read as a
//! context-free grammar. See [`check`] for what it guarantees.

use crate::ebnf::{self, Expr, Production};
use crate::lexer::{Token, TokenClass};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::sync::OnceLock;

/// The authoritative portable grammar.
pub const WEAVE_EBNF: &str = include_str!("../../../specification/grammar/weave.ebnf");
/// The target-only N2 delta. It is never used for parsing; the normalisation
/// tests read it as EBNF and resolve its references against the base grammar.
pub const N2_DELTA_EBNF: &str = include_str!("../../../specification/grammar/weave-n2-delta.ebnf");

/// Start symbols of the portable grammar (SYN-01).
pub const START_SYMBOLS: [&str; 3] = ["flow-file", "n0-file", "n1-file"];

/// Special-sequence productions and the lexer tokens that implement them.
pub const LEXICAL: [(&str, Symbol); 5] = [
    ("IDENT", Symbol::Ident),
    ("POSINT", Symbol::PosInt),
    ("NL", Symbol::Newline),
    ("INDENT", Symbol::Indent),
    ("DEDENT", Symbol::Dedent),
];

/// Punctuation the lexer produces as single tokens.
pub const PUNCTUATION: [&str; 14] = [
    "(", ")", "[", "]", ",", ":", ".", "=", "->", "==", "+", "-", "*", "?",
];

/// Lookahead bound of the conflict analysis, in tokens.
pub const MAX_LOOKAHEAD: usize = 8;
const EXPANSION_BUDGET: usize = 200_000;

/// A grammar symbol matched against one token.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Symbol {
    /// A quoted terminal, matched by token text.
    Lit(String),
    /// `IDENT`: any word token; contextual words are identifiers too (LEX-REQ-2).
    Ident,
    /// `POSINT`: an integer token without a leading zero.
    PosInt,
    /// `NL`.
    Newline,
    /// `INDENT`.
    Indent,
    /// `DEDENT`.
    Dedent,
    /// End of input, after a start symbol.
    Eof,
}

impl Symbol {
    /// Grammar spelling of the symbol, used in the CST and in reports.
    pub fn name(&self) -> String {
        match self {
            Symbol::Lit(s) => format!("\"{s}\""),
            Symbol::Ident => "IDENT".into(),
            Symbol::PosInt => "POSINT".into(),
            Symbol::Newline => "NL".into(),
            Symbol::Indent => "INDENT".into(),
            Symbol::Dedent => "DEDENT".into(),
            Symbol::Eof => "EOF".into(),
        }
    }

    /// Wording for "expected ..." messages.
    pub fn describe(&self) -> String {
        match self {
            Symbol::Lit(s) => format!("'{s}'"),
            Symbol::Ident => "an identifier".into(),
            Symbol::PosInt => "a positive integer".into(),
            Symbol::Newline => "the end of the line".into(),
            Symbol::Indent => "an indented block".into(),
            Symbol::Dedent => "the end of the block".into(),
            Symbol::Eof => "the end of the file".into(),
        }
    }

    /// Does `token`, whose text is `text`, match this symbol?
    pub fn matches(&self, token: &Token, text: &str) -> bool {
        match self {
            Symbol::Lit(s) => {
                matches!(
                    token.class,
                    TokenClass::Word | TokenClass::Int | TokenClass::Punct
                ) && text == s
            }
            Symbol::Ident => token.class == TokenClass::Word,
            Symbol::PosInt => token.class == TokenClass::Int && !text.starts_with('0'),
            Symbol::Newline => token.class == TokenClass::Newline,
            Symbol::Indent => token.class == TokenClass::Indent,
            Symbol::Dedent => token.class == TokenClass::Dedent,
            Symbol::Eof => token.class == TokenClass::Eof,
        }
    }

    /// Can some token match both symbols?
    pub fn overlaps(&self, other: &Symbol) -> bool {
        match (self, other) {
            (a, b) if a == b => true,
            (Symbol::Ident, Symbol::Lit(s)) | (Symbol::Lit(s), Symbol::Ident) => is_word(s),
            (Symbol::PosInt, Symbol::Lit(s)) | (Symbol::Lit(s), Symbol::PosInt) => {
                is_int(s) && !s.starts_with('0')
            }
            _ => false,
        }
    }
}

fn is_word(s: &str) -> bool {
    let mut bytes = s.bytes();
    bytes
        .next()
        .is_some_and(|b| b.is_ascii_alphabetic() || b == b'_')
        && bytes.all(|b| b.is_ascii_alphanumeric() || b == b'_')
}

fn is_int(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
}

/// Does `s` lex as exactly one token of the lexer?
pub fn is_single_token(s: &str) -> bool {
    is_word(s) || is_int(s) || PUNCTUATION.contains(&s)
}

/// A compiled grammar expression.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum GExpr {
    Sym(Symbol),
    Rule(usize),
    Opt(Box<GExpr>),
    Rep(Box<GExpr>),
    Seq(Vec<GExpr>),
    Alt(Vec<GExpr>),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Rule {
    pub name: String,
    pub body: GExpr,
    pub line: usize,
}

/// A grammar ready for interpretation.
#[derive(Clone, Debug)]
pub struct Grammar {
    pub rules: Vec<Rule>,
    index: HashMap<String, usize>,
}

impl Grammar {
    pub fn rule(&self, name: &str) -> Option<usize> {
        self.index.get(name).copied()
    }

    /// Read, check and compile an EBNF text. Any normalisation problem is an error,
    /// so the interpreted grammar never silently differs from the EBNF reading.
    pub fn from_ebnf(text: &str, starts: &[&str]) -> Result<Grammar, Report> {
        let productions = match ebnf::parse(text) {
            Ok(p) => p,
            Err(e) => {
                return Err(Report {
                    problems: vec![Problem {
                        check: "ebnf",
                        production: String::new(),
                        line: e.line,
                        message: e.message,
                    }],
                    ..Report::default()
                });
            }
        };
        let report = check(&productions, starts);
        if !report.problems.is_empty() {
            return Err(report);
        }
        compile(&productions).map_err(|problems| Report {
            problems,
            ..Report::default()
        })
    }
}

/// The embedded portable grammar, compiled once.
pub fn builtin() -> Result<&'static Grammar, &'static Report> {
    static GRAMMAR: OnceLock<Result<Grammar, Report>> = OnceLock::new();
    GRAMMAR
        .get_or_init(|| Grammar::from_ebnf(WEAVE_EBNF, &START_SYMBOLS))
        .as_ref()
}

fn lexical(name: &str) -> Option<Symbol> {
    LEXICAL
        .iter()
        .find(|(n, _)| *n == name)
        .map(|(_, s)| s.clone())
}

fn compile(productions: &[Production]) -> Result<Grammar, Vec<Problem>> {
    let mut index = HashMap::new();
    let mut ordered = Vec::new();
    for p in productions {
        if !matches!(p.expr, Expr::Special(_)) {
            index.insert(p.name.clone(), ordered.len());
            ordered.push(p);
        }
    }
    let mut problems = Vec::new();
    let mut rules = Vec::new();
    for p in ordered {
        let body = lower(&p.expr, &index, &p.name, p.line, &mut problems);
        rules.push(Rule {
            name: p.name.clone(),
            body,
            line: p.line,
        });
    }
    if problems.is_empty() {
        Ok(Grammar { rules, index })
    } else {
        Err(problems)
    }
}

fn lower(
    expr: &Expr,
    index: &HashMap<String, usize>,
    owner: &str,
    line: usize,
    problems: &mut Vec<Problem>,
) -> GExpr {
    let mut go = |e: &Expr| lower(e, index, owner, line, problems);
    match expr {
        Expr::Terminal(s) => GExpr::Sym(Symbol::Lit(s.clone())),
        Expr::Ref(name) => match (lexical(name), index.get(name)) {
            (Some(sym), _) => GExpr::Sym(sym),
            (None, Some(&i)) => GExpr::Rule(i),
            (None, None) => {
                problems.push(Problem {
                    check: "undefined",
                    production: owner.into(),
                    line,
                    message: format!("{name} is not defined"),
                });
                GExpr::Seq(Vec::new())
            }
        },
        Expr::Special(text) => {
            problems.push(Problem {
                check: "special-sequence",
                production: owner.into(),
                line,
                message: format!(
                    "special sequence ? {text} ? is not the whole body of a lexical production"
                ),
            });
            GExpr::Seq(Vec::new())
        }
        Expr::Optional(e) => GExpr::Opt(Box::new(go(e))),
        Expr::Repeat(e) => GExpr::Rep(Box::new(go(e))),
        Expr::Seq(items) => GExpr::Seq(items.iter().map(go).collect()),
        Expr::Alt(items) => GExpr::Alt(items.iter().map(go).collect()),
    }
}

/// One normalisation finding.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Problem {
    /// `ebnf`, `duplicate`, `undefined`, `special-sequence`, `terminal`,
    /// `start`, `unreachable`, `nullable`, `left-recursion`, `choice` or `greedy`.
    pub check: &'static str,
    pub production: String,
    pub line: usize,
    pub message: String,
}

impl std::fmt::Display for Problem {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "line {} ({}): [{}] {}",
            self.line, self.production, self.check, self.message
        )
    }
}

/// Result of the normalisation check.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Report {
    pub productions: usize,
    pub lexical_productions: usize,
    pub choices_checked: usize,
    pub greedy_checked: usize,
    /// Largest lookahead (tokens) needed to separate two alternatives, or an
    /// option or repetition from what follows it.
    pub max_lookahead_used: usize,
    pub problems: Vec<Problem>,
}

/// The normalisation check.
///
/// Structural checks: no duplicate production; every referenced name is
/// defined; a special sequence is the whole body of a production named after a
/// lexer token (`IDENT`, `POSINT`, `NL`, `INDENT`, `DEDENT`); every quoted
/// terminal lexes as exactly one token; the start symbols exist and every
/// production is reachable from one of them; no production is left-recursive;
/// no option or repetition body can match the empty string.
///
/// Ordered-choice checks, with up to [`MAX_LOOKAHEAD`] tokens of lookahead,
/// where an identifier overlaps every identifier-shaped terminal (LEX-REQ-2):
///
/// * **choice**: no two alternatives of one choice can both match a prefix of
///   the same token sequence. In particular no alternative is shadowed by an
///   earlier one that matches a prefix of it.
/// * **greedy**: an option or repetition body cannot match a prefix of input
///   on which the continuation after the option or repetition (computed
///   through every use of the enclosing production up to the end of file)
///   could also start.
///
/// When both hold, the ordered-choice parse succeeds exactly when a
/// context-free derivation exists, and it is that derivation: at every choice
/// at most one alternative can match, and a greedy step never consumes tokens
/// that a context-free derivation would leave to the continuation. The checks
/// are sufficient, not necessary: they can reject a grammar on which ordered
/// choice would still be correct, and a pair that stays compatible for
/// [`MAX_LOOKAHEAD`] tokens is reported rather than assumed separable.
pub fn check(productions: &[Production], starts: &[&str]) -> Report {
    let mut report = Report {
        productions: productions.len(),
        lexical_productions: productions
            .iter()
            .filter(|p| matches!(p.expr, Expr::Special(_)))
            .count(),
        ..Report::default()
    };
    let problems = &mut report.problems;
    let mut defined: BTreeMap<&str, &Production> = BTreeMap::new();
    for p in productions {
        if let Some(first) = defined.get(p.name.as_str()) {
            problems.push(Problem {
                check: "duplicate",
                production: p.name.clone(),
                line: p.line,
                message: format!("{} is already defined on line {}", p.name, first.line),
            });
        } else {
            defined.insert(&p.name, p);
        }
        match (&p.expr, lexical(&p.name)) {
            (Expr::Special(_), None) => problems.push(Problem {
                check: "special-sequence",
                production: p.name.clone(),
                line: p.line,
                message: format!(
                    "{} is a special sequence but not a lexer token ({})",
                    p.name,
                    LEXICAL.map(|(n, _)| n).join(", ")
                ),
            }),
            (expr, Some(_)) if !matches!(expr, Expr::Special(_)) => problems.push(Problem {
                check: "special-sequence",
                production: p.name.clone(),
                line: p.line,
                message: format!(
                    "{} names a lexer token but is not a special sequence",
                    p.name
                ),
            }),
            _ => {}
        }
        p.expr.walk(&mut |e| match e {
            Expr::Ref(name) if !defined_anywhere(productions, name) => problems.push(Problem {
                check: "undefined",
                production: p.name.clone(),
                line: p.line,
                message: format!("{name} is referenced but not defined"),
            }),
            Expr::Terminal(s) if !is_single_token(s) => problems.push(Problem {
                check: "terminal",
                production: p.name.clone(),
                line: p.line,
                message: format!("terminal \"{s}\" is not exactly one lexer token"),
            }),
            Expr::Special(text) if !matches!(p.expr, Expr::Special(_)) => problems.push(Problem {
                check: "special-sequence",
                production: p.name.clone(),
                line: p.line,
                message: format!("special sequence ? {text} ? must be the whole production body"),
            }),
            _ => {}
        });
    }
    // Reachability from the start symbols.
    let mut reached: BTreeSet<&str> = BTreeSet::new();
    let mut work: Vec<&str> = Vec::new();
    for s in starts {
        if defined.contains_key(s) {
            work.push(s);
        } else {
            problems.push(Problem {
                check: "start",
                production: (*s).into(),
                line: 0,
                message: format!("start symbol {s} is not defined"),
            });
        }
    }
    while let Some(name) = work.pop() {
        if !reached.insert(name) {
            continue;
        }
        if let Some(p) = defined.get(name) {
            p.expr.walk(&mut |e| {
                if let Expr::Ref(r) = e {
                    work.push(r);
                }
            });
        }
    }
    for p in productions {
        if !reached.contains(p.name.as_str()) {
            problems.push(Problem {
                check: "unreachable",
                production: p.name.clone(),
                line: p.line,
                message: format!("{} is not reachable from {}", p.name, starts.join(", ")),
            });
        }
    }
    if !problems.is_empty() {
        return report;
    }
    let grammar = match compile(productions) {
        Ok(g) => g,
        Err(mut p) => {
            report.problems.append(&mut p);
            return report;
        }
    };
    Analysis::new(&grammar, starts).run(&mut report);
    report
}

fn defined_anywhere(productions: &[Production], name: &str) -> bool {
    productions.iter().any(|p| p.name == name)
}

// ------------------------------------------------------------------ analysis

/// A continuation item: an expression to match, a return from a production
/// (continue at any use of it), or the end of input.
#[derive(Clone, Copy, Debug)]
enum Item<'g> {
    E(&'g GExpr),
    Return(usize),
    Eof,
}

type Stack<'g> = Vec<Item<'g>>;

enum Outcome {
    Disjoint(usize),
    Conflict(Vec<Symbol>, &'static str),
}

struct Analysis<'g> {
    g: &'g Grammar,
    starts: Vec<usize>,
    nullable: Vec<bool>,
    /// For each production, the continuations after each of its uses.
    uses: Vec<Vec<Stack<'g>>>,
    /// Option and repetition occurrences with the continuation after them.
    greedy: Vec<(usize, &'g GExpr, Stack<'g>)>,
    budget: usize,
}

impl<'g> Analysis<'g> {
    fn new(g: &'g Grammar, starts: &[&str]) -> Analysis<'g> {
        let mut a = Analysis {
            g,
            starts: starts.iter().filter_map(|s| g.rule(s)).collect(),
            nullable: vec![false; g.rules.len()],
            uses: vec![Vec::new(); g.rules.len()],
            greedy: Vec::new(),
            budget: EXPANSION_BUDGET,
        };
        loop {
            let mut changed = false;
            for (i, r) in g.rules.iter().enumerate() {
                if !a.nullable.get(i).copied().unwrap_or(true) && a.is_nullable(&r.body) {
                    if let Some(n) = a.nullable.get_mut(i) {
                        *n = true;
                    }
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }
        for (i, r) in g.rules.iter().enumerate() {
            a.collect(i, &r.body, vec![Item::Return(i)]);
        }
        a
    }

    fn is_nullable(&self, e: &GExpr) -> bool {
        match e {
            GExpr::Sym(_) => false,
            GExpr::Rule(i) => self.nullable.get(*i).copied().unwrap_or(false),
            GExpr::Opt(_) | GExpr::Rep(_) => true,
            GExpr::Seq(items) => items.iter().all(|x| self.is_nullable(x)),
            GExpr::Alt(items) => items.iter().any(|x| self.is_nullable(x)),
        }
    }

    /// Record uses of productions and greedy constructs; `cont` is what follows `e`
    /// (top of stack last).
    fn collect(&mut self, owner: usize, e: &'g GExpr, cont: Stack<'g>) {
        match e {
            GExpr::Sym(_) => {}
            GExpr::Rule(i) => {
                if let Some(u) = self.uses.get_mut(*i) {
                    u.push(cont);
                }
            }
            GExpr::Seq(items) => {
                for (k, item) in items.iter().enumerate() {
                    let mut c = cont.clone();
                    c.extend(items.iter().skip(k + 1).rev().map(Item::E));
                    self.collect(owner, item, c);
                }
            }
            GExpr::Alt(items) => {
                for item in items {
                    self.collect(owner, item, cont.clone());
                }
            }
            GExpr::Opt(x) => {
                self.greedy.push((owner, e, cont.clone()));
                self.collect(owner, x, cont);
            }
            GExpr::Rep(x) => {
                self.greedy.push((owner, e, cont.clone()));
                let mut c = cont;
                c.push(Item::E(e));
                self.collect(owner, x, c);
            }
        }
    }

    /// Expand `stack` to every possible next symbol (`None`: the stack can end),
    /// with the stack remaining after it.
    fn steps(
        &mut self,
        stack: Stack<'g>,
        out: &mut Vec<(Option<Symbol>, Stack<'g>)>,
        returned: &mut Vec<usize>,
    ) {
        if self.budget == 0 {
            return;
        }
        self.budget -= 1;
        let mut stack = stack;
        let Some(top) = stack.pop() else {
            out.push((None, stack));
            return;
        };
        match top {
            Item::Eof => out.push((Some(Symbol::Eof), stack)),
            Item::Return(rule) => {
                if returned.contains(&rule) {
                    return; // already continued after this production on this path
                }
                returned.push(rule);
                let uses = self.uses.get(rule).cloned().unwrap_or_default();
                for u in uses {
                    self.steps(u, out, returned);
                }
                if self.starts.contains(&rule) {
                    self.steps(vec![Item::Eof], out, returned);
                }
                returned.pop();
            }
            Item::E(e) => match e {
                GExpr::Sym(s) => out.push((Some(s.clone()), stack)),
                GExpr::Rule(i) => {
                    if let Some(r) = self.g.rules.get(*i) {
                        stack.push(Item::E(&r.body));
                        self.steps(stack, out, returned);
                    }
                }
                GExpr::Seq(items) => {
                    stack.extend(items.iter().rev().map(Item::E));
                    self.steps(stack, out, returned);
                }
                GExpr::Alt(items) => {
                    for item in items {
                        let mut s = stack.clone();
                        s.push(Item::E(item));
                        self.steps(s, out, returned);
                    }
                }
                GExpr::Opt(x) => {
                    let mut s = stack.clone();
                    s.push(Item::E(x));
                    self.steps(s, out, returned);
                    self.steps(stack, out, returned);
                }
                GExpr::Rep(x) => {
                    let mut s = stack.clone();
                    s.push(Item::E(e));
                    s.push(Item::E(x));
                    self.steps(s, out, returned);
                    self.steps(stack, out, returned);
                }
            },
        }
    }

    /// Can `a` and `b` both match a prefix of one token sequence? `prefix` is the
    /// overlapping sequence so far.
    fn separate(&mut self, a: Stack<'g>, b: Stack<'g>, prefix: &mut Vec<Symbol>) -> Outcome {
        let (mut sa, mut sb) = (Vec::new(), Vec::new());
        self.steps(a, &mut sa, &mut Vec::new());
        self.steps(b, &mut sb, &mut Vec::new());
        if self.budget == 0 {
            return Outcome::Conflict(prefix.clone(), "analysis budget exhausted");
        }
        let mut needed = prefix.len() + 1;
        for (x, ra) in &sa {
            for (y, rb) in &sb {
                match (x, y) {
                    (None, _) | (_, None) => {
                        return Outcome::Conflict(
                            prefix.clone(),
                            "one side can end where the other continues",
                        );
                    }
                    (Some(x), Some(y)) if x.overlaps(y) => {
                        prefix.push(x.clone());
                        if prefix.len() >= MAX_LOOKAHEAD {
                            let witness = prefix.clone();
                            prefix.pop();
                            return Outcome::Conflict(
                                witness,
                                "not separated within the lookahead bound",
                            );
                        }
                        let inner = self.separate(ra.clone(), rb.clone(), prefix);
                        prefix.pop();
                        match inner {
                            Outcome::Disjoint(k) => needed = needed.max(k),
                            conflict => return conflict,
                        }
                    }
                    _ => {}
                }
            }
        }
        Outcome::Disjoint(needed)
    }

    fn left_recursive(&self) -> Vec<usize> {
        // Productions reachable at the left edge without consuming a token.
        fn left(a: &Analysis, e: &GExpr, out: &mut BTreeSet<usize>) {
            match e {
                GExpr::Sym(_) => {}
                GExpr::Rule(i) => {
                    out.insert(*i);
                }
                GExpr::Opt(x) | GExpr::Rep(x) => left(a, x, out),
                GExpr::Alt(items) => items.iter().for_each(|x| left(a, x, out)),
                GExpr::Seq(items) => {
                    for x in items {
                        left(a, x, out);
                        if !a.is_nullable(x) {
                            break;
                        }
                    }
                }
            }
        }
        let edges: Vec<BTreeSet<usize>> = self
            .g
            .rules
            .iter()
            .map(|r| {
                let mut s = BTreeSet::new();
                left(self, &r.body, &mut s);
                s
            })
            .collect();
        let mut result = Vec::new();
        for start in 0..self.g.rules.len() {
            let mut seen = BTreeSet::new();
            let mut work: Vec<usize> = edges
                .get(start)
                .map(|s| s.iter().copied().collect())
                .unwrap_or_default();
            while let Some(r) = work.pop() {
                if r == start {
                    result.push(start);
                    break;
                }
                if seen.insert(r) {
                    work.extend(edges.get(r).into_iter().flatten().copied());
                }
            }
        }
        result
    }

    fn run(mut self, report: &mut Report) {
        let g = self.g;
        for (i, r) in g.rules.iter().enumerate() {
            if self.nullable.get(i).copied().unwrap_or(false) {
                report.problems.push(Problem {
                    check: "nullable",
                    production: r.name.clone(),
                    line: r.line,
                    message: format!("{} can match the empty string", r.name),
                });
            }
        }
        for i in self.left_recursive() {
            if let Some(r) = g.rules.get(i) {
                report.problems.push(Problem {
                    check: "left-recursion",
                    production: r.name.clone(),
                    line: r.line,
                    message: format!("{} is left-recursive", r.name),
                });
            }
        }
        let greedy = std::mem::take(&mut self.greedy);
        for (owner, e, _) in &greedy {
            if let GExpr::Opt(x) | GExpr::Rep(x) = e
                && self.is_nullable(x)
                && let Some(r) = g.rules.get(*owner)
            {
                report.problems.push(Problem {
                    check: "nullable",
                    production: r.name.clone(),
                    line: r.line,
                    message: "an option or repetition body can match the empty string".into(),
                });
            }
        }
        if !report.problems.is_empty() {
            return;
        }
        // Choices.
        for r in &g.rules {
            let mut alts: Vec<&'g [GExpr]> = Vec::new();
            fn find<'a>(e: &'a GExpr, out: &mut Vec<&'a [GExpr]>) {
                match e {
                    GExpr::Alt(items) => {
                        out.push(items);
                        items.iter().for_each(|x| find(x, out));
                    }
                    GExpr::Opt(x) | GExpr::Rep(x) => find(x, out),
                    GExpr::Seq(items) => items.iter().for_each(|x| find(x, out)),
                    GExpr::Sym(_) | GExpr::Rule(_) => {}
                }
            }
            find(&r.body, &mut alts);
            for items in alts {
                report.choices_checked += 1;
                for (i, a) in items.iter().enumerate() {
                    for (j, b) in items.iter().enumerate().skip(i + 1) {
                        self.budget = EXPANSION_BUDGET;
                        match self.separate(vec![Item::E(a)], vec![Item::E(b)], &mut Vec::new()) {
                            Outcome::Disjoint(k) => report.max_lookahead_used = report.max_lookahead_used.max(k),
                            Outcome::Conflict(witness, why) => report.problems.push(Problem {
                                check: "choice",
                                production: r.name.clone(),
                                line: r.line,
                                message: format!(
                                    "alternatives {} and {} can both match input starting {}: {why}",
                                    i + 1,
                                    j + 1,
                                    spell(&witness)
                                ),
                            }),
                        }
                    }
                }
            }
        }
        // Options and repetitions against their continuation.
        for (owner, e, cont) in greedy {
            let (GExpr::Opt(x) | GExpr::Rep(x)) = e else {
                continue;
            };
            report.greedy_checked += 1;
            self.budget = EXPANSION_BUDGET;
            if let Some(r) = g.rules.get(owner) {
                match self.separate(vec![Item::E(x)], cont, &mut Vec::new()) {
                    Outcome::Disjoint(k) => report.max_lookahead_used = report.max_lookahead_used.max(k),
                    Outcome::Conflict(witness, why) => report.problems.push(Problem {
                        check: "greedy",
                        production: r.name.clone(),
                        line: r.line,
                        message: format!(
                            "the {} body and its continuation can both match input starting {}: {why}",
                            if matches!(e, GExpr::Opt(_)) { "option" } else { "repetition" },
                            spell(&witness)
                        ),
                    }),
                }
            }
        }
    }
}

fn spell(symbols: &[Symbol]) -> String {
    if symbols.is_empty() {
        return "anywhere (empty prefix)".into();
    }
    symbols
        .iter()
        .map(Symbol::name)
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn problems(text: &str) -> Vec<&'static str> {
        let productions = ebnf::parse(text).unwrap_or_default();
        check(&productions, &["s"])
            .problems
            .iter()
            .map(|p| p.check)
            .collect()
    }

    #[test]
    fn builtin_grammar_is_normalised() {
        let report = match builtin() {
            Ok(_) => check(&ebnf::parse(WEAVE_EBNF).unwrap_or_default(), &START_SYMBOLS),
            Err(r) => r.clone(),
        };
        assert_eq!(report.problems, Vec::new());
        assert!(report.choices_checked > 20 && report.greedy_checked > 20);
    }

    #[test]
    fn structural_problems_are_reported() {
        assert_eq!(problems("s = \"a\" ; s = \"b\" ;"), vec!["duplicate"]);
        assert_eq!(problems("s = t ;"), vec!["undefined"]);
        assert_eq!(problems("s = \"a\" ; t = \"b\" ;"), vec!["unreachable"]);
        assert_eq!(
            problems("s = WORD ; WORD = ? letters ? ;"),
            vec!["special-sequence"]
        );
        assert_eq!(
            problems("s = IDENT ; IDENT = \"x\" ;"),
            vec!["special-sequence"]
        );
        assert_eq!(problems("s = \"a\", ? x ? ;"), vec!["special-sequence"]);
        assert_eq!(problems("s = \"a b\" ;"), vec!["terminal"]);
        assert_eq!(problems("s = \"@\" ;"), vec!["terminal"]);
        assert_eq!(problems("s = s, \"a\" | \"b\" ;"), vec!["left-recursion"]);
        assert_eq!(problems("s = { [ \"a\" ] }, \"b\" ;"), vec!["nullable"]);
        assert_eq!(problems("s = [ \"a\" ] ;"), vec!["nullable"]);
        let productions = ebnf::parse("t = \"a\" ;").unwrap_or_default();
        assert_eq!(
            check(&productions, &["s"])
                .problems
                .first()
                .map(|p| p.check),
            Some("start")
        );
    }

    #[test]
    fn ordered_choice_hazards_are_reported() {
        // An earlier alternative that is a prefix of a later one shadows it.
        assert_eq!(
            problems("s = ( \"a\" | \"a\", \"b\" ), \"c\" ;"),
            vec!["choice"]
        );
        // The longer alternative first is still reported: both can match.
        assert_eq!(
            problems("s = ( \"a\", \"b\" | \"a\" ), \"c\" ;"),
            vec!["choice"]
        );
        // An identifier overlaps a contextual word (LEX-REQ-2).
        assert_eq!(
            problems("s = ( IDENT | \"let\" ), \"c\" ; IDENT = ? i ? ;"),
            vec!["choice"]
        );
        // A greedy option that can take a token its continuation needs.
        assert_eq!(
            problems("s = [ \"a\" ], IDENT ; IDENT = ? i ? ;"),
            vec!["greedy"]
        );
        // A greedy repetition whose continuation starts the same way.
        assert_eq!(problems("s = { \"a\" }, \"a\" ;"), vec!["greedy"]);
        // A shared prefix that is separated later is fine.
        assert_eq!(
            problems("s = \"a\", \"b\", \"c\" | \"a\", \"b\", \"d\" ;"),
            Vec::<&str>::new()
        );
        // A pair never separated within the bound is reported.
        let same = format!(
            "s = {0} | {0}, \"x\" ;",
            ["\"a\""; MAX_LOOKAHEAD + 1].join(", ")
        );
        assert_eq!(problems(&same), vec!["choice"]);
    }

    #[test]
    fn the_unnormalised_await_option_is_a_greedy_conflict() {
        // The pre-normalisation spelling of let-call: `[ "await" ]` before a call whose
        // operation name may itself be the word await.
        let text = "s = \"let\", IDENT, \"=\", [ \"await\" ], call, NL ; call = IDENT, \"(\", \")\" ; \
                    IDENT = ? i ? ; NL = ? n ? ;";
        assert_eq!(problems(text), vec!["greedy"]);
        let fixed = "s = \"let\", IDENT, \"=\", ( \"await\", call | call ), NL ; call = IDENT, \"(\", \")\" ; \
                     IDENT = ? i ? ; NL = ? n ? ;";
        assert_eq!(problems(fixed), Vec::<&str>::new());
    }

    #[test]
    fn n2_delta_reads_as_ebnf_and_resolves_against_the_base() {
        let base = ebnf::parse(WEAVE_EBNF).unwrap_or_default();
        let delta = ebnf::parse(N2_DELTA_EBNF);
        assert!(delta.is_ok());
        let delta = delta.unwrap_or_default();
        assert!(!delta.is_empty());
        for p in &delta {
            p.expr.walk(&mut |e| {
                if let Expr::Ref(name) = e {
                    assert!(
                        delta.iter().chain(base.iter()).any(|q| &q.name == name),
                        "{name} in the N2 delta is undefined"
                    );
                }
            });
        }
        // The delta stays out of the parser: none of its new productions are in the base.
        let g = builtin().ok();
        assert!(g.is_some_and(
            |g| g.rule("evidence-decl").is_none() && g.rule("correlation-clause").is_none()
        ));
    }
}
