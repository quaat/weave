#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""P0 reference evaluator: parse, check and evaluate pure files (docs/chapters/pure.rst).

Written from the P0 chapter, independently of the Rust crates. Parsing uses the
Lark parser that ``grammar_audit.py`` generates from ``grammar/weave.ebnf`` and a
layout pass that keeps source positions; static checking and evaluation follow the
chapter's rules and its checking order. It is the oracle of the Rust/Python
differential (``p0_differential.py``), not a production implementation.

    python3 scripts/p0_reference.py check FILE [--json]
    python3 scripts/p0_reference.py run FILE --entry NAME [--args JSON] [--fuel N]
                                     [--max-depth N] [--int-bits N] [--json]

Exit status as for the ``weave`` command: 0 checked or a value, 1 a rejected file or
an invalid run request, 2 usage, 3 a pure fault, 4 an exhausted budget.

Evaluation never uses the Python stack per Weave call: each call is a generator
on an explicit stack. Within one call, expressions recurse to their nesting depth,
which the source bounds.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from grammar_audit import generate  # noqa: E402  (the independent generated grammar)
from lark import Lark, Token, Tree, UnexpectedInput  # noqa: E402

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)
sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

CODES = json.loads((ROOT / "diagnostics.json").read_text(encoding="utf-8"))["codes"]
DEFAULT_BUDGETS = {"fuel": 1_000_000, "depth": 10_000, "int_bits": 65_536}
# Nesting limits (pure.rst, "Nesting limits"), the same as the Rust checker's.
SYNTAX_DEPTH_LIMIT = 300
EXPR_DEPTH_LIMIT = 256
TYPE_DEPTH_LIMIT = 64
BUILTIN_TYPES = ("Int", "Bool", "List")
BUILTIN_CONSTANTS = ("true", "false")
PRIMITIVES = {"length": 1, "is_empty": 1, "head": 1, "tail": 1, "cons": 2, "div": 2, "mod": 2, "not": 1}
BUILTINS = set(BUILTIN_TYPES) | set(BUILTIN_CONSTANTS) | set(PRIMITIVES)
MARK_IN, MARK_OUT = "⟪", "⟫"

# A span is (start_line, start_column, end_line, end_column), 1-based, end exclusive.
NOWHERE = (1, 1, 1, 1)


class Diagnostic(Exception):
    def __init__(self, code: str, message: str, span=NOWHERE, stage: str = "static"):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.span, self.stage = code, message, span, stage

    def document(self, file: str) -> dict:
        """The diagnostic as a weave-diagnostic-v1 document."""
        entry = CODES[self.code]
        sl, sc, el, ec = self.span
        return {"format": "weave-diagnostic-v1", "code": self.code, "category": entry["category"],
                "rule": entry["rule"], "secondary_rules": list(entry["secondary_rules"]),
                "severity": "error", "stage": self.stage, "message": self.message,
                "span": {"file": file or "<input>", "start": {"line": sl, "column": sc},
                         "end": {"line": el, "column": ec}},
                "related": [], "details": {}}


def span_of(a, b=None):
    b = a if b is None else b
    return (a[0], a[1], b[2], b[3])


# ---------------------------------------------------------------- parsing

class LayoutError(ValueError):
    pass


def layout(source: str):
    """Four-space layout (lexical chapter) with markers, keeping positions.

    Returns the marked text and, per output line, (source line, marker count)."""
    if MARK_IN in source or MARK_OUT in source:
        raise ValueError("internal layout marker in source")
    out, where, levels, previous = [], [], [0], None
    lines = source.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for number, raw in enumerate(lines, 1):
        if raw.endswith("\r"):
            raw = raw[:-1]
        if "\t" in raw:
            raise LayoutError(number, raw.index("\t") + 1, "Tabs are not allowed.")
        if "\r" in raw:
            raise ValueError(number, raw.index("\r") + 1, "carriage return inside a line")
        code = raw.split("#", 1)[0].rstrip(" ")
        if not code.strip(" "):
            continue
        indent = len(code) - len(code.lstrip(" "))
        if indent % 4:
            raise LayoutError(number, 1, "Indentation is not a multiple of four spaces.")
        if previous is None and indent:
            raise LayoutError(number, 1, "The first line must not be indented.")
        marks = ""
        if indent > levels[-1]:
            if indent != levels[-1] + 4 or not previous.endswith(":"):
                raise LayoutError(number, 1, "Unexpected nested block.")
            levels.append(indent)
            marks += MARK_IN
        while indent < levels[-1]:
            levels.pop()
            marks += MARK_OUT
        if indent != levels[-1]:
            raise LayoutError(number, 1, "Dedent does not return to an enclosing level.")
        out.append(marks + code + "\n")
        where.append((number, len(marks)))
        previous = code
    tail = MARK_OUT * (len(levels) - 1)
    if tail:
        out.append(tail)
        last = where[-1][0] if where else 1
        where.append((last, len(tail)))
    return "".join(out), where


_PARSER = None


def lark_parser() -> Lark:
    global _PARSER
    if _PARSER is None:
        grammar, _ = generate((ROOT / "grammar/weave.ebnf").read_text(encoding="utf-8"))
        _PARSER = Lark(grammar, start="pure_file", parser="earley", lexer="dynamic",
                       propagate_positions=True, keep_all_tokens=True)
    return _PARSER


