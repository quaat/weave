"""Independent review: packet construction, Codex invocation and result acceptance.

The reviewer runs as a fresh, ephemeral, read-only ``codex exec`` session with
no MCP servers and with GitHub and SSH credentials removed from its
environment. Its final message must satisfy ``review-result.v1.schema.json``;
the result is then validated again here and bound to the exact request. Process
exit status, silence, or prose never count as approval.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import schema
from .model import digest

SCHEMA_PATH = schema.SCHEMA_DIR / "review-result.v1.schema.json"
SCRUBBED_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
                "SSH_AUTH_SOCK", "SSH_AGENT_PID", "GIT_ASKPASS", "SSH_ASKPASS")

PROMPT_TEMPLATE = """You are the independent reviewer for a change to the Weave repository.
You did not write this change and you owe it no agreement. Work read-only: inspect the
repository at the working directory, the diff between the base and head commits, the
surrounding source, and the specification. Challenge assumptions, including the local
review's. You may run read-only commands (for example `git diff`, `git show`, tests that
do not write outside temporary directories). Do not edit files and do not contact GitHub.

Assess every acceptance criterion (AC-*) and every documentation criterion (DOC-*) as
satisfied, partially_satisfied, not_satisfied or not_verifiable, with evidence. Give each
finding a stable id (reuse ids from earlier rounds for the same problem), a severity, whether
it blocks acceptance, a location, a reproduction, and the required correction. Report the
checks you actually ran with their exit codes. Use verdict PASS only if every criterion is
satisfied and no blocking finding remains; REQUEST_CHANGES when fixes are needed; BLOCKED
when you cannot review (missing access, inconsistent packet).

Echo these identity fields exactly: run_id, attempt, request_id, base_sha, head_sha,
requirements_digest, and schema_version 1.

Review packet (JSON):
{packet}
"""


class ReviewRejected(Exception):
    pass


def documentation_criteria(docs_impact: list[dict]) -> list[dict]:
    crit = [{"id": "DOC-1", "text": "Every document in the documentation impact list is updated or has a recorded justification."},
            {"id": "DOC-2", "text": "Claims in changed documents (counts, codes, commands, paths, hashes, boundaries) match the artefacts."}]
    for i, item in enumerate(docs_impact, start=3):
        crit.append({"id": f"DOC-{i}", "text": f"{item['path']}: {item['reason']} ({item['status']})"})
    return crit


def build_packet(*, run_id: str, attempt: int, request_id: str, issue_url: str, milestone: str | None,
                 criteria: list[dict], requirements_digest: str, base_sha: str, head_sha: str,
                 dependency_evidence: list[str], decisions: list[str], checks: list[dict],
                 ci_links: list[str], limitations: list[str], docs_impact: list[dict],
                 docs_changed: list[str], docs_audit: dict, local_findings: list[dict],
                 review_round: int, previous_findings: list[dict], mode: str = "full") -> dict:
    return {
        "schema_version": 1, "run_id": run_id, "attempt": attempt, "request_id": request_id,
        "issue_url": issue_url, "milestone": milestone, "review_round": review_round, "mode": mode,
        "requirements_digest": requirements_digest, "base_sha": base_sha, "head_sha": head_sha,
        "acceptance_criteria": [{"id": c["id"], "text": c["text"]} for c in criteria],
        "documentation_criteria": documentation_criteria(docs_impact),
        "dependency_and_gate_evidence": dependency_evidence, "maintainer_decisions": decisions,
        "verification": checks, "ci_links": ci_links, "accepted_limitations": limitations,
        "documentation_impact": docs_impact, "documents_changed": docs_changed,
        "documentation_audit": docs_audit, "local_review_findings": local_findings,
        "previous_findings": previous_findings,
        "inspect": {"diff": f"git diff {base_sha}..{head_sha}", "log": f"git log {base_sha}..{head_sha}"},
    }


@dataclass
class ReviewRun:
    result: dict
    raw_path: Path
    provenance: dict


def codex_version(codex: str = "codex") -> str:
    out = subprocess.run([codex, "--version"], capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


def run_codex(packet: dict, worktree: Path, out_dir: Path, policy: dict, codex: str = "codex") -> ReviewRun:
    """Launch a fresh restricted Codex session for the packet. Raises ReviewRejected on any failure."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT_TEMPLATE.format(packet=json.dumps(packet, indent=2))
    result_path = out_dir / f"review-{packet['request_id']}.json"
    events_path = out_dir / f"review-{packet['request_id']}.events.jsonl"
    cfg = policy["review"]["codex"]
    args = [codex, "exec", "--sandbox", cfg["sandbox"], *cfg["extra_args"]]
    for override in cfg["config_overrides"]:
        args += ["-c", override]
    args += ["--output-schema", str(SCHEMA_PATH), "-o", str(result_path), "--json", "-C", str(worktree), "-"]
    with tempfile.TemporaryDirectory() as empty_gh:
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
        env.update({"GH_CONFIG_DIR": empty_gh, "GIT_TERMINAL_PROMPT": "0"})
        try:
            with open(events_path, "w", encoding="utf-8") as ev:
                proc = subprocess.run(args, input=prompt, stdout=ev, stderr=subprocess.PIPE, text=True,
                                      env=env, timeout=policy["review"]["timeout_seconds"])
        except subprocess.TimeoutExpired as exc:
            raise ReviewRejected("review timed out; a timeout is not a verdict") from exc
    session = "unknown"
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("type") == "thread.started":
            session = e.get("thread_id", "unknown")
    if proc.returncode != 0:
        raise ReviewRejected(f"codex exited {proc.returncode}: {proc.stderr.strip()[-400:]}")
    if not result_path.exists() or not result_path.read_text(encoding="utf-8").strip():
        raise ReviewRejected("codex produced no final message; silence is not a verdict")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewRejected("codex final message is not JSON; prose is not a verdict") from exc
    provenance = {"cli": "codex exec", "version": codex_version(codex), "session": session}
    return ReviewRun(result, result_path, provenance)


