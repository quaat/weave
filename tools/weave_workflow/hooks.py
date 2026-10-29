"""Claude Code hook adapter. Lightweight: no network, no builds, no Codex.

Hooks are guards and evidence collectors, not a security boundary or a
scheduler; the transition gates in ``transitions.py`` hold even when hooks are
absent. Outside an active run the hooks stay out of the way of ordinary work,
apart from a few irreversible commands that always need confirmation.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from .state import Store, run_issues, utcnow

POLICY_PATH = Path(__file__).resolve().parent / "policy.json"
WORKER_ENV_PREFIX = ("unset GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN SSH_AUTH_SOCK; "
                     "export GH_CONFIG_DIR=/nonexistent/weave-worker GIT_TERMINAL_PROMPT=0 "
                     "GIT_SSH_COMMAND=false; ")

ALWAYS_DENY = [
    (re.compile(r"\bgit\s+push\b[^|;&]*\s(--force\b|-f\b|--force-with-lease\b)"), "force-push is never allowed"),
]
ALWAYS_ASK = [
    (re.compile(r"\bgh\s+pr\s+merge\b"), "merging needs explicit maintainer authority"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "would discard uncommitted work"),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"), "would delete untracked files"),
    (re.compile(r"\bgh\s+release\s+(create|upload|delete)\b|\bgit\s+push\b[^|;&]*\s--tags\b|\bgit\s+push\b[^|;&]*\brefs/tags/"),
     "release and tag publication need explicit policy"),
]
COORDINATOR_DIRECT_WRITES = re.compile(
    r"\bgh\s+(project\s+item-edit|project\s+item-add|issue\s+(close|reopen|edit|comment|delete)|label\s+(create|edit|delete))\b"
    r"|\bgh\s+api\b[^|;&]*(-X|--method)\s*(POST|PATCH|PUT|DELETE)")
WORKER_FORBIDDEN = re.compile(
    r"(^|[\s;&|(])(gh|codex|claude)\s|\bgit\s+(push|remote\s+(add|set-url))\b|\bgit\s+worktree\s+(add|remove)\b"
    r"|api\.github\.com|uploads\.github\.com|\bgit\s+(commit\s+--amend|rebase)\b")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _store(cwd: str) -> Store | None:
    try:
        return Store.for_repo(Path(cwd))
    except Exception:  # noqa: BLE001 - not a repository: hooks are inert
        return None


def _out(obj: dict) -> int:
    print(json.dumps(obj))
    return 0


def _pre_decision(decision: str, reason: str, updated: dict | None = None) -> int:
    hso = {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}
    if updated is not None:
        hso["updatedInput"] = updated
    return _out({"hookSpecificOutput": hso})


def _toplevel(cwd: str) -> str:
    return subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True).stdout.strip()


def _rel(path: str, cwd: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd) / p
    try:
        return str(p.resolve().relative_to(Path(_toplevel(cwd)).resolve()))
    except Exception:  # noqa: BLE001
        return str(p)


def pre_tool_use(payload: dict) -> int:
    policy = _policy()
    tool = payload.get("tool_name", "")
    tin = payload.get("tool_input") or {}
    agent_type = payload.get("agent_type") or ""
    worker = agent_type in policy["worker_agent_types"]
    cwd = payload.get("cwd") or "."
    store = _store(cwd)
    run = store.active_run() if store else None
    if tool == "Bash":
        cmd = tin.get("command", "")
        for pat, why in ALWAYS_DENY:
            if pat.search(cmd):
                return _pre_decision("deny", f"Weave policy: {why}.")
        if worker:
            if WORKER_FORBIDDEN.search(cmd):
                return _pre_decision("deny", "Weave policy: workers do not use GitHub, push, manage worktrees, rewrite history "
                                             "or launch agents. Return a structured message to the orchestrator instead.")
            return _pre_decision("allow", "worker shell with GitHub and SSH credentials removed",
                                 {**tin, "command": WORKER_ENV_PREFIX + cmd})
        for pat, why in ALWAYS_ASK:
            if pat.search(cmd):
                return _pre_decision("ask", f"Weave policy: {why}.")
        if run and COORDINATOR_DIRECT_WRITES.search(cmd):
            return _pre_decision("ask", "Weave run active: board, label and comment writes go through "
                                        "`python3 -m tools.weave_workflow` so gates and the ledger apply.")
        return 0
    if tool in EDIT_TOOLS and worker:
        path = tin.get("file_path") or tin.get("notebook_path") or ""
        rel = _rel(path, cwd)
        for prot in policy["protected_paths"]:
            if rel == prot.rstrip("/") or rel.startswith(prot if prot.endswith("/") else prot + "/") or rel == prot:
                return _pre_decision("deny", f"Weave policy: {rel} is protected (snapshots, provenance, policy, CI and "
                                             "agent configuration change only through an explicitly reviewed task).")
        allowed = ((run or {}).get("delegations") or {}).get(agent_type, {}).get("allowed_paths")
        if allowed:
            from .docs_audit import matches
            if not matches(rel, allowed):
                return _pre_decision("deny", f"Weave policy: {rel} is outside this delegation's allowed paths {allowed}.")
    return 0


def post_tool_use(payload: dict, failed: bool) -> int:
    store = _store(payload.get("cwd") or ".")
    if not store or not store.active_run():
        return 0
    tin = payload.get("tool_input") or {}
    rec = {"type": "evidence", "hook": "PostToolUseFailure" if failed else "PostToolUse",
           "tool": payload.get("tool_name"), "ok": not failed, "agent_type": payload.get("agent_type"),
           "agent_id": payload.get("agent_id"), "payload_keys": sorted(payload)}
    if "command" in tin:
        rec["command"] = tin["command"][:300]
    path = tin.get("file_path") or tin.get("notebook_path")
    if path:
        rel = _rel(path, payload.get("cwd") or ".")
        rec["path"] = rel
        from .docs_audit import docmap_for, load_docmap, matches
        try:
            top = _toplevel(payload.get("cwd") or ".")
        except OSError:
            top = ""
        docmap = docmap_for(Path(top)) if top else load_docmap()  # the edited tree's own map
        if not failed and matches(rel, docmap["managed_documents"]):
            pending = store.root / "docs-audit-pending.json"
            items = json.loads(pending.read_text()) if pending.exists() else []
            if rel not in items:
                items.append(rel)
            pending.write_text(json.dumps(items))
            rec["docs_audit_queued"] = True
    store.append(rec)
    return 0


def subagent(payload: dict, phase: str) -> int:
    store = _store(payload.get("cwd") or ".")
    if not store or not store.active_run():
        return 0
    store.append({"type": "subagent", "phase": phase, "agent_id": payload.get("agent_id"),
                  "agent_type": payload.get("agent_type"), "run_id": store.active_run().get("run_id"),
                  "payload_keys": sorted(payload)})
    return 0


def _auto_checkpoint(store: Store, reason: str) -> dict:
    prev = store.read_checkpoint() or {}
    run = store.active_run() or {}
    return store.checkpoint({**{k: v for k, v in prev.items() if k not in ("checkpointed_at", "active_issue")},
                             "run_id": run.get("run_id"), "active_issues": run_issues(run),
                             "pending_messages": [i["event_id"] for i in store.pending()],
                             "reason": reason,
                             "next_action": prev.get("next_action", "reconcile, then resume the active issues")})


def stop(payload: dict) -> int:
    store = _store(payload.get("cwd") or ".")
    if not store or not store.active_run():
        return 0
    if payload.get("stop_hook_active"):
        _auto_checkpoint(store, "stop (after guard)")
        return 0
    guard = store.root / "stop-guard.json"
    counts = json.loads(guard.read_text()) if guard.exists() else {}
    sid = payload.get("session_id", "unknown")
    pending = store.pending()
    if pending and counts.get(sid, 0) < 2:
        counts[sid] = counts.get(sid, 0) + 1
        guard.write_text(json.dumps(counts))
        return _out({"decision": "block",
                     "reason": f"{len(pending)} protocol message(s) are not yet delivered to GitHub. Flush them with "
                               "`python3 -m tools.weave_workflow reconcile --apply`, or record a BLOCKED outcome; "
                               "stopping is not Done."})
    _auto_checkpoint(store, "stop")
    return 0


def session_start(payload: dict) -> int:
    store = _store(payload.get("cwd") or ".")
    if not store:
        return 0
    run, cp, pending = store.active_run(), store.read_checkpoint(), store.pending()
    if not run and not pending:
        return 0
    lines = ["Weave development workflow state (from the local ledger):"]
    if run:
        issues = ", ".join(f"#{n}" for n in run_issues(run)) or "-"
        lines.append(f"- Active run {run.get('run_id')} on issues {issues}, scope: {run.get('scope', '-')}")
    if cp:
        lines.append(f"- Last checkpoint {cp.get('checkpointed_at')}: {cp.get('next_action', '-')}")
    if pending:
        lines.append(f"- {len(pending)} undelivered protocol message(s) in the outbox")
    lines.append("Use the weave-project skill: reconcile before any new claim; resume existing work first.")
    return _out({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}})


def pre_compact(payload: dict) -> int:
    store = _store(payload.get("cwd") or ".")
    if store and store.active_run():
        _auto_checkpoint(store, f"pre-compact ({payload.get('trigger', '-')})")
    return 0


def session_end(payload: dict) -> int:
    store = _store(payload.get("cwd") or ".")
    if store and store.active_run():
        _auto_checkpoint(store, f"session end ({payload.get('reason', '-')})")
        store.append({"type": "run", "phase": "session-ended", "run_id": store.active_run().get("run_id"),
                      "note": "claim release intent recorded; the claim is released only by an explicit RELEASED event",
                      "at": utcnow()})
    return 0


HANDLERS = {
    "PreToolUse": pre_tool_use,
    "PostToolUse": lambda p: post_tool_use(p, False),
    "PostToolUseFailure": lambda p: post_tool_use(p, True),
    "SubagentStart": lambda p: subagent(p, "start"),
    "SubagentStop": lambda p: subagent(p, "stop"),
    "Stop": stop,
    "SessionStart": session_start,
    "PreCompact": pre_compact,
    "SessionEnd": session_end,
}


def main(event: str, stdin=None) -> int:
    raw = (stdin or sys.stdin).read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    handler = HANDLERS.get(event)
    if handler is None:
        return 0
    try:
        return handler(payload)
    except Exception as exc:  # noqa: BLE001
        if event == "PreToolUse" and payload.get("agent_type") in _policy()["worker_agent_types"]:
            print(f"Weave guard failed closed for a worker: {exc}", file=sys.stderr)
            return 2
        print(f"weave hook {event} error (non-blocking): {exc}", file=sys.stderr)
        return 0
