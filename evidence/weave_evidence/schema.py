# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Strict validator for the JSON Schema subset used by the evidence schemas.

The evidence tooling has no third-party dependencies, so it validates its own
schemas with this small, fail-closed implementation (the approach of
``tools/weave_workflow/schema.py``). A keyword outside the supported subset
raises ``SchemaError`` instead of being ignored. ``const`` and ``enum`` compare
JSON values, so ``true`` never equals ``1``.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

SUPPORTED = {
    "$schema", "$id", "$defs", "$ref", "title", "description", "type", "properties",
    "required", "additionalProperties", "enum", "const", "pattern", "minLength",
    "minimum", "items", "minItems", "uniqueItems", "allOf", "if", "then",
}
TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class SchemaError(Exception):
    """The schema itself uses an unsupported construct."""


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    if schema.get("$schema") != DIALECT:
        raise SchemaError(f"{name}: $schema must be {DIALECT}")
    check_subset(schema)
    return schema


def check_subset(schema, path: str = "$") -> None:
    """Raise SchemaError if any keyword in the schema is outside the subset."""
    if not isinstance(schema, dict):
        raise SchemaError(f"{path}: a schema must be an object")
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise SchemaError(f"unsupported keywords at {path}: {sorted(unknown)}")
    for key in ("properties", "$defs"):
        for name, sub in schema.get(key, {}).items():
            check_subset(sub, f"{path}.{key}.{name}")
    for key in ("items", "if", "then"):
        if key in schema:
            check_subset(schema[key], f"{path}.{key}")
    if isinstance(schema.get("additionalProperties"), dict):
        check_subset(schema["additionalProperties"], f"{path}.additionalProperties")
    for i, sub in enumerate(schema.get("allOf", [])):
        check_subset(sub, f"{path}.allOf[{i}]")


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def validate(instance, schema: dict) -> list[str]:
    """Return a list of error strings; empty means valid."""
    errors: list[str] = []
    _check(instance, schema, schema, "$", errors)
    return errors


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local $ref is supported: {ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _check(value, schema: dict, root: dict, path: str, errors: list[str]) -> None:
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise SchemaError(f"unsupported keywords at {path}: {sorted(unknown)}")
    if "$ref" in schema:
        _check(value, _resolve(schema["$ref"], root), root, path, errors)
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(TYPES[t](value) for t in types):
            errors.append(f"{path}: expected {'/'.join(types)}, got {type(value).__name__}")
            return
    if "const" in schema and not _same(value, schema["const"]):
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and not any(_same(value, option) for option in schema["enum"]):
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if TYPES["number"](value) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems"):
            seen = [json.dumps(v, sort_keys=True) for v in value]
            if len(seen) != len(set(seen)):
                errors.append(f"{path}: items are not unique")
        if "items" in schema:
            for i, item in enumerate(value):
                _check(item, schema["items"], root, f"{path}[{i}]", errors)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field {key!r}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                _check(item, props[key], root, f"{path}.{key}", errors)
            elif extra is False:
                errors.append(f"{path}: unexpected field {key!r}")
            elif isinstance(extra, dict):
                _check(item, extra, root, f"{path}.{key}", errors)
    for sub in schema.get("allOf", []):
        _check(value, sub, root, path, errors)
    if "if" in schema:
        probe: list[str] = []
        _check(value, schema["if"], root, path, probe)
        if not probe and "then" in schema:
            _check(value, schema["then"], root, path, errors)