def accept(result: dict, *, request: dict, current_head: str, current_base: str,
           requirements_now: str, criteria_ids: list[str], doc_criteria_ids: list[str]) -> dict:
    """Validate a review result against the schema and the exact request. Returns a normalised verdict.

    Raises ReviewRejected for any mismatch; a rejected result is never a verdict.
    """
    errors = schema.validate(result, schema.load("review-result.v1.schema.json"))
    if errors:
        raise ReviewRejected(f"schema: {errors[:3]}")
    checks = [("run_id", request["run_id"]), ("attempt", request["attempt"]),
              ("request_id", request["event_id"]), ("head_sha", request["head_sha"]),
              ("base_sha", request["base_sha"]), ("requirements_digest", request["requirements_digest"])]
    for key, expected in checks:
        if result[key] != expected:
            raise ReviewRejected(f"identity mismatch on {key}: {result[key]!r} != {expected!r}")
    if result["head_sha"] != current_head:
        raise ReviewRejected("candidate head moved since the review request; result is stale")
    if result["base_sha"] != current_base:
        raise ReviewRejected("base drifted since the review request; result is stale")
    if result["requirements_digest"] != requirements_now:
        raise ReviewRejected("issue requirements changed since the review request")
    assessed = {c["id"]: c for c in result["criteria"]}
    missing = [i for i in criteria_ids + doc_criteria_ids if i not in assessed]
    unmet = [i for i, c in assessed.items() if c["status"] != "satisfied"]
    blocking = [f["id"] for f in result["findings"] if f["blocking"] or f["severity"] in ("critical", "high")]
    verdict = result["verdict"]
    if verdict == "PASS" and (missing or unmet or blocking):
        raise ReviewRejected(f"inconsistent PASS: missing={missing} unmet={unmet} blocking={blocking}")
    return {"verdict": verdict, "missing_criteria": missing, "unmet_criteria": unmet,
            "blocking_findings": blocking, "review_digest": digest(json.dumps(result, sort_keys=True))}
