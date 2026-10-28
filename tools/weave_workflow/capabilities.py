"""Discover installed tool versions and permissions. Read-only; never prints credentials."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def _run(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _which(name: str, extra: list[Path]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for d in extra:
        if (d / name).exists():
            return str(d / name)
    return None


def inspect(repo: Path) -> dict:
    home = Path.home()
    out: dict = {"python": sys.version.split()[0]}
    claude = _which("claude", [home / ".local/bin"])
    out["claude_code"] = _run([claude, "--version"])[1] if claude else None
    rc, text = _run(["gh", "--version"])
    out["gh"] = text.splitlines()[0] if rc == 0 else None
    rc, text = _run(["gh", "auth", "status"])
    scopes = re.search(r"Token scopes:\s*(.+)", text)
    out["gh_authenticated"] = rc == 0
    out["gh_scopes"] = [s.strip(" '") for s in scopes.group(1).split(",")] if scopes else []
    out["gh_project_scope"] = any(s in ("project", "read:project") for s in out["gh_scopes"])
    out["gh_project_write_scope"] = "project" in out["gh_scopes"]
    out["gh_workflow_scope"] = "workflow" in out["gh_scopes"]
    codex = _which("codex", [])
    out["codex"] = _run([codex, "--version"])[1] if codex else None
    if codex:
        rc, text = _run([codex, "login", "status"])
        out["codex_login"] = text.splitlines()[-1] if text else None
        _, help_text = _run([codex, "exec", "--help"])
        out["codex_exec_output_schema"] = "--output-schema" in help_text
        out["codex_exec_ephemeral"] = "--ephemeral" in help_text
    plugins = home / ".claude/plugins/installed_plugins.json"
    installed = []
    if plugins.exists():
        try:
            installed = sorted(json.loads(plugins.read_text())["plugins"])
        except (ValueError, KeyError):
            pass
    out["claude_plugins"] = installed
    out["autonomous_development_installed"] = any(p.startswith("autonomous-development@") for p in installed)
    cargo = _which("cargo", [home / ".cargo/bin"])
    rustc = _which("rustc", [home / ".cargo/bin"])
    out["cargo"] = _run([cargo, "--version"])[1] if cargo else None
    out["rustc"] = _run([rustc, "--version"])[1] if rustc else None
    out["rust_on_path"] = shutil.which("cargo") is not None
    out["state_dir_override"] = bool(os.environ.get("WEAVE_WORKFLOW_STATE"))
    return out
