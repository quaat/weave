# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Shared helpers for the evidence tests."""
from __future__ import annotations

import copy
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The evidence files named in the context of quaat/weave#7, plus colour-check.json,
# which the stability policy lists with them.
ISSUE_FILES = [
    "inventory-proof/proof.json",
    "inventory-proof/ordering.json",
    "inventory-proof/colour-proof.json",
    "inventory-proof/scenarios.json",
    "inventory-proof/durable-scenarios.json",
    "specification/validation/report.json",
]
ALL_FILES = ISSUE_FILES + ["inventory-proof/colour-check.json"]

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def repo_copy() -> Path:
    """A temporary copy of the files the wrappers and exporter read. Tests edit only the copy."""
    target = Path(tempfile.mkdtemp(prefix="weave-evidence-"))
    shutil.copytree(ROOT / "inventory-proof", target / "inventory-proof", ignore=_IGNORE)
    spec = target / "specification"
    for sub in ("validation", "examples", "reference/prototype"):
        shutil.copytree(ROOT / "specification" / sub, spec / sub, ignore=_IGNORE)
    (spec / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "specification/scripts/validate.py", spec / "scripts/validate.py")
    shutil.copy2(ROOT / "specification/PROVENANCE.json", spec / "PROVENANCE.json")
    return target


def minimal_trace() -> dict:
    return {
        "format": "weave-trace-v1",
        "kind": "replay",
        "subject": "checkout",
        "model": {"net": "Inventory", "source_sha256": "0" * 64},
        "steps": [
            {"sequence": 1, "kind": "fire", "transition": "reserve",
             "marking": [{"place": "held", "colour": [], "count": 1}]},
            {"sequence": 2, "kind": "return", "flow": "checkout", "tag": "Ok"},
        ],
        "final_marking": [{"place": "held", "colour": [], "count": 1}],
        "outcome": "Ok",
        "context": {},
    }


def minimal_envelope(**changes) -> dict:
    envelope = {
        "format": "weave-evidence-envelope-v1",
        "claim": {"name": "checkout[Ok]", "pointer": "/0", "statement": None, "detail": {}},
        "claim_label": "SCRIPTED / passed scenario",
        "runtime_status": "waiting",
        "profiles": [{"name": "F0", "revision": "0.2-draft"}],
        "bounds": None,
        "assumptions": [],
        "scope": None,
        "completeness": None,
        "wrapped": {"path": "inventory-proof/scenarios.json", "sha256": "a" * 64, "format": None},
        "sources": [{"path": "inventory-proof/Inventory.weave", "sha256": "b" * 64}],
        "dependencies": [{"path": "inventory-proof/simulate.py", "sha256": "c" * 64}],
        "tools": [{"name": "evidence/weave_evidence", "version": "0.1.0", "supported_profiles": []}],
        "trace": {"format": "weave-trace-v1", "sha256": "d" * 64},
    }
    envelope.update(copy.deepcopy(changes))
    return envelope


def minimal_net() -> dict:
    return {
        "format": "weave-canonical-net-v1",
        "net": "Tiny",
        "profile": {"name": "N1", "revision": "0.2-draft"},
        "source_sha256": "e" * 64,
        "parameters": [{"name": "stock", "sort": "Nat"}],
        "colour_sorts": ["tenant", "order"],
        "places": [
            {"name": "available", "owner": "domain", "indices": []},
            {"name": "held", "owner": "activation", "indices": ["t", "o"]},
        ],
        "initial_marking": [
            {"place": "available", "constant": 0, "parameters": {"stock": 1}},
            {"place": "held", "constant": 0, "parameters": {}},
        ],
        "transitions": [
            {"name": "reserve", "binder": ["t", "o"], "guards": [],
             "arcs": [{"kind": "take", "place": "available", "weight": 1, "inscription": []},
                      {"kind": "put", "place": "held", "weight": 1, "inscription": ["t", "o"]}]},
        ],
    }
