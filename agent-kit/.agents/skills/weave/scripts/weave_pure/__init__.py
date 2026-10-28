"""Kit extension: checked pure functions with immutable integer lists and cooperative fork/join.

This package is a kit-level addition; the vendored prototype under assets/prototype is unchanged.
"""
from .check import check_program, check_source
from .runtime import MODES, SCHEDULES, Limits, Machine
from .syntax import PureError, parse_program
from .values import EMPTY, IntList, IntListPair, RuntimeFault, decode, encode

__all__ = ["check_program", "check_source", "parse_program", "Machine", "Limits", "MODES", "SCHEDULES",
           "PureError", "RuntimeFault", "IntList", "IntListPair", "EMPTY", "decode", "encode", "run_source"]


def run_source(source: str, entry: str, json_args: list, **options):
    """Check `source`, decode JSON arguments for `entry`, and execute it. Returns (value, machine)."""
    program = check_source(source)
    fn = next((f for f in program.functions if f.name == entry), None)
    if fn is None:
        raise RuntimeFault("E425", f"Unknown entry function `{entry}`.")
    if not isinstance(json_args, list) or len(json_args) != len(fn.params):
        raise RuntimeFault("E424", f"`{entry}` expects a JSON array of {len(fn.params)} argument(s).")
    args = [decode(value, type_name, f"argument `{name}`")
            for value, (name, type_name) in zip(json_args, fn.params)]
    machine = Machine(program, **options)
    return machine.run(entry, args), machine
