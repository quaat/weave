"""Parser for the kit's pure-function extension: `fn` declarations over immutable values."""
from __future__ import annotations

import re
from dataclasses import dataclass


class PureError(Exception):
    """Source-located diagnostic for the pure extension."""

    def __init__(self, code: str, message: str, line: int = 0, stage: str = "pure"):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.line, self.stage = code, message, line, stage


TYPES = ("Int", "Bool", "IntList", "IntListPair")
RESERVED = {"fn", "flow", "let", "return", "if", "else", "elif", "fork", "await", "match",
            "true", "false", "while", "for", "loop", "parallel", "retry", "within"}


@dataclass(frozen=True)
class IntLit:
    value: int
    line: int


@dataclass(frozen=True)
class BoolLit:
    value: bool
    line: int


@dataclass(frozen=True)
class Var:
    name: str
    line: int


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple
    line: int


@dataclass(frozen=True)
class Le:
    left: object
    right: object
    line: int


@dataclass(frozen=True)
class Let:
    name: str
    expr: object
    line: int


@dataclass(frozen=True)
class Return:
    expr: object
    line: int


@dataclass(frozen=True)
class If:
    cond: object
    then: tuple
    other: tuple
    line: int


@dataclass(frozen=True)
class Fork:
    branches: tuple  # exactly two Let(name, Call) after checking
    line: int


@dataclass(frozen=True)
class FnDecl:
    name: str
    params: tuple  # ((name, type), ...)
    ret: str
    body: tuple
    line: int


@dataclass(frozen=True)
class Program:
    functions: tuple
    flows: tuple  # ((name, line), ...) - effectful declarations, never executed here


@dataclass
class _Node:
    level: int
    text: str
    line: int
    children: list


IDENT = r"[A-Za-z_]\w*"
FN_RE = re.compile(rf"fn\s+({IDENT})\s*\((.*)\)\s*->\s*(.+):$")
FLOW_RE = re.compile(rf"flow\s+({IDENT})\b")
LET_RE = re.compile(rf"let\s+({IDENT})\s*=\s*(.+)$")
TOKEN_RE = re.compile(r"\s*(?:(?P<int>-?\d+)|(?P<name>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)"
                      r"|(?P<op><=|\(|\)|,)|(?P<bad>\S))")


def _lines(source: str) -> list[_Node]:
    root = _Node(-1, "", 0, [])
    stack = [root]
    for number, raw in enumerate(source.splitlines(), 1):
        lead = raw[:len(raw) - len(raw.lstrip())]
        if "\t" in lead:
            raise PureError("E400", "Tabs are not allowed in indentation; use four spaces.", number)
        text = raw.split("#", 1)[0].rstrip()
        if not text.strip():
            continue
        indent = len(text) - len(text.lstrip(" "))
        if indent % 4:
            raise PureError("E400", "Indentation must be a multiple of four spaces.", number)
        level = indent // 4
        while stack[-1].level >= level:
            stack.pop()
        parent = stack[-1]
        if level != parent.level + 1 or (parent is not root and not parent.text.endswith(":")):
            raise PureError("E400", "Unexpected indentation.", number)
        node = _Node(level, text.strip(), number, [])
        parent.children.append(node)
        stack.append(node)
    return root.children


