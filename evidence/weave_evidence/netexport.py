# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Export a canonical net (weave-canonical-net-v1) from the prototype's parser output.

The exporter imports the version-3 prototype's parsers from
``inventory-proof/`` (``checker.parse_net`` for N0 sources,
``coloured.parse_coloured`` for N1 sources) and reads their result. It does
not modify the prototype and writes no bytecode into its directory. The
parsers define what is accepted; the exporter only reorders their output.
"""
from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

from .documents import CANONICAL_NET

# Positional colour sorts of the N1 prototype: coloured.py docstring
# ("Two positional colour sorts (tenant, order)") and status.rst, profile N1.
N1_COLOUR_SORTS = ["tenant", "order"]
ARC_ORDER = ("take", "read", "put")


def _prototype(root: Path):
    directory = str((Path(root) / "inventory-proof").resolve())
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loaded = sys.modules.get("checker")
        if loaded is not None and str(Path(loaded.__file__).resolve().parent) != directory:
            raise RuntimeError(f"a different 'checker' module is already imported from {loaded.__file__}")
        if directory not in sys.path:
            sys.path.insert(0, directory)
        return importlib.import_module("checker"), importlib.import_module("coloured")
    finally:
        sys.dont_write_bytecode = previous


class ExportError(ValueError):
    """The prototype parser rejected the source, or the profile is not supported."""


def _initial(text: str, parameter: str) -> tuple[int, dict]:
    return (0, {parameter: 1}) if text == parameter else (int(text), {})


def export(source_path: Path, profile: str, root: Path, revision: str) -> dict:
    """Parse ``source_path`` with the prototype parser for ``profile`` (N0 or N1) and export it.

    Guards are sorted: the prototype treats a transition's guards as a set
    (``checker.explore_order`` and ``coloured.explore_colours`` test them with ``any``).
    """
    checker, coloured = _prototype(root)
    source = Path(source_path).read_text(encoding="utf-8")
    try:
        return _export(checker, coloured, source, profile, revision)
    except checker.CheckError as error:
        raise ExportError(f"{source_path}: the {profile} parser rejected the source: {error.code} {error.message}") from error


def _export(checker, coloured, source: str, profile: str, revision: str) -> dict:
    if profile == "N0":
        base = checker.parse_net(source)
        place_indices = {p: () for p in base.places}
        binders = {t: () for t in base.transitions}
        inscriptions = {t: {k: {} for k in ARC_ORDER} for t in base.transitions}
        sorts: list[str] = []
    elif profile == "N1":
        net = coloured.parse_coloured(source)
        base = net.base
        place_indices, binders, inscriptions = net.places, net.bindings, net.arcs
        sorts = list(N1_COLOUR_SORTS)
    else:
        raise ExportError(f"unsupported profile {profile!r}; the exporter reads N0 and N1 sources")
    places = []
    marking = []
    for name in sorted(base.places):
        place = base.places[name]
        places.append({"name": name, "owner": place.owner, "indices": list(place_indices[name])})
        constant, parameters = _initial(place.initial, base.parameter)
        marking.append({"place": name, "constant": constant, "parameters": parameters})
    transitions = []
    for name in sorted(base.transitions):
        t = base.transitions[name]
        arcs = []
        for kind in ARC_ORDER:
            for place in sorted(getattr(t, kind)):
                arcs.append({"kind": kind, "place": place, "weight": getattr(t, kind)[place],
                             "inscription": list(inscriptions[name][kind].get(place, ()))})
        transitions.append({"name": name, "binder": list(binders[name]), "guards": sorted(set(t.guards)), "arcs": arcs})
    return {
        "format": CANONICAL_NET,
        "net": base.name,
        "profile": {"name": profile, "revision": revision},
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "parameters": [{"name": base.parameter, "sort": "Nat"}],
        "colour_sorts": sorts,
        "places": places,
        "initial_marking": marking,
        "transitions": transitions,
    }