class Positions:
    def __init__(self, where):
        self.where = where

    def point(self, line, column):
        if not self.where:
            return 1, 1
        source_line, shift = self.where[min(max(line, 1), len(self.where)) - 1]
        return source_line, max(1, column - shift)

    def token(self, t: Token):
        return (*self.point(t.line, t.column), *self.point(t.end_line, t.end_column))

    def node(self, tree: Tree):
        """From the node's first to its last source token (iterative, for deep trees)."""
        first = self._edge(tree, 0)
        last = self._edge(tree, -1)
        if first is None or last is None:
            return NOWHERE
        return span_of(self.token(first), self.token(last))

    @staticmethod
    def _edge(tree: Tree, end: int):
        """The first (end=0) or last (end=-1) source token under tree, by an explicit stack."""
        stack = [tree]
        while stack:
            node = stack.pop()
            if isinstance(node, Token):
                if node.value not in (MARK_IN, MARK_OUT, "\n"):
                    return node
                continue
            stack.extend(node.children if end == -1 else reversed(node.children))
        return None


def parse(source: str):
    """The Lark tree of a pure file and the position map; E001 or E500 on failure."""
    try:
        text, where = layout(source)
    except LayoutError as e:
        line, column, message = e.args
        raise Diagnostic("E001", message, (line, column, line, column + 1), "layout")
    except ValueError as e:
        line, column, message = e.args if len(e.args) == 3 else (1, 1, str(e))
        raise Diagnostic("E500", message, (line, column, line, column + 1), "lexical")
    positions = Positions(where)
    try:
        tree = lark_parser().parse(text)
    except UnexpectedInput as e:
        line, column = positions.point(getattr(e, "line", 1) or 1, getattr(e, "column", 1) or 1)
        raise Diagnostic("E500", f"Not P0 pure-file syntax: {type(e).__name__}.", (line, column, line, column + 1), "syntax")
    check_syntax_depth(tree, positions)
    return tree, positions


