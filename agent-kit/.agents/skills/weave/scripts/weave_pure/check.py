"""Static checker for pure `fn` programs: types, terminal branches, effects, fork scope, recursion."""
from __future__ import annotations

from .syntax import (BoolLit, Call, Fork, If, IntLit, Le, Let, PureError, Program, Return, Var,
                     parse_program)
from .values import PRIMITIVES


class _Checker:
    def __init__(self, program: Program):
        self.flows = {name for name, _ in program.flows}
        self.sigs = {}
        self.calls = {}  # function -> set of called user functions
        for fn in program.functions:
            if fn.name in PRIMITIVES:
                raise PureError("P402", f"`{fn.name}` collides with a list primitive.", fn.line)
            if fn.name in self.sigs or fn.name in self.flows:
                raise PureError("P402", f"Duplicate declaration `{fn.name}`.", fn.line)
            self.sigs[fn.name] = fn

    def expr(self, e, env: dict, current: str, hidden: dict | None = None) -> str:
        if isinstance(e, IntLit):
            return "Int"
        if isinstance(e, BoolLit):
            return "Bool"
        if isinstance(e, Var):
            if hidden and e.name in hidden:
                raise PureError("P412", f"Fork branch uses sibling result `{e.name}` before the join; "
                                        "fork results are visible only after both branches complete.", e.line)
            if e.name in env:
                return env[e.name]
            if "." in e.name:
                raise PureError("P409", f"Pure functions cannot reference net or foreign operation `{e.name}`.",
                                e.line)
            if e.name in self.sigs or e.name in PRIMITIVES or e.name in self.flows:
                raise PureError("P403", f"`{e.name}` is a function, not a value; higher-order functions are "
                                        "unsupported.", e.line)
            raise PureError("P403", f"Unknown binding `{e.name}`.", e.line)
        if isinstance(e, Le):
            for side in (e.left, e.right):
                if self.expr(side, env, current, hidden) != "Int":
                    raise PureError("P406", "`<=` compares two Int values.", e.line)
            return "Bool"
        if isinstance(e, Call):
            if "." in e.name:
                raise PureError("P409", f"Pure functions cannot invoke net or foreign operation `{e.name}`.",
                                e.line)
            if e.name in self.flows:
                raise PureError("P409", f"Pure function cannot call effectful flow `{e.name}`.", e.line)
            if e.name in PRIMITIVES:
                params, ret, _ = PRIMITIVES[e.name]
            elif e.name in self.sigs:
                fn = self.sigs[e.name]
                params, ret = tuple(t for _, t in fn.params), fn.ret
                self.calls[current].add(e.name)
            else:
                raise PureError("P404", f"Unknown function or primitive `{e.name}`.", e.line)
            if len(e.args) != len(params):
                raise PureError("P405", f"`{e.name}` expects {len(params)} argument(s), got {len(e.args)}.",
                                e.line)
            for i, (arg, expected) in enumerate(zip(e.args, params), 1):
                actual = self.expr(arg, env, current, hidden)
                if actual != expected:
                    raise PureError("P406", f"Argument {i} of `{e.name}` must be {expected}, got {actual}.",
                                    e.line)
            return ret
        raise PureError("P400", "Unsupported expression.", getattr(e, "line", 0))

    def bind(self, name: str, env: dict, line: int) -> None:
        if name in env:
            raise PureError("P413", f"`{name}` is already bound; rebinding and shadowing are unsupported.", line)
        if name in self.sigs or name in PRIMITIVES:
            raise PureError("P413", f"Binding `{name}` collides with a function name.", line)

    def block(self, stmts: tuple, env: dict, fn) -> None:
        env = dict(env)
        for index, stmt in enumerate(stmts):
            last = index == len(stmts) - 1
            if isinstance(stmt, Let):
                self.bind(stmt.name, env, stmt.line)
                env[stmt.name] = self.expr(stmt.expr, env, fn.name)
            elif isinstance(stmt, Fork):
                self.fork(stmt, env, fn)
            elif isinstance(stmt, Return):
                actual = self.expr(stmt.expr, env, fn.name)
                if actual != fn.ret:
                    raise PureError("P407", f"`{fn.name}` returns {fn.ret}, but this returns {actual}.", stmt.line)
                if not last:
                    raise PureError("P408", "Statements after `return` are unreachable.", stmts[index + 1].line)
            elif isinstance(stmt, If):
                if self.expr(stmt.cond, env, fn.name) != "Bool":
                    raise PureError("P414", "An `if` condition must be Bool.", stmt.line)
                self.block(stmt.then, env, fn)
                self.block(stmt.other, env, fn)
                if not last:
                    raise PureError("P408", "`if`/`else` is terminal; no statements may follow it.",
                                    stmts[index + 1].line)
            if last and not isinstance(stmt, (Return, If)):
                raise PureError("P408", f"Every path of `{fn.name}` must end in `return` or a terminal "
                                        "`if`/`else`.", stmt.line)

    def fork(self, stmt: Fork, env: dict, fn) -> None:
        if len(stmt.branches) != 2:
            raise PureError("P412", f"`fork` requires exactly two branches, got {len(stmt.branches)}.", stmt.line)
        names = [b.name for b in stmt.branches]
        if names[0] == names[1]:
            raise PureError("P412", "Fork branches must bind distinct names.", stmt.line)
        results = {}
        for branch, sibling in zip(stmt.branches, reversed(names)):
            call = branch.expr
            if not isinstance(call, Call) or call.name not in self.sigs:
                raise PureError("P412", "Each fork branch must call a user-defined pure function; primitives "
                                        "and plain expressions are not activations.", branch.line)
            self.bind(branch.name, env, branch.line)
            results[branch.name] = self.expr(call, env, fn.name, hidden={sibling: True})
        env.update(results)

    def recursion(self) -> None:
        # Tarjan SCC: direct self-recursion is allowed; any longer cycle is mutual recursion.
        index, low, stack, on, counter = {}, {}, [], set(), [0]

        def visit(v):
            work = [(v, iter(sorted(self.calls[v])))]
            index[v] = low[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on.add(v)
            while work:
                node, it = work[-1]
                advanced = False
                for w in it:
                    if w not in index:
                        index[w] = low[w] = counter[0]
                        counter[0] += 1
                        stack.append(w)
                        on.add(w)
                        work.append((w, iter(sorted(self.calls[w]))))
                        advanced = True
                        break
                    if w in on:
                        low[node] = min(low[node], index[w])
                if advanced:
                    continue
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        component.append(w)
                        if w == node:
                            break
                    if len(component) > 1:
                        first = min(component, key=lambda n: self.sigs[n].line)
                        raise PureError("P411", "Mutual recursion is unsupported: "
                                                + ", ".join(sorted(component)) + ".", self.sigs[first].line)

        for name in self.sigs:
            if name not in index:
                visit(name)


def check_program(program: Program) -> Program:
    checker = _Checker(program)
    if not program.functions:
        raise PureError("P400", "No pure functions to check.")
    for fn in program.functions:
        checker.calls[fn.name] = set()
        checker.block(fn.body, dict(fn.params), fn)
    checker.recursion()
    if program.flows:
        name, line = program.flows[0]
        raise PureError("P410", f"Effectful flow `{name}` cannot appear in a pure program; check flows with "
                                "`check` and keep pure functions in separate files.", line)
    return program


def check_source(source: str) -> Program:
    return check_program(parse_program(source))
