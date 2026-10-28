"""Write-ahead publication of protocol events to issue comments.

Every event is queued in the local outbox before any network call. Delivery is
recorded in the ledger with the comment id and envelope digest, which is what
later authenticates the event. Messages are delivered strictly in sequence; the
first failure pauses delivery so causally dependent messages never overtake it.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import events
from .github import AmbiguousWrite, GitHubError, RateLimited
from .state import Store


class DeliveryPaused(Exception):
    """GitHub is unavailable or rate limited; messages remain queued."""


# Kinds that gates rely on may only be published by the command that produces their evidence.
# Anything relayed through the generic `event publish` path has origin "relay".
RESERVED_ORIGINS = {
    "CLAIMED": {"claim"}, "DOCS_IMPACT": {"claim"}, "PLAN": {"claim"},
    "VERIFICATION_RESULT": {"verify"}, "DOCS_AUDIT_RESULT": {"docs-audit"},
    "REVIEW_REQUESTED": {"review"}, "REVIEW_RESULT": {"review"}, "READY_TO_MERGE": {"review"},
    "TRANSITION_INTENT": {"transition"}, "STATE_CHANGED": {"transition"}, "COMPLETED": {"transition"},
    "GATE_EVALUATED": {"milestone-gate"}, "DECISION_RECORDED": set(),
}


@dataclass
class Publisher:
    store: Store
    adapter: object
    issue_repo: str
    coordinators: list[str]
    dry_run: bool = False

    def publish(self, event: dict, body: str = "", origin: str = "relay") -> dict:
        """Queue and deliver one event. Returns the published (possibly redacted) event.

        ``origin`` names the command that produced the event's evidence; reserved kinds are
        refused unless they come from their own command."""
        allowed = RESERVED_ORIGINS.get(event["kind"])
        if allowed is not None and origin not in allowed:
            raise events.EventError(f"{event['kind']} can only be published by {sorted(allowed) or 'a maintainer'}, not {origin!r}")
        text, clean = events.render(event, body)
        number = int(clean["issue"].split("#")[1])
        item = {"event_id": clean["event_id"], "issue_number": number, "text": text,
                "event": clean, "digest": events.event_digest(clean), "origin": origin,
                "attempts": 0, "sequence": self.store.next_sequence()}
        if self.dry_run:
            return clean
        self.store.enqueue(item)
        self.store.append({"type": "event", "event": clean, "sequence": item["sequence"], "origin": origin})
        self.flush()
        return clean

    def flush(self) -> int:
        """Deliver queued messages in order. Returns the number delivered."""
        delivered = 0
        known = self.store.deliveries()
        for item in self.store.pending():
            if item["event_id"] in known:
                self.store.dequeue(item["event_id"])
                continue
            comment = None
            if item.get("attempts", 0) > 0:
                # A previous attempt may have landed: never post again without a successful lookup.
                found, ok = self._find_existing(item)
                if not ok:
                    raise DeliveryPaused(f"cannot verify earlier delivery attempt of {item['event_id']}; paused")
                comment = found
            if comment is None:
                item["attempts"] = item.get("attempts", 0) + 1
                self.store.enqueue(item, replace=True)
                try:
                    comment = self.adapter.post_comment(item["issue_number"], item["text"])
                except AmbiguousWrite:
                    found, ok = self._find_existing(item)
                    if not ok or found is None:
                        raise DeliveryPaused(f"ambiguous delivery of {item['event_id']}; will verify before any retry")
                    comment = found
                except (RateLimited, GitHubError) as exc:
                    raise DeliveryPaused(f"delivery paused at {item['event_id']}: {exc}") from exc
            self.store.append({"type": "delivery", "event_id": item["event_id"],
                               "issue_number": item["issue_number"], "comment_id": comment.id,
                               "digest": item["digest"], "author": comment.author,
                               "origin": item.get("origin", "relay")})
            self.store.dequeue(item["event_id"])
            delivered += 1
        return delivered

    def _find_existing(self, item: dict):
        """Look for an earlier delivery of this event. Returns (comment or None, lookup succeeded)."""
        try:
            snap = self.adapter.snapshot()
        except GitHubError:
            return None, False
        issue = snap.issues.get(item["issue_number"])
        for comment in (issue.comments if issue else []):
            ev = events.extract(comment.body)
            if ev and ev.get("event_id") == item["event_id"] and comment.author in self.coordinators \
                    and not comment.edited and events.event_digest(ev) == item["digest"]:
                return comment, True
        return None, True


def authenticated_events(store: Store, snap, coordinators: list[str], issue_number: int) -> tuple[list[dict], list[dict]]:
    """Return (trusted events in causal order, rejected envelopes with reasons) for an issue."""
    deliveries = store.deliveries()
    trusted, rejected = [], []
    issue = snap.issues.get(issue_number)
    for comment in (issue.comments if issue else []):
        verdict = events.authenticate(comment, deliveries, coordinators)
        if verdict.event is None:
            continue
        allowed = RESERVED_ORIGINS.get(verdict.event["kind"])
        origin = deliveries.get(verdict.event["event_id"], {}).get("origin", "relay")
        if verdict.trusted and allowed is not None and origin not in allowed:
            rejected.append({"comment_id": comment.id, "author": comment.author,
                             "reason": f"{verdict.event['kind']} was not produced by its own command (origin {origin})"})
        elif verdict.trusted:
            trusted.append(verdict.event)
        else:
            rejected.append({"comment_id": comment.id, "author": comment.author, "reason": verdict.reason})
    return events.order_events(trusted), rejected


def maintainer_decisions(store: Store, snap, maintainers: list[str], issue_number: int) -> list[dict]:
    deliveries = store.deliveries()
    issue = snap.issues.get(issue_number)
    out = []
    for comment in (issue.comments if issue else []):
        d = events.maintainer_decision(comment, maintainers, deliveries)
        if d:
            out.append(d)
    return out
