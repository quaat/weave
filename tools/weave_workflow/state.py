"""Local durable state: run ledger, write-ahead outbox, coordinator lock, checkpoints.

State lives under ``<git common dir>/weave-workflow`` so every worktree of the
repository shares one ledger and one lock, and nothing is committed.
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"


def state_dir(repo: Path) -> Path:
    override = os.environ.get("WEAVE_WORKFLOW_STATE")
    if override:
        path = Path(override)
    else:
        out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=repo,
                             capture_output=True, text=True, check=True).stdout.strip()
        common = Path(out)
        if not common.is_absolute():
            common = (repo / common).resolve()
        path = common / "weave-workflow"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


class LockHeld(Exception):
    pass


@dataclass
class Store:
    root: Path

    @classmethod
    def for_repo(cls, repo: Path) -> "Store":
        return cls(state_dir(repo))

    # -- ledger ---------------------------------------------------------------
    @property
    def ledger_path(self) -> Path:
        return self.root / "ledger.jsonl"

    def append(self, record: dict) -> dict:
        record = {"recorded_at": utcnow(), **record}
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        with open(self.ledger_path, "a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return record

    def records(self, rtype: str | None = None) -> list[dict]:
        if not self.ledger_path.exists():
            return []
        out = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rtype is None or rec.get("type") == rtype:
                out.append(rec)
        return out

    def events(self, issue: str | None = None) -> list[dict]:
        evs = [r["event"] for r in self.records("event")]
        return [e for e in evs if issue is None or e["issue"] == issue]

    def deliveries(self) -> dict[str, dict]:
        return {r["event_id"]: r for r in self.records("delivery")}

    def operations(self) -> dict[str, list[dict]]:
        ops: dict[str, list[dict]] = {}
        for r in self.records("operation"):
            ops.setdefault(r["operation_id"], []).append(r)
        return ops

    # -- outbox ---------------------------------------------------------------
    @property
    def outbox(self) -> Path:
        p = self.root / "outbox"
        p.mkdir(exist_ok=True, mode=0o700)
        return p

    def enqueue(self, item: dict) -> Path:
        path = self.outbox / f"{item['event_id']}.json"
        if path.exists():
            return path  # idempotent: same event id is the same message
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(item, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def pending(self) -> list[dict]:
        items = [json.loads(p.read_text(encoding="utf-8")) for p in self.outbox.glob("*.json")]
        return sorted(items, key=lambda i: (i.get("sequence", 0), i["event_id"]))

    def dequeue(self, event_id: str) -> None:
        (self.outbox / f"{event_id}.json").unlink(missing_ok=True)

    def next_sequence(self) -> int:
        seqs = [i.get("sequence", 0) for i in self.pending()]
        seqs += [r.get("sequence", 0) for r in self.records("event")]
        return max(seqs, default=0) + 1

    # -- checkpoint -----------------------------------------------------------
    @property
    def checkpoint_path(self) -> Path:
        return self.root / "checkpoint.json"

    def checkpoint(self, data: dict) -> dict:
        data = {"checkpointed_at": utcnow(), **data}
        tmp = self.checkpoint_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.checkpoint_path)
        return data

    def read_checkpoint(self) -> dict | None:
        if not self.checkpoint_path.exists():
            return None
        return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))

    # -- active run -----------------------------------------------------------
    @property
    def active_run_path(self) -> Path:
        return self.root / "active-run.json"

    def active_run(self) -> dict | None:
        if not self.active_run_path.exists():
            return None
        return json.loads(self.active_run_path.read_text(encoding="utf-8"))

    def set_active_run(self, data: dict | None) -> None:
        if data is None:
            self.active_run_path.unlink(missing_ok=True)
            return
        tmp = self.active_run_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.active_run_path)

    def run_dir(self, run_id: str) -> Path:
        p = self.root / "runs" / run_id
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        return p

    # -- coordinator lock -----------------------------------------------------
    @contextmanager
    def coordinator_lock(self, run_id: str):
        """Exclusive single-host coordinator lock (OS advisory lock)."""
        path = self.root / "coordinator.lock"
        fh = open(path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.seek(0)
            holder = fh.read().strip()
            fh.close()
            raise LockHeld(f"another coordinator holds the lock: {holder or 'unknown'}")
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps({"run_id": run_id, "pid": os.getpid(),
                                 "host": socket.gethostname(), "since": utcnow()}))
            fh.flush()
            yield
        finally:
            fh.seek(0)
            fh.truncate()
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()


def heartbeat_expired(heartbeat_at: str, ttl_seconds: int, now: float | None = None) -> bool:
    ts = datetime.fromisoformat(heartbeat_at.replace("Z", "+00:00")).timestamp()
    return (now if now is not None else time.time()) - ts > ttl_seconds
