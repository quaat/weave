"""Protocol events: build, validate, render as issue comments, and authenticate.

An event is only trusted when its comment was posted by an authorised
coordinator login, has not been edited, and matches a delivery record in the
local run ledger (comment id and envelope digest). Text that merely claims a
sender is never sufficient.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import schema
from .model import Comment, digest
from .state import new_id, utcnow

MARKER = "<!-- weave-agent:event:v1 -->"
DECISION_PREFIX = "/weave-decision"
ENVELOPE_RE = re.compile(re.escape(MARKER) + r"\s*```json\s*\n(.*?)\n```", re.S)

SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"(?i)(authorization:\s*(?:bearer|token)\s+)[^\s]+"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
]


class EventError(Exception):
    pass


def redact(text: str) -> tuple[str, bool]:
    changed = False
    for pat in SECRET_PATTERNS:
        text, n = pat.subn("[REDACTED]", text)
        changed = changed or n > 0
    return text, changed


def build(kind: str, *, run_id: str, attempt: int, issue: str, milestone: str | None,
          sender: str, recipient: str, correlation_id: str | None = None,
          causation_id: str | None = None, summary: str = "", **fields) -> dict:
    event_id = new_id("ev")
    event = {
        "schema_version": 1, "event_id": event_id, "run_id": run_id, "attempt": attempt,
        "issue": issue, "milestone": milestone, "sender": sender, "recipient": recipient,
        "kind": kind, "correlation_id": correlation_id or event_id,
        "causation_id": causation_id, "created_at": utcnow(), "summary": summary, **fields,
    }
    errors = validate(event)
    if errors:
        raise EventError(f"invalid {kind} event: {errors}")
    return event


def validate(event: dict) -> list[str]:
    return schema.validate(event, schema.load("event.v1.schema.json"))


def canonical(event: dict) -> str:
    return json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def event_digest(event: dict) -> str:
    return digest(canonical(event))


def render(event: dict, body: str = "") -> tuple[str, dict]:
    """Render a comment. Returns (comment text, possibly redacted event)."""
    if body.lstrip().startswith(DECISION_PREFIX) or DECISION_PREFIX in body:
        raise EventError("coordinator comments may not contain maintainer decision commands")
    redacted_any = False
    clean = {}
    for key, value in event.items():
        if isinstance(value, str):
            value, hit = redact(value)
            redacted_any = redacted_any or hit
        clean[key] = value
    body, hit = redact(body)
    redacted_any = redacted_any or hit
    if redacted_any:
        clean["redacted"] = True
    heading = f"[weave-agent] {clean['kind']} — {clean['sender']} → {clean['recipient']}"
    parts = [heading, MARKER, "```json", json.dumps(clean, indent=2, ensure_ascii=False), "```"]
    if clean.get("summary"):
        parts.append(clean["summary"])
    if body:
        parts.append(body)
    if redacted_any:
        parts.append("_Some content was redacted before publication._")
    return "\n".join(parts) + "\n", clean


def extract(comment_body: str) -> dict | None:
    m = ENVELOPE_RE.search(comment_body)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


@dataclass
class Verdict:
    trusted: bool
    reason: str
    event: dict | None


def authenticate(comment: Comment, deliveries: dict[str, dict], coordinators: list[str]) -> Verdict:
    """Decide whether an envelope comment is an authentic coordinator event."""
    event = extract(comment.body)
    if event is None:
        return Verdict(False, "no envelope", None)
    errors = validate(event)
    if errors:
        return Verdict(False, f"schema: {errors[0]}", event)
    if comment.author not in coordinators:
        return Verdict(False, f"author {comment.author} is not an authorised coordinator", event)
    if comment.edited:
        return Verdict(False, "comment was edited after publication", event)
    record = deliveries.get(event["event_id"])
    if record is None:
        return Verdict(False, "event id not in the local run ledger (spoofed or foreign)", event)
    if record.get("comment_id") != comment.id:
        return Verdict(False, "comment id does not match the ledger delivery", event)
    if record.get("digest") != event_digest(event):
        return Verdict(False, "envelope digest does not match the ledger", event)
    return Verdict(True, "ledger match", event)


def maintainer_decision(comment: Comment, maintainers: list[str], deliveries: dict[str, dict]) -> dict | None:
    """A maintainer decision is an unedited comment, absent from the ledger, by a maintainer
    login, whose first line starts with ``/weave-decision``. Anything else is task data."""
    first = comment.body.strip().splitlines()[0] if comment.body.strip() else ""
    if not first.startswith(DECISION_PREFIX):
        return None
    if comment.author not in maintainers or comment.edited:
        return None
    if any(r.get("comment_id") == comment.id for r in deliveries.values()):
        return None
    return {"comment_id": comment.id, "author": comment.author, "created_at": comment.created_at,
            "decision": first[len(DECISION_PREFIX):].strip(), "text": comment.body.strip()}


def order_events(events: list[dict]) -> list[dict]:
    """Deduplicate by event id and order causally (causation before effect), then by time."""
    unique: dict[str, dict] = {}
    for e in events:
        unique.setdefault(e["event_id"], e)
    by_id = dict(unique)
    ordered, placed = [], set()

    def place(e: dict, depth: int = 0) -> None:
        if e["event_id"] in placed or depth > len(by_id):
            return
        cause = e.get("causation_id")
        if cause and cause in by_id and cause not in placed:
            place(by_id[cause], depth + 1)
        placed.add(e["event_id"])
        ordered.append(e)

    # Ties on the second-resolution timestamp keep delivery (comment) order.
    position = {eid: i for i, eid in enumerate(by_id)}
    for e in sorted(by_id.values(), key=lambda e: (e["created_at"], position[e["event_id"]])):
        place(e)
    return ordered
