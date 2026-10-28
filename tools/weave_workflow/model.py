"""Plain data model for a reconciled view of the repository, board and runs."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

STATUSES = ("Todo", "In Progress", "In Review", "Done")


def milestone_key(title: str) -> str | None:
    """Stable identity of a roadmap milestone: the leading ``M<number>`` of its title."""
    m = re.match(r"^\s*(M\d+)\b", title)
    return m.group(1) if m else None


def milestone_order(key: str) -> int:
    return int(key[1:])


def digest(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Milestone:
    number: int
    title: str
    state: str

    @property
    def key(self) -> str | None:
        return milestone_key(self.title)


@dataclass
class Comment:
    id: int
    author: str
    body: str
    created_at: str
    edited: bool


@dataclass
class Issue:
    number: int
    title: str
    body: str
    state: str = "open"
    state_reason: str | None = None
    labels: list[str] = field(default_factory=list)
    milestone: Milestone | None = None
    comments: list[Comment] = field(default_factory=list)
    blocked_by: list[int] = field(default_factory=list)
    sub_issues: list[int] = field(default_factory=list)
    parent: int | None = None
    url: str = ""

    @property
    def milestone_key(self) -> str | None:
        return self.milestone.key if self.milestone else None

    @property
    def completed(self) -> bool:
        return self.state == "closed" and self.state_reason == "completed"


@dataclass
class ProjectItem:
    item_id: str
    issue: int
    status: str | None
    option_id: str | None = None


@dataclass
class ProjectInfo:
    project_id: str
    title: str
    status_field_id: str
    options: dict[str, str]
    items: dict[int, ProjectItem]


@dataclass
class PullRequest:
    number: int
    state: str
    merged: bool
    head_ref: str
    head_sha: str
    base_ref: str
    base_sha: str
    merge_sha: str | None
    closes: list[int]
    checks: list[tuple[str, str]]
    review_decision: str | None
    merged_by: str | None = None


@dataclass
class Snapshot:
    issues: dict[int, Issue]
    milestones: list[Milestone]
    pulls: list[PullRequest] = field(default_factory=list)
    project: ProjectInfo | None = None
    project_error: str | None = None
    branch_protection: dict | None = None
    notes: list[str] = field(default_factory=list)

    def status_of(self, number: int) -> str | None:
        if not self.project:
            return None
        item = self.project.items.get(number)
        return item.status if item else None


# ----------------------------------------------------------------- issue bodies

SECTION_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)
CHECKBOX_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.+?)\s*$", re.M)


def sections(body: str) -> dict[str, str]:
    """Split a Markdown body into ``{heading: text}`` for level-2/3 headings."""
    out: dict[str, str] = {}
    matches = list(SECTION_RE.finditer(body))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out[m.group(2)] = body[m.end():end].strip()
    return out


def acceptance_criteria(body: str) -> list[dict]:
    """Stable criterion IDs (AC-n, in document order) with preserved text digests."""
    crit = []
    for heading, text in sections(body).items():
        if not heading.lower().startswith(("acceptance criteria", "definition of done")):
            continue
        for m in CHECKBOX_RE.finditer(text):
            crit.append({"text": m.group(2), "checked": m.group(1) != " ", "section": heading})
    for i, c in enumerate(crit, 1):
        c["id"] = f"AC-{i}"
        c["text_digest"] = digest(c["text"])
    return crit


def requirements_digest(issue: Issue) -> str:
    """Digest of scope and criteria; any material change invalidates plans and reviews."""
    parts = [issue.title, issue.milestone_key or "-"]
    for heading, text in sections(issue.body).items():
        if heading.lower().startswith(("scope", "acceptance criteria", "definition of done",
                                       "depends on", "out of scope", "decisions to record",
                                       "required cases", "rules")):
            # Ticking a checkbox records progress; it does not change the requirement.
            parts.append(f"## {heading}\n" + re.sub(r"\[(?: |x|X)\]", "[ ]", text))
    return digest("\n\n".join(parts))


# ------------------------------------------------------------- serialisation


def snapshot_to_dict(snap: Snapshot) -> dict:
    from dataclasses import asdict
    data = asdict(snap)
    data["issues"] = {str(k): v for k, v in data["issues"].items()}
    if data["project"]:
        data["project"]["items"] = {str(k): v for k, v in data["project"]["items"].items()}
    return data


def snapshot_from_dict(data: dict) -> Snapshot:
    def ms(d):
        return Milestone(**d) if d else None
    issues = {}
    for k, v in data["issues"].items():
        v = dict(v)
        v["milestone"] = ms(v.get("milestone"))
        v["comments"] = [Comment(**c) for c in v.get("comments", [])]
        issues[int(k)] = Issue(**v)
    project = None
    if data.get("project"):
        p = dict(data["project"])
        p["items"] = {int(k): ProjectItem(**v) for k, v in p["items"].items()}
        project = ProjectInfo(**p)
    pulls = []
    for pr in data.get("pulls", []):
        pr = dict(pr)
        pr["checks"] = [tuple(c) for c in pr.get("checks", [])]
        pulls.append(PullRequest(**pr))
    return Snapshot(issues=issues, milestones=[Milestone(**m) for m in data["milestones"]], pulls=pulls,
                    project=project, project_error=data.get("project_error"),
                    branch_protection=data.get("branch_protection"), notes=list(data.get("notes", [])))
