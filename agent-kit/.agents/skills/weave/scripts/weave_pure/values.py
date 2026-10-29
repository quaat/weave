"""Immutable values and the closed primitive set for the pure extension."""
from __future__ import annotations

from .syntax import PureError


class IntList:
    """Persistent singly linked list node; EMPTY is the shared empty list."""

    __slots__ = ("head", "tail", "length")

    def __init__(self, head, tail, length):
        self.head, self.tail, self.length = head, tail, length

    @staticmethod
    def from_iter(items) -> "IntList":
        result = EMPTY
        for item in reversed(list(items)):
            result = IntList(item, result, result.length + 1)
        return result

    def items(self):
        node = self
        while node.length:
            yield node.head
            node = node.tail

    def to_list(self) -> list:
        return list(self.items())

    def __repr__(self):
        return f"IntList({self.to_list()})"


EMPTY = IntList(None, None, 0)


class IntListPair:
    __slots__ = ("first", "second")

    def __init__(self, first: IntList, second: IntList):
        self.first, self.second = first, second


class RuntimeFault(PureError):
    def __init__(self, code: str, message: str, line: int = 0):
        super().__init__(code, message, line, stage="runtime")


def _nonempty(xs: IntList, name: str, line: int) -> IntList:
    if not xs.length:
        raise RuntimeFault("P420", f"{name}() of an empty list.", line)
    return xs


def _split_half(xs: IntList, line: int) -> IntListPair:
    # First half: floor(n/2) copied nodes; second half shares the original suffix.
    count = xs.length // 2
    heads, node = [], xs
    for _ in range(count):
        heads.append(node.head)
        node = node.tail
    return IntListPair(IntList.from_iter(heads), node)


# name -> (parameter types, return type, implementation(args..., line))
PRIMITIVES = {
    "length": (("IntList",), "Int", lambda xs, line: xs.length),
    "is_empty": (("IntList",), "Bool", lambda xs, line: xs.length == 0),
    "head": (("IntList",), "Int", lambda xs, line: _nonempty(xs, "head", line).head),
    "tail": (("IntList",), "IntList", lambda xs, line: _nonempty(xs, "tail", line).tail),
    "cons": (("Int", "IntList"), "IntList", lambda x, xs, line: IntList(x, xs, xs.length + 1)),
    "split_half": (("IntList",), "IntListPair", _split_half),
    "first": (("IntListPair",), "IntList", lambda pair, line: pair.first),
    "second": (("IntListPair",), "IntList", lambda pair, line: pair.second),
}


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def decode(value, type_name: str, where: str):
    """Convert a JSON value into a runtime value of the declared type."""
    def bad(expected):
        return RuntimeFault("P424", f"{where}: expected {expected}, got {value!r}.")
    if type_name == "Int":
        if not _is_int(value):
            raise bad("an integer")
        return value
    if type_name == "Bool":
        if not isinstance(value, bool):
            raise bad("true or false")
        return value
    if type_name == "IntList":
        if not isinstance(value, list) or not all(_is_int(v) for v in value):
            raise bad("a JSON list of integers")
        return IntList.from_iter(value)
    if type_name == "IntListPair":
        if not isinstance(value, list) or len(value) != 2:
            raise bad("a two-element list of integer lists")
        return IntListPair(decode(value[0], "IntList", where), decode(value[1], "IntList", where))
    raise RuntimeFault("P424", f"{where}: unsupported type {type_name}.")


def encode(value):
    if isinstance(value, IntList):
        return [int(v) for v in value.items()]
    if isinstance(value, IntListPair):
        return [encode(value.first), encode(value.second)]
    if isinstance(value, bool):
        return value
    return int(value)