def check_syntax_depth(tree: Tree, positions) -> None:
    """P0-FILE-1: no production nested deeper than SYNTAX_DEPTH_LIMIT (iterative walk).

    Every rule node counts, the root pure_file as 1; UINT is a token here, as it is
    a lexical production in the chapter's count."""
    stack = [(tree, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > SYNTAX_DEPTH_LIMIT:
            raise Diagnostic("E500", f"Nesting exceeds the P0 syntax depth limit of {SYNTAX_DEPTH_LIMIT} productions.",
                             positions.node(node), "limit")
        stack.extend((c, depth + 1) for c in reversed(node.children) if isinstance(c, Tree))


# ---------------------------------------------------------------- lowering

def kids(tree: Tree, name: str):
    return [c for c in tree.children if isinstance(c, Tree) and c.data == name]


def kid(tree: Tree, name: str) -> Tree:
    found = kids(tree, name)
    if not found:
        raise Diagnostic("E500", f"internal: missing {name}", NOWHERE, "internal")
    return found[0]


@dataclass
class Name:
    text: str
    span: tuple


@dataclass
class TypeAst:
    name: Name
    args: list | None
    span: tuple


@dataclass
class Expr:
    kind: str
    span: tuple
    a: object = None
    b: object = None
    c: object = None
    d: object = None
    depth: int = 1


def expr_depth(e: Expr) -> int:
    """Expression depth from the children's depths (pure.rst, "Nesting limits")."""
    if e.kind == "int":
        return 1
    if e.kind == "list":
        return 1 + max((x.depth for x in e.a), default=0)
    if e.kind == "neg":
        return 1 + e.a.depth
    if e.kind == "bin":
        return 1 + max(e.b.depth, e.c.depth)
    args = [max(v.depth, label.depth if label is not None else 0) for label, v, _ in (e.c or [])]
    return max(len(e.b), 1) + max(args, default=0)


def mk(kind, span, *fields) -> Expr:
    """An expression node; E500 at stage limit beyond EXPR_DEPTH_LIMIT."""
    e = Expr(kind, span, *fields)
    e.depth = expr_depth(e)
    if e.depth > EXPR_DEPTH_LIMIT:
        raise Diagnostic("E500", f"Expression nesting exceeds the P0 expression depth limit of {EXPR_DEPTH_LIMIT}.",
                         span, "limit")
    return e


@dataclass
class Stmt:
    kind: str
    span: tuple
    keyword: tuple
    name: Name | None = None
    value: Expr | None = None
    then: list | None = None
    otherwise: list | None = None
    then_span: tuple | None = None
    else_span: tuple | None = None


@dataclass
class Block:
    stmts: list
    span: tuple


class Lower:
    def __init__(self, positions: Positions):
        self.p = positions

    def name(self, tok: Token) -> Name:
        return Name(tok.value, self.p.token(tok))

    def leaf(self, tree: Tree, index: int) -> Name:
        """The index-th direct token of tree: names are found by position, since
        contextual words are valid names (``let let = 1``)."""
        return self.name([t for t in tree.children if isinstance(t, Token)][index])

    def idents(self, tree: Tree):
        return [self.name(t) for t in tree.children
                if isinstance(t, Token) and (t.value[:1].isalpha() or t.value[:1] == "_")]

    def file(self, tree: Tree):
        items = []
        for item in kids(tree, "pure_item"):
            inner = item.children[0]
            items.append(self.record(inner) if inner.data == "record_decl" else self.function(inner))
        return items

    def record(self, tree):
        name = self.leaf(tree, 1)
        fields = [(self.leaf(f, 0), self.type(kid(f, "pure_type"))) for f in kids(tree, "field_decl")]
        return ("record", name, fields, self.p.node(tree))

    def function(self, tree):
        name = self.leaf(tree, 1)
        params = []
        for plist in kids(tree, "fn_params"):
            for p in kids(plist, "fn_param"):
                params.append((self.leaf(p, 0), self.type(kid(p, "pure_type"))))
        return ("fn", name, params, self.type(kid(tree, "pure_type")), self.block(kid(tree, "pure_block")),
                self.p.node(tree))

    def type(self, tree):
        name = self.leaf(tree, 0)
        bracket = any(isinstance(c, Token) and c.value == "[" for c in tree.children)
        args = [self.type(t) for t in kids(tree, "pure_type")] if bracket else None
        return TypeAst(name, args, self.p.node(tree))

    def block(self, tree) -> Block:
        stmts = [self.statement(s.children[0]) for s in kids(tree, "statement")]
        span = span_of(stmts[0].span, stmts[-1].span) if stmts else self.p.node(tree)
        return Block(stmts, span)

    def statement(self, tree) -> Stmt:
        keyword = self.p.token(tree.children[0])
        start = keyword
        if tree.data == "let_stmt":
            value = self.expr(kid(tree, "expr"))
            return Stmt("let", span_of(start, value.span), keyword, name=self.leaf(tree, 1), value=value)
        if tree.data == "return_stmt":
            value = self.expr(kid(tree, "expr"))
            return Stmt("return", span_of(start, value.span), keyword, value=value)
        if tree.data == "if_stmt":
            blocks = [self.block(b) for b in kids(tree, "pure_block")]
            then = blocks[0]
            otherwise = blocks[1] if len(blocks) > 1 else None
            end = (otherwise or then).span
            return Stmt("if", span_of(start, end), keyword, value=self.expr(kid(tree, "expr")),
                        then=then, otherwise=otherwise)
        if tree.data == "fork_stmt":
            block = self.block(kid(tree, "pure_block"))
            return Stmt("fork", span_of(start, block.span), keyword, then=block)
        raise Diagnostic("E500", f"internal: statement {tree.data}", NOWHERE, "internal")

    OPS = {"or": "or", "and": "and", "<": "<", "<=": "<=", ">": ">", ">=": ">=", "==": "==", "!=": "!=",
           "+": "+", "-": "-", "*": "*"}

    def fold(self, tree, operand):
        """Left fold; a binary expression spans its operands' syntax nodes, parentheses included."""
        acc, pending, first = None, None, None
        for c in tree.children:
            if isinstance(c, Tree) and c.data == operand:
                rhs = self.dispatch(c)
                if acc is None:
                    first = self.p.node(c)
                    acc = rhs
                else:
                    acc = mk("bin", span_of(first, self.p.node(c)), pending, acc, rhs)
            elif isinstance(c, Tree) and c.data == "compare_op":
                pending = c.children[0].value
            elif isinstance(c, Token) and c.value in self.OPS:
                pending = c.value
        return acc

    def dispatch(self, tree):
        return {"expr": lambda t: self.fold(t, "conjunction"),
                "conjunction": lambda t: self.fold(t, "comparison"),
                "comparison": lambda t: self.fold(t, "sum"),
                "sum": lambda t: self.fold(t, "product"),
                "product": lambda t: self.fold(t, "unary"),
                "unary": self.unary, "primary": self.primary}[tree.data](tree)

    def expr(self, tree):
        return self.fold(tree, "conjunction")

    def unary(self, tree):
        inner = kids(tree, "unary")
        if inner:
            return mk("neg", self.p.node(tree), self.unary(inner[0]))
        return self.primary(kid(tree, "primary"))

    def primary(self, tree):
        first = tree.children[0]
        if isinstance(first, Token) and first.type == "UINT":
            return mk("int", self.p.token(first), first.value)
        if isinstance(first, Token) and first.value == "(":
            return self.expr(kid(tree, "expr"))
        if isinstance(first, Tree) and first.data == "list_literal":
            return mk("list", self.p.node(first), [self.expr(e) for e in kids(first, "expr")])
        if isinstance(first, Tree) and first.data == "name_expr":
            return self.name_expr(first)
        raise Diagnostic("E500", "internal: primary", NOWHERE, "internal")

    def name_expr(self, tree):
        prefix, parts, call = None, [], None
        for c in tree.children:
            if isinstance(c, Token):
                if c.value == "(":
                    call = []
                elif c.value not in (")", ".") and call is None:
                    parts.append(self.name(c))
            elif c.data == "prefixed":
                word = parts.pop()
                if word.text != "await":
                    raise Diagnostic("E500", f"'{word.text}' before a qualified name is not P0 syntax.", word.span, "syntax")
                prefix = word
                parts.extend(self.idents(c))
            elif c.data == "call_args":
                call = []
                for arg in kids(c, "call_arg"):
                    exprs = [self.expr(e) for e in kids(arg, "expr")]
                    label, value = (None, exprs[0]) if len(exprs) == 1 else (exprs[0], exprs[1])
                    call.append((label, value, self.p.node(arg)))
        return mk("path", self.p.node(tree), prefix, parts, call)


# ---------------------------------------------------------------- types

INT, BOOL = ("Int",), ("Bool",)


def LIST(t):
    return ("List", t)


def spell(t, records) -> str:
    if t[0] == "List":
        return f"List[{spell(t[1], records)}]"
    if t[0] == "Record":
        return records[t[1]]["name"]
    return t[0]


@dataclass
class Checked:
    records: list
    functions: list
    names: dict = field(default_factory=dict)


def fail(code, message, span):
    raise Diagnostic(code, message, span, "static")


class Checker:
    def __init__(self):
        self.globals = {}
        self.records = []
        self.signatures = []
        self.depths = []
        self.scopes = []
        self.slots = 0
        self.calls = []

    # -- declarations
    def resolve(self, t: TypeAst):
        name, args = t.name.text, t.args
        if name in ("Int", "Bool"):
            if args is not None:
                fail("E504", f"{name} takes no type arguments.", t.span)
            return (name,)
        if name == "List":
            if args is None or len(args) != 1:
                fail("E504", "List takes exactly one element type.", t.span)
            return LIST(self.resolve(args[0]))
        kind = self.globals.get(name)
        if kind and kind[0] == "record":
            if args is not None:
                fail("E504", f"Record type {name} takes no type arguments.", t.span)
            return ("Record", kind[1])
        if args is not None:
            fail("E504", f"{name}[...] is an indexed nominal type such as a handle.", t.span)
        fail("E504", f"Unknown type {name}.", t.span)

    def record_cycle(self, start):
        def mentions(t, out):
            if t[0] == "Record":
                out.append(t[1])
            elif t[0] == "List":
                mentions(t[1], out)
        work, seen = [], set()
        for _, t in self.records[start]["fields"]:
            mentions(t, work)
        while work:
            r = work.pop()
            if r == start:
                return True
            if r not in seen:
                seen.add(r)
                for _, t in self.records[r]["fields"]:
                    mentions(t, work)
        return False

    def lookup(self, name):
        for scope in reversed(self.scopes):
            for local in reversed(scope):
                if local[0] == name:
                    return local
        return None

    def fresh(self, name: Name):
        if self.lookup(name.text) or name.text in self.globals or name.text in BUILTINS:
            fail("E506", f"{name.text} would shadow another name.", name.span)

    def bind(self, name, ty):
        slot = self.slots
        self.slots += 1
        self.scopes[-1].append((name, slot, ty))
        return slot

    def run(self, items):
        records = [i for i in items if i[0] == "record"]
        fns = [i for i in items if i[0] == "fn"]
        nr = nf = 0
        for item in items:
            name = item[1]
            if name.text in BUILTINS:
                fail("E501", f"{name.text} is a built-in name.", name.span)
            if name.text in self.globals:
                fail("E501", f"{name.text} is declared twice.", name.span)
            if item[0] == "record":
                self.globals[name.text] = ("record", nr)
                nr += 1
            else:
                self.globals[name.text] = ("fn", nf)
                nf += 1
        self.records = [{"name": r[1].text, "fields": [], "name_span": r[1].span} for r in records]
        for i, r in enumerate(records):
            fields = []
            for fname, ftype in r[2]:
                if any(n == fname.text for n, _ in fields):
                    fail("E502", f"Field {fname.text} is declared twice.", fname.span)
                fields.append((fname.text, self.resolve(ftype)))
            self.records[i]["fields"] = fields
        for i, r in enumerate(records):
            if self.record_cycle(i):
                fail("E503", f"Record {r[1].text} is recursive.", r[1].span)
        self.depths = self.record_depths()
        for i, r in enumerate(records):
            if self.depths[i] > TYPE_DEPTH_LIMIT:
                self.type_limit(r[1].span)
        for f in fns:
            params = []
            for pname, ptype in f[2]:
                if any(n == pname.text for n, _ in params):
                    fail("E506", f"Parameter {pname.text} is declared twice.", pname.span)
                self.fresh(pname)
                ty = self.resolve(ptype)
                self.depth_ok(ty, ptype.span)
                params.append((pname.text, ty))
            ret = self.resolve(f[3])
            self.depth_ok(ret, f[3].span)
            self.signatures.append((params, ret))
        functions, graph = [], []
        for index, f in enumerate(fns):
            self.structure(f[4])
            params, ret = self.signatures[index]
            self.scopes, self.slots, self.calls = [[]], 0, []
            for pname, ptype in params:
                self.bind(pname, ptype)
            body = self.block(f[4], ret)
            graph.append(sorted(self.calls, key=lambda c: (c[1][0], c[1][1])))
            functions.append({"name": f[1].text, "params": params, "ret": ret, "body": body,
                              "locals": self.slots, "name_span": f[1].span})
        reach = [self.reachable(graph, i) for i in range(len(graph))]
        for f, calls in enumerate(graph):
            for g, span in calls:
                if g != f and f in reach[g]:
                    fail("E516", f"{functions[f]['name']} and {functions[g]['name']} call each other.", span)
        return Checked(self.records, functions)

    @staticmethod
    def reachable(graph, start):
        seen, work = set(), [g for g, _ in graph[start]]
        while work:
            g = work.pop()
            if g not in seen:
                seen.add(g)
                work.extend(h for h, _ in graph[g])
        return seen

    def structure(self, block: Block):
        terminal = False
        for st in block.stmts:
            if terminal:
                fail("E515", "Statement after a terminal statement.", st.span)
            if st.kind == "fork":
                fail("E514", "fork is not P0.", st.keyword)
            if st.kind == "if":
                self.structure(st.then)
                if st.otherwise is None:
                    fail("E515", "if without else.", st.keyword)
                self.structure(st.otherwise)
                terminal = True
            elif st.kind == "return":
                terminal = True
        if not terminal:
            fail("E515", "Block does not end in a terminal statement.", block.stmts[-1].span if block.stmts else block.span)

    # -- bodies: typed nodes are tuples (kind, type, span, ...)
    def block(self, block: Block, ret):
        self.scopes.append([])
        lets, end = [], None
        for st in block.stmts:
            if st.kind == "let":
                value = self.synth(st.value, None)
                self.fresh(st.name)
                lets.append((self.bind(st.name.text, value[1]), value))
            elif st.kind == "return":
                end = ("return", self.check(st.value, ret))
            elif st.kind == "if":
                cond = self.check(st.value, BOOL)
                end = ("if", cond, self.block(st.then, ret), self.block(st.otherwise, ret))
        self.scopes.pop()
        return (lets, end)

    def check(self, e: Expr, expected):
        typed = self.synth(e, expected)
        if typed[1] != expected:
            fail("E510", f"Expected {spell(expected, self.records)}, found {spell(typed[1], self.records)}.", e.span)
        return typed

    # -- type depth (pure.rst, "Nesting limits")
    @staticmethod
    def type_limit(span):
        raise Diagnostic("E500", f"Type nesting exceeds the P0 type depth limit of {TYPE_DEPTH_LIMIT}.", span, "limit")

    def ty_depth(self, t, depths=None) -> int:
        """Int and Bool 1, List[T] one more than T, a record its depth (iterative)."""
        depths = self.depths if depths is None else depths
        lists = 0
        while t[0] == "List":
            lists, t = lists + 1, t[1]
        if t[0] != "Record":
            return lists + 1
        d = depths[t[1]]
        return lists + (d if d is not None else 1)

    def record_depths(self) -> list:
        """Each record's depth: one more than its deepest field type, by an explicit-stack
        post-order walk of the record graph (acyclic once E503 has passed)."""
        def base(t):
            while t[0] == "List":
                t = t[1]
            return t[1] if t[0] == "Record" else None
        depth = [None] * len(self.records)
        for start in range(len(self.records)):
            stack = [start]
            while stack:
                i = stack[-1]
                if depth[i] is not None:
                    stack.pop()
                    continue
                fields = self.records[i]["fields"]
                pending = next((j for j in (base(t) for _, t in fields) if j is not None and depth[j] is None), None)
                if pending is not None:
                    stack.append(pending)
                    continue
                depth[i] = 1 + max((self.ty_depth(t, depth) for _, t in fields), default=0)
                stack.pop()
        return [d if d is not None else 1 for d in depth]

    def depth_ok(self, t, span):
        if self.ty_depth(t) > TYPE_DEPTH_LIMIT:
            self.type_limit(span)

    def synth(self, e: Expr, expected):
        typed = self.synth_inner(e, expected)
        self.depth_ok(typed[1], e.span)
        return typed

    def synth_inner(self, e: Expr, expected):
        if e.kind == "int":
            return ("int", INT, e.span, int(e.a))
        if e.kind == "list":
            return self.list(e, expected)
        if e.kind == "neg":
            return ("neg", INT, e.span, self.check(e.a, INT))
        if e.kind == "bin":
            return self.binary(e)
        prefix, parts, call = e.a, e.b, e.c
        if prefix is not None:
            fail("E513", "await in pure code.", e.span)
        if call is not None:
            return self.call(e, parts, call, expected)
        return self.path(parts)

    def list(self, e, expected):
        items = e.a
        if expected is not None and expected[0] == "List":
            return ("list", expected, e.span, [self.check(i, expected[1]) for i in items])
        if expected is not None and not items:
            fail("E510", f"Expected {spell(expected, self.records)}, found a list.", e.span)
        if not items:
            fail("E511", "[] needs an expected list type.", e.span)
        first = self.synth(items[0], None)
        rest = [self.check(i, first[1]) for i in items[1:]]
        return ("list", LIST(first[1]), e.span, [first] + rest)

    def binary(self, e):
        op, l, r = e.a, e.b, e.c
        if op in ("+", "-", "*"):
            return ("arith", INT, e.span, op, self.check(l, INT), self.check(r, INT))
        if op in ("<", "<=", ">", ">="):
            return ("cmp", BOOL, e.span, op, self.check(l, INT), self.check(r, INT))
        if op in ("==", "!="):
            left = self.synth(l, None)
            if left[1] not in (INT, BOOL):
                fail("E510", f"{op} compares Int or Bool values.", l.span)
            return ("cmp", BOOL, e.span, op, left, self.check(r, left[1]))
        return (op, BOOL, e.span, self.check(l, BOOL), self.check(r, BOOL))

    def path(self, parts):
        root, fields = parts[0], parts[1:]
        local = self.lookup(root.text)
        if local is not None:
            current = ("local", local[2], root.span, local[1])
        elif not fields and root.text in BUILTIN_CONSTANTS:
            return ("bool", BOOL, root.span, root.text == "true")
        else:
            fail("E505", f"{root.text} is not a value in scope.", root.span)
        for f in fields:
            if current[1][0] != "Record":
                fail("E509", f".{f.text} needs a record.", f.span)
            record = self.records[current[1][1]]
            index = next((i for i, (n, _) in enumerate(record["fields"]) if n == f.text), None)
            if index is None:
                fail("E509", f"Record {record['name']} has no field {f.text}.", f.span)
            current = ("field", record["fields"][index][1], span_of(current[2], f.span), current, index)
        return current

    def positional(self, args, arity, span):
        for label, _, aspan in args:
            if label is not None:
                fail("E507", "Named arguments construct records.", aspan)
        if len(args) != arity:
            fail("E507", f"Expected {arity} arguments, got {len(args)}.", span)

    def call(self, e, parts, args, expected):
        if len(parts) > 1:
            fail("E512", f"{'.'.join(p.text for p in parts)}(...) is an operation call.", e.span)
        name = parts[0].text
        if name in PRIMITIVES:
            self.positional(args, PRIMITIVES[name], e.span)
            return self.primitive(e, name, [a[1] for a in args], expected)
        kind = self.globals.get(name)
        if kind is not None and kind[0] == "fn":
            params, ret = self.signatures[kind[1]]
            self.positional(args, len(params), e.span)
            typed = [self.check(a[1], t) for a, (_, t) in zip(args, params)]
            self.calls.append((kind[1], e.span))
            return ("call", ret, e.span, kind[1], typed)
        if kind is not None and kind[0] == "record":
            return self.construct(e, kind[1], args)
        fail("E507", f"{name} is not a function.", parts[0].span)

    def primitive(self, e, name, args, expected):
        if name in ("div", "mod"):
            return ("prim", INT, e.span, name, [self.check(a, INT) for a in args])
        if name == "not":
            return ("prim", BOOL, e.span, name, [self.check(args[0], BOOL)])
        if name == "cons":
            if expected is not None and expected[0] == "List":
                typed = [self.check(args[0], expected[1]), self.check(args[1], expected)]
                return ("prim", expected, e.span, name, typed)
            head = self.synth(args[0], None)
            return ("prim", LIST(head[1]), e.span, name, [head, self.check(args[1], LIST(head[1]))])
        xs = self.synth(args[0], None)
        if xs[1][0] != "List":
            fail("E510", f"{name} needs a list.", args[0].span)
        result = {"length": INT, "is_empty": BOOL, "head": xs[1][1], "tail": xs[1]}[name]
        return ("prim", result, e.span, name, [xs])

    def construct(self, e, r, args):
        record = self.records[r]
        names = [n for n, _ in record["fields"]]
        given = []
        for label, value, aspan in args:
            if label is None:
                fail("E507", "Records are constructed with named arguments.", aspan)
            if not (label.kind == "path" and label.a is None and label.c is None and len(label.b) == 1):
                fail("E507", "A field name comes before ':'.", label.span)
            fname = label.b[0]
            if fname.text not in names:
                fail("E508", f"Record {record['name']} has no field {fname.text}.", fname.span)
            index = names.index(fname.text)
            if any(i == index for i, _ in given):
                fail("E508", f"Field {fname.text} is given twice.", fname.span)
            given.append((index, value))
        if len(given) != len(names):
            fail("E508", f"Record {record['name']} construction misses fields.", e.span)
        typed = [(i, self.check(v, record["fields"][i][1])) for i, v in given]
        return ("construct", ("Record", r), e.span, r, typed)


def check(source: str) -> Checked:
    """Parse, lower and check; raises Diagnostic for the first violation."""
    tree, positions = parse(source)
    items = Lower(positions).file(tree)
    return Checker().run(items)


# ---------------------------------------------------------------- evaluation

class Fault(Exception):
    def __init__(self, kind, code, span):
        self.kind, self.code, self.span = kind, code, span


class Exhausted(Exception):
    def __init__(self, kind, code, span):
        self.kind, self.code, self.span = kind, code, span


# A list is None (empty) or (head, tail, length): persistent, shares suffixes.
def cons(x, xs):
    return (x, xs, 1 + (xs[2] if xs else 0))


def to_list(values):
    out = None
    for v in reversed(values):
        out = cons(v, out)
    return out


def iterate(xs):
    while xs is not None:
        yield xs[0]
        xs = xs[1]


class Machine:
    def __init__(self, program: Checked, budgets: dict):
        self.program, self.budgets = program, budgets
        self.fuel = self.depth = self.bits = 0
        self.active = 0

    def admit(self, n: int, span):
        """P0-BUDGET-4."""
        size = abs(n).bit_length()
        if size > self.budgets["int_bits"]:
            raise Exhausted("int-size", "E532", span)
        self.bits = max(self.bits, size)
        return n

    def enter(self, span):
        """P0-EVAL-3: fuel first (P0-BUDGET-2), then depth (P0-BUDGET-3)."""
        if self.fuel >= self.budgets["fuel"]:
            raise Exhausted("fuel", "E530", span)
        self.fuel += 1
        if self.active >= self.budgets["depth"]:
            raise Exhausted("depth", "E531", span)
        self.active += 1
        self.depth = max(self.depth, self.active)

    def body(self, f: int, args: list):
        function = self.program.functions[f]
        env = list(args) + [None] * (function["locals"] - len(args))
        lets, end = function["body"]
        while True:
            for slot, value in lets:
                env[slot] = yield from self.eval(value, env)
            if end[0] == "return":
                return (yield from self.eval(end[1], env))
            cond = yield from self.eval(end[1], env)
            lets, end = end[2] if cond else end[3]

    def eval(self, e, env):
        kind, span = e[0], e[2]
        if kind == "int":
            return self.admit(e[3], span)
        if kind == "bool":
            return e[3]
        if kind == "local":
            return env[e[3]]
        if kind == "field":
            record = yield from self.eval(e[3], env)
            return record[2][e[4]]
        if kind == "neg":
            return self.admit(-(yield from self.eval(e[3], env)), span)
        if kind == "arith":
            a = yield from self.eval(e[4], env)
            b = yield from self.eval(e[5], env)
            return self.admit(a + b if e[3] == "+" else a - b if e[3] == "-" else a * b, span)
        if kind == "cmp":
            a = yield from self.eval(e[4], env)
            b = yield from self.eval(e[5], env)
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[e[3]]
        if kind == "and":
            left = yield from self.eval(e[3], env)
            return (yield from self.eval(e[4], env)) if left else False
        if kind == "or":
            left = yield from self.eval(e[3], env)
            return True if left else (yield from self.eval(e[4], env))
        if kind == "list":
            values = []
            for item in e[3]:
                values.append((yield from self.eval(item, env)))
            return to_list(values)
        if kind == "construct":
            fields = [None] * len(self.program.records[e[3]]["fields"])
            for index, value in e[4]:
                fields[index] = yield from self.eval(value, env)
            return ("record", e[3], tuple(fields))
        if kind == "call":
            args = []
            for a in e[4]:
                args.append((yield from self.eval(a, env)))
            return (yield ("call", e[3], args, span))
        if kind == "prim":
            args = []
            for a in e[4]:
                args.append((yield from self.eval(a, env)))
            return self.primitive(e[3], args, span)
        raise RuntimeError(f"internal: {kind}")

    def primitive(self, name, args, span):
        if name in ("div", "mod"):
            a, d = args
            if d == 0:
                raise Fault("division-by-zero", "E520", span)
            r = a % abs(d)              # 0 <= r < abs(d)   (D3)
            q = (a - r) // d            # exact: a - r is a multiple of d
            return self.admit(q if name == "div" else r, span)
        if name == "not":
            return not args[0]
        if name == "cons":
            return cons(args[0], args[1])
        xs = args[0]
        if name == "length":
            return self.admit(xs[2] if xs else 0, span)
        if name == "is_empty":
            return xs is None
        if xs is None:
            raise Fault("empty-list", "E521", span)
        return xs[0] if name == "head" else xs[1]

    def run(self, f: int, args: list, entry_span):
        stack = []

        def call(g, values, span):
            self.enter(span)
            stack.append(self.body(g, values))

        call(f, args, entry_span)
        value = None
        while stack:
            try:
                request = stack[-1].send(value)
            except StopIteration as done:
                stack.pop()
                self.active -= 1
                value = done.value
                continue
            _, g, values, span = request
            call(g, values, span)
            value = None
        return value


def decode(json_value, ty, program: Checked, path: str):
    """P0-RUN-1: a JSON argument as a value of type ty."""
    def bad(message):
        raise Diagnostic("E540", f"Argument {path}: {message}.", NOWHERE, "run")
    if ty == INT:
        if isinstance(json_value, bool) or not isinstance(json_value, int):
            bad("expected Int")
        return json_value
    if ty == BOOL:
        if not isinstance(json_value, bool):
            bad("expected Bool")
        return json_value
    if ty[0] == "List":
        if not isinstance(json_value, list):
            bad("expected a list")
        return to_list([decode(v, ty[1], program, f"{path}[{i}]") for i, v in enumerate(json_value)])
    record = program.records[ty[1]]
    if not isinstance(json_value, dict):
        bad(f"expected record {record['name']}")
    if getattr(json_value, "duplicate", False):
        bad("a field appears twice")
    names = [n for n, _ in record["fields"]]
    if set(json_value) - set(names) or set(names) - set(json_value):
        bad(f"record {record['name']} needs exactly the fields {', '.join(names)}")
    return ("record", ty[1], tuple(decode(json_value[n], t, program, f"{path}.{n}") for n, t in record["fields"]))


class JsonObject(dict):
    """A JSON object that remembers whether a key appeared twice."""
    duplicate = False


def json_object(pairs):
    out = JsonObject(pairs)
    out.duplicate = len(out) != len(pairs)
    return out


def encode(value, ty, program: Checked):
    """P0-RUN-2."""
    if ty in (INT, BOOL):
        return value
    if ty[0] == "List":
        return [encode(v, ty[1], program) for v in iterate(value)]
    record = program.records[ty[1]]
    return {n: encode(v, t, program) for (n, t), v in zip(record["fields"], value[2])}


def integers(value, ty, program):
    if ty == INT:
        yield value
    elif ty[0] == "List":
        for v in iterate(value):
            yield from integers(v, ty[1], program)
    elif ty[0] == "Record":
        for (_, t), v in zip(program.records[ty[1]]["fields"], value[2]):
            yield from integers(v, t, program)


def run(program: Checked, entry: str, args_json, budgets: dict | None = None) -> dict:
    """Run entry on JSON arguments; the result has the shape of ``weave run --json``."""
    budgets = dict(DEFAULT_BUDGETS, **(budgets or {}))
    report = {"outcome": None, "value": None, "fault": None, "exhausted": None, "diagnostics": []}
    names = [f["name"] for f in program.functions]
    if entry not in names:
        raise Diagnostic("E540", f"No function named {entry}.", NOWHERE, "run")
    index = names.index(entry)
    function = program.functions[index]
    span = function["name_span"]
    if not isinstance(args_json, list) or len(args_json) != len(function["params"]):
        raise Diagnostic("E540", f"{entry} takes {len(function['params'])} argument(s).", span, "run")
    args = []
    for value, (pname, ptype) in zip(args_json, function["params"]):
        try:
            args.append(decode(value, ptype, program, pname))
        except Diagnostic as d:
            raise Diagnostic(d.code, d.message, span, "run")
    machine = Machine(program, budgets)
    try:
        for value, (_, ptype) in zip(args, function["params"]):
            for n in integers(value, ptype, program):
                machine.admit(n, span)
        result = machine.run(index, args, span)
        report.update(outcome="value", value=encode(result, function["ret"], program))
    except Fault as f:
        report.update(outcome="fault", fault=f.kind)
        report["diagnostics"].append(Diagnostic(f.code, f.kind, f.span, "runtime"))
    except Exhausted as x:
        report.update(outcome="exhausted", exhausted=x.kind)
        report["diagnostics"].append(Diagnostic(x.code, x.kind, x.span, "runtime"))
    report["budgets"] = {"fuel": {"limit": budgets["fuel"], "used": machine.fuel},
                         "depth": {"limit": budgets["depth"], "max": machine.depth},
                         "int_bits": {"limit": budgets["int_bits"], "max": machine.bits}}
    return report


# ---------------------------------------------------------------- command line

def budget(text: str) -> int:
    """A budget is a nonnegative integer (P0-BUDGET-1); anything else is a usage error."""
    if not (text.isascii() and text.isdigit()):
        raise argparse.ArgumentTypeError(f"{text!r} is not a nonnegative integer")
    return int(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P0 reference evaluator")
    ap.add_argument("command", choices=["check", "run"])
    ap.add_argument("file")
    ap.add_argument("--entry")
    ap.add_argument("--args", default="[]")
    ap.add_argument("--fuel", type=budget, default=DEFAULT_BUDGETS["fuel"])
    ap.add_argument("--max-depth", type=budget, default=DEFAULT_BUDGETS["depth"])
    ap.add_argument("--int-bits", type=budget, default=DEFAULT_BUDGETS["int_bits"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.command == "run" and not a.entry:
        ap.error("run needs --entry")
    source = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
    name = "<stdin>" if a.file == "-" else a.file
    out = {"command": a.command, "file": name, "claims": [], "diagnostics": []}
    code = 0
    try:
        program = check(source)
        out["claims"] = [{"label": "CHECKED pure", "subject": name,
                          "functions": [f["name"] for f in program.functions]}]
        if a.command == "run":
            args = json.loads(a.args, object_pairs_hook=json_object)
            report = run(program, a.entry, args, {"fuel": a.fuel, "depth": a.max_depth, "int_bits": a.int_bits})
            diagnostics = report.pop("diagnostics")
            out.update(report)
            out["diagnostics"] = [d.document(name) for d in diagnostics]
            code = {"value": 0, "fault": 3, "exhausted": 4}[report["outcome"]]
    except Diagnostic as d:
        if a.command == "run":
            out["outcome"] = None
        out["diagnostics"] = [d.document(name)]
        code = 1
    except (ValueError, RecursionError) as e:
        print(f"p0_reference: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(out, indent=2))
    else:
        for claim in out["claims"]:
            print(f"CHECKED pure {name}: {', '.join(claim['functions'])}")
        if out.get("outcome"):
            print(f"outcome: {out['outcome']}")
            if out["outcome"] == "value":
                print("result: " + json.dumps(out["value"], separators=(",", ":")))
            b = out["budgets"]
            print(f"budgets: fuel {b['fuel']['used']}/{b['fuel']['limit']}, depth {b['depth']['max']}/"
                  f"{b['depth']['limit']}, int-bits {b['int_bits']['max']}/{b['int_bits']['limit']}")
        for d in out["diagnostics"]:
            print(f"{name}:{d['span']['start']['line']}:{d['span']['start']['column']}: "
                  f"{d['code']} ({d['rule']}) [{d['stage']}] {d['message']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
