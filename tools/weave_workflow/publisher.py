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


@dataclass
class Publisher:
    store: Store
    adapter: object
    issue_repo: str
    coordinators: list[str]
    dry_run: bool = False

    def publish(self, event: dict, body: str = "") -> dict:
        """Queue and deliver one event. Returns the published (possibly redacted) event."""
        text, clean = events.render(event, body)
        number = int(clean["issue"].split("#")[1])
        item = {"event_id": clean["event_id"], "issue_number": number, "text": text,
                "event": clean, "digest": events.event_digest(clean),
                "sequence": self.store.next_sequence()}
        if self.dry_run:
            return clean
        self.store.enqueue(item)
        self.store.append({"type": "event", "event": clean, "sequence": item["sequence"]})
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
            try:
                comment = self.adapter.post_comment(item["issue_number"], item["text"])
            except AmbiguousWrite:
                comment = self._find_existing(item)
                if comment is None:
                    raise DeliveryPaused(f"ambiguous delivery of {item['event_id']}; will verify and retry")
            except (RateLimited, GitHubError) as exc:
                raise DeliveryPaused(f"delivery paused at {item['event_id']}: {exc}") from exc
            self.store.append({"type": "delivery", "event_id": item["event_id"],
                               "issue_number": item["issue_number"], "comment_id": comment.id,
                               "digest": item["digest"], "author": comment.author})
            self.store.dequeue(item["event_id"])
            delivered += 1
        return delivered

    def _find_existing(self, item: dict):
        """After an ambiguous timeout, look for the comment before re-posting (dedupe)."""
        try:
            snap = self.adapter.snapshot()
        except GitHubError:
            return None
        issue = snap.issues.get(item["issue_number"])
        for comment in (issue.comments if issue else []):
            ev = events.extract(comment.body)
            if ev and ev.get("event_id") == item["event_id"] and comment.author in self.coordinators \
                    and not comment.edited and events.event_digest(ev) == item["digest"]:
                return comment
        return None


def authenticated_events(store: Store, snap, coordinators: list[str], issue_number: int) -> tuple[list[dict], list[dict]]:
    """Return (trusted events in causal order, rejected envelopes with reasons) for an issue."""
    deliveries = store.deliveries()
    trusted, rejected = [], []
    issue = snap.issues.get(issue_number)
    for comment in (issue.comments if issue else []):
        verdict = events.authenticate(comment, deliveries, coordinators)
        if verdict.event is None:
            continue
        if verdict.trusted:
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