def _split_top(text: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip() or parts:
        parts.append(current)
    return [p.strip() for p in parts]


def _check_name(name: str, line: int, what: str) -> None:
    if name in RESERVED:
        raise PureError("E400", f"`{name}` is reserved and cannot be used as a {what} name.", line)


def parse_type(text: str, line: int) -> str:
    text = text.strip()
    if text in TYPES:
        return text
    kind = "a linear resource or nominal flow type" if "[" in text else "an unsupported type"
    raise PureError("E401", f"`{text}` is {kind}. Pure functions accept and return only "
                            f"{', '.join(TYPES)}; they cannot receive, construct, or return "
                            "linear resource handles.", line)


class _ExprParser:
    def __init__(self, text: str, line: int):
        self.line = line
        self.tokens = []
        for m in TOKEN_RE.finditer(text):
            kind = m.lastgroup
            if kind == "bad":
                raise PureError("E400", f"Unsupported operator or character `{m.group(kind)}` in a pure "
                                        "expression; only integer literals, true/false, names, calls, "
                                        "parentheses, and `<=` are implemented.", line)
            self.tokens.append((kind, m.group(kind)))
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        if token[0] is None:
            raise PureError("E400", "Incomplete expression.", self.line)
        self.pos += 1
        return token

    def parse(self):
        expr = self.compare()
        if self.pos != len(self.tokens):
            raise PureError("E400", f"Unexpected token `{self.peek()[1]}` in expression.", self.line)
        return expr

    def compare(self):
        left = self.primary()
        if self.peek() == ("op", "<="):
            self.take()
            right = self.primary()
            if self.peek() == ("op", "<="):
                raise PureError("E400", "Chained comparisons are unsupported.", self.line)
            return Le(left, right, self.line)
        return left

    def primary(self):
        kind, value = self.take()
        if kind == "int":
            return IntLit(int(value), self.line)
        if kind == "name":
            if value in ("true", "false"):
                return BoolLit(value == "true", self.line)
            if self.peek() == ("op", "("):
                self.take()
                args = []
                if self.peek() != ("op", ")"):
                    while True:
                        args.append(self.compare())
                        if self.peek() == ("op", ","):
                            self.take()
                            continue
                        break
                if self.take() != ("op", ")"):
                    raise PureError("E400", "Expected `)` after call arguments.", self.line)
                return Call(value, tuple(args), self.line)
            return Var(value, self.line)
        if (kind, value) == ("op", "("):
            expr = self.compare()
            if self.take() != ("op", ")"):
                raise PureError("E400", "Expected `)`.", self.line)
            return expr
        raise PureError("E400", f"Unexpected token `{value}` in expression.", self.line)


def parse_expr(text: str, line: int):
    if re.search(r"\bawait\b", text):
        raise PureError("E409", "Pure functions cannot await operations.", line)
    return _ExprParser(text, line).parse()


def _parse_block(nodes: list[_Node]) -> tuple:
    stmts, i = [], 0
    while i < len(nodes):
        node, text = nodes[i], nodes[i].text
        word = text.split()[0].rstrip(":")
        if re.search(r"\bawait\b", text):
            raise PureError("E409", "Pure functions cannot await net or foreign operations.", node.line)
        if word == "else":
            raise PureError("E408", "`else` without a matching `if`.", node.line)
        if word == "elif":
            raise PureError("E408", "`elif` is unsupported; nest an `if` inside `else`.", node.line)
        if word == "if":
            if not text.endswith(":"):
                raise PureError("E408", "`if` must end with `:`.", node.line)
            cond = parse_expr(text[2:-1], node.line)
            then = _parse_body(node)
            if i + 1 >= len(nodes) or nodes[i + 1].text != "else:":
                raise PureError("E408", "`if` requires a terminal `else:` branch at the same level.", node.line)
            other = _parse_body(nodes[i + 1])
            stmts.append(If(cond, then, other, node.line))
            i += 2
            continue
        if text == "fork:":
            branches = []
            for child in _children(node):
                m = LET_RE.match(child.text)
                if not m or child.children:
                    raise PureError("E412", "A fork branch must be a single `let name = function(args)`.",
                                    child.line)
                _check_name(m.group(1), child.line, "binding")
                branches.append(Let(m.group(1), parse_expr(m.group(2), child.line), child.line))
            stmts.append(Fork(tuple(branches), node.line))
            i += 1
            continue
        if node.children:
            raise PureError("E400", f"Unsupported block in pure function: {text}", node.line)
        m = LET_RE.match(text)
        if m:
            _check_name(m.group(1), node.line, "binding")
            stmts.append(Let(m.group(1), parse_expr(m.group(2), node.line), node.line))
        elif word == "return":
            rest = text[len("return"):].strip()
            if not rest:
                raise PureError("E407", "A pure function must return a value.", node.line)
            stmts.append(Return(parse_expr(rest, node.line), node.line))
        else:
            raise PureError("E400", f"Unsupported statement in pure function: {text}", node.line)
        i += 1
    return tuple(stmts)


def _children(node: _Node) -> list[_Node]:
    if not node.children:
        raise PureError("E400", "A block opener must be followed by an indented body.", node.line)
    return node.children


def _parse_body(node: _Node) -> tuple:
    return _parse_block(_children(node))


def parse_program(source: str) -> Program:
    functions, flows = [], []
    for node in _lines(source):
        text = node.text
        flow = FLOW_RE.match(text)
        if flow:
            flows.append((flow.group(1), node.line))
            continue
        if not text.startswith("fn "):
            raise PureError("E400", f"Unsupported top-level declaration in a pure program: {text}", node.line)
        m = FN_RE.match(text)
        if not m:
            raise PureError("E400", "Expected `fn name(param: Type, ...) -> Type:`; pure functions "
                                    "require explicit parameter and return types.", node.line)
        name = m.group(1)
        _check_name(name, node.line, "function")
        params, seen = [], set()
        for part in _split_top(m.group(2)):
            pm = re.fullmatch(rf"({IDENT})\s*:\s*(.+)", part)
            if not pm:
                raise PureError("E400", f"Malformed parameter `{part}`.", node.line)
            _check_name(pm.group(1), node.line, "parameter")
            if pm.group(1) in seen:
                raise PureError("E402", f"Duplicate parameter `{pm.group(1)}`.", node.line)
            seen.add(pm.group(1))
            params.append((pm.group(1), parse_type(pm.group(2), node.line)))
        ret = parse_type(m.group(3), node.line)
        functions.append(FnDecl(name, tuple(params), ret, _parse_body(node), node.line))
    return Program(tuple(functions), tuple(flows))
