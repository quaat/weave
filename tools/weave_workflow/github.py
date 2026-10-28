"""Typed GitHub adapter: a ``gh``-backed implementation and an in-memory fake.

Reads page through every connection and verify completeness against reported
totals. Writes take JSON bodies from temporary UTF-8 files and argument arrays;
nothing is interpolated into a shell.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .model import (Comment, Issue, Milestone, ProjectInfo, ProjectItem, PullRequest,
                    Snapshot, milestone_key)


class GitHubError(Exception):
    pass


class RateLimited(GitHubError):
    pass


class MissingScope(GitHubError):
    pass


class AmbiguousWrite(GitHubError):
    """A write may or may not have happened (timeout, dropped connection)."""


# --------------------------------------------------------------------------- gh


ISSUES_QUERY = """
query($owner:String!,$name:String!,$endCursor:String){
  repository(owner:$owner,name:$name){
    issues(first:50,after:$endCursor,orderBy:{field:CREATED_AT,direction:ASC}){
      totalCount pageInfo{hasNextPage endCursor}
      nodes{
        number title body url state stateReason
        labels(first:100){totalCount nodes{name}}
        milestone{number title state}
        blockedBy(first:100){totalCount nodes{number}}
        subIssues(first:100){totalCount nodes{number}}
        parent{number}
        comments(first:100){totalCount nodes{databaseId author{login} body createdAt lastEditedAt}}
      }
    }
  }
}"""

COMMENTS_QUERY = """
query($owner:String!,$name:String!,$number:Int!,$endCursor:String){
  repository(owner:$owner,name:$name){issue(number:$number){
    comments(first:100,after:$endCursor){totalCount pageInfo{hasNextPage endCursor}
      nodes{databaseId author{login} body createdAt lastEditedAt}}}}
}"""

PROJECT_QUERY = """
query($owner:String!,$number:Int!,$endCursor:String){
  user(login:$owner){projectV2(number:$number){
    id title
    fields(first:50){nodes{... on ProjectV2SingleSelectField{id name options{id name}}}}
    items(first:100,after:$endCursor){totalCount pageInfo{hasNextPage endCursor}
      nodes{id content{... on Issue{number repository{nameWithOwner}}}
        fieldValueByName(name:"Status"){... on ProjectV2ItemFieldSingleSelectValue{name optionId}}}}
  }}
}"""

PULLS_QUERY = """
query($owner:String!,$name:String!,$endCursor:String){
  repository(owner:$owner,name:$name){
    pullRequests(first:50,after:$endCursor,orderBy:{field:CREATED_AT,direction:ASC}){
      totalCount pageInfo{hasNextPage endCursor}
      nodes{number state merged headRefName headRefOid baseRefName baseRefOid
        mergeCommit{oid} reviewDecision mergedBy{login}
        closingIssuesReferences(first:20){nodes{number}}
        commits(last:1){nodes{commit{oid statusCheckRollup{state
          contexts(first:100){totalCount nodes{__typename ... on CheckRun{name status conclusion}
                                             ... on StatusContext{context state}}}}}}}}
    }
  }
}"""


@dataclass
class GhCli:
    repo: str
    project_owner: str
    project_number: int
    gh: str = "gh"
    retries: int = 3

    @property
    def owner(self) -> str:
        return self.repo.split("/")[0]

    @property
    def name(self) -> str:
        return self.repo.split("/")[1]

    # -- transport ------------------------------------------------------------
    def _run(self, args: list[str], input_text: str | None = None) -> str:
        delay = 2.0
        for attempt in range(self.retries):
            try:
                proc = subprocess.run([self.gh, *args], input=input_text, capture_output=True,
                                      text=True, timeout=120)
            except subprocess.TimeoutExpired as exc:
                raise AmbiguousWrite(f"gh timed out: {args[:3]}") from exc
            if proc.returncode == 0:
                return proc.stdout
            err = proc.stderr + proc.stdout
            if "missing required scopes" in err or "INSUFFICIENT_SCOPES" in err:
                raise MissingScope(err.strip().splitlines()[0])
            if "rate limit" in err.lower() or "HTTP 429" in err or "secondary rate" in err.lower():
                if attempt + 1 == self.retries:
                    raise RateLimited(err.strip()[:300])
                time.sleep(delay)
                delay *= 2
                continue
            raise GitHubError(err.strip()[:500])
        raise GitHubError("unreachable")

    def _graphql_pages(self, query: str, variables: dict) -> list[dict]:
        args = ["api", "graphql", "--paginate", "--slurp", "-f", f"query={query}"]
        for key, value in variables.items():
            args += ["-F" if isinstance(value, int) else "-f", f"{key}={value}"]
        pages = json.loads(self._run(args))
        for page in pages:
            if page.get("errors"):
                msg = json.dumps(page["errors"])[:500]
                if "INSUFFICIENT_SCOPES" in msg or "read:project" in msg:
                    raise MissingScope(msg)
                raise GitHubError(msg)
        return pages

    def _rest(self, method: str, path: str, payload: dict | None = None) -> object:
        args = ["api", "-X", method, path]
        if payload is None:
            out = self._run(args)
        else:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as fh:
                json.dump(payload, fh, ensure_ascii=False)
                tmp = fh.name
            try:
                out = self._run(args + ["--input", tmp])
            finally:
                Path(tmp).unlink(missing_ok=True)
        return json.loads(out) if out.strip() else None

    # -- reads ----------------------------------------------------------------
    def fetch_milestones(self) -> list[Milestone]:
        pages = json.loads(self._run(["api", "--paginate", "--slurp",
                                      f"repos/{self.repo}/milestones?state=all&per_page=100"]))
        return [Milestone(m["number"], m["title"], m["state"]) for page in pages for m in page]

    def fetch_issues(self) -> list[Issue]:
        pages = self._graphql_pages(ISSUES_QUERY, {"owner": self.owner, "name": self.name})
        issues, total = [], None
        for page in pages:
            conn = page["data"]["repository"]["issues"]
            total = conn["totalCount"]
            for node in conn["nodes"]:
                issues.append(self._issue(node))
        if total is not None and len(issues) != total:
            raise GitHubError(f"incomplete issue listing: {len(issues)} of {total}")
        return issues

    def _issue(self, node: dict) -> Issue:
        for conn in ("labels", "blockedBy", "subIssues"):
            if node[conn]["totalCount"] > len(node[conn]["nodes"]):
                raise GitHubError(f"#{node['number']}: {conn} exceeds one page; extend the adapter")
        comments = [self._comment(c) for c in node["comments"]["nodes"]]
        if node["comments"]["totalCount"] > len(comments):
            comments = self.fetch_comments(node["number"])
        ms = node["milestone"]
        return Issue(
            number=node["number"], title=node["title"], body=node["body"] or "", url=node["url"],
            state=node["state"].lower(), state_reason=(node["stateReason"] or "").lower() or None,
            labels=[l["name"] for l in node["labels"]["nodes"]],
            milestone=Milestone(ms["number"], ms["title"], ms["state"].lower()) if ms else None,
            comments=comments,
            blocked_by=[n["number"] for n in node["blockedBy"]["nodes"]],
            sub_issues=[n["number"] for n in node["subIssues"]["nodes"]],
            parent=node["parent"]["number"] if node["parent"] else None,
        )

    @staticmethod
    def _comment(c: dict) -> Comment:
        return Comment(id=c["databaseId"], author=(c["author"] or {}).get("login", "ghost"),
                       body=c["body"], created_at=c["createdAt"], edited=c["lastEditedAt"] is not None)

    def fetch_comments(self, number: int) -> list[Comment]:
        pages = self._graphql_pages(COMMENTS_QUERY, {"owner": self.owner, "name": self.name, "number": number})
        out = [self._comment(c) for p in pages for c in p["data"]["repository"]["issue"]["comments"]["nodes"]]
        total = pages[-1]["data"]["repository"]["issue"]["comments"]["totalCount"] if pages else 0
        if len(out) != total:
            raise GitHubError(f"#{number}: incomplete comments {len(out)} of {total}")
        return out

    def fetch_project(self) -> ProjectInfo:
        pages = self._graphql_pages(PROJECT_QUERY, {"owner": self.project_owner, "number": self.project_number})
        proj = pages[0]["data"]["user"]["projectV2"]
        if proj is None:
            raise GitHubError(f"project {self.project_number} not found for {self.project_owner}")
        status = [f for f in proj["fields"]["nodes"] if f and f.get("name") == "Status"]
        if len(status) != 1:
            raise GitHubError("project has no unique single-select 'Status' field")
        items, total = {}, 0
        for page in pages:
            conn = page["data"]["user"]["projectV2"]["items"]
            total = conn["totalCount"]
            for node in conn["nodes"]:
                content = node["content"] or {}
                if content.get("repository", {}).get("nameWithOwner") != self.repo:
                    continue
                value = node["fieldValueByName"] or {}
                items[content["number"]] = ProjectItem(node["id"], content["number"], value.get("name"), value.get("optionId"))
        seen = sum(len(p["data"]["user"]["projectV2"]["items"]["nodes"]) for p in pages)
        if seen != total:
            raise GitHubError(f"incomplete project item listing: {seen} of {total}")
        return ProjectInfo(project_id=proj["id"], title=proj["title"], status_field_id=status[0]["id"],
                           options={o["name"]: o["id"] for o in status[0]["options"]}, items=items)

    def fetch_pulls(self) -> list[PullRequest]:
        pages = self._graphql_pages(PULLS_QUERY, {"owner": self.owner, "name": self.name})
        pulls = []
        for page in pages:
            for n in page["data"]["repository"]["pullRequests"]["nodes"]:
                commit = n["commits"]["nodes"][0]["commit"] if n["commits"]["nodes"] else {}
                rollup = commit.get("statusCheckRollup") or {}
                checks = []
                contexts = rollup.get("contexts") or {"totalCount": 0, "nodes": []}
                complete = contexts["totalCount"] == len(contexts["nodes"])
                for c in contexts["nodes"]:
                    if c["__typename"] == "CheckRun":
                        checks.append((c["name"], (c["conclusion"] or c["status"] or "").upper()))
                    else:
                        checks.append((c["context"], (c["state"] or "").upper()))
                pulls.append(PullRequest(
                    number=n["number"], state=n["state"].lower(), merged=n["merged"],
                    head_ref=n["headRefName"], head_sha=n["headRefOid"], base_ref=n["baseRefName"],
                    base_sha=n["baseRefOid"], merge_sha=(n["mergeCommit"] or {}).get("oid"),
                    closes=[i["number"] for i in n["closingIssuesReferences"]["nodes"]],
                    checks=checks, review_decision=n["reviewDecision"],
                    merged_by=(n["mergedBy"] or {}).get("login"), checks_complete=complete))
        return pulls

    def fetch_branch_protection(self, branch: str) -> dict | None:
        try:
            return self._rest("GET", f"repos/{self.repo}/branches/{branch}/protection")
        except GitHubError as exc:
            if "Branch not protected" in str(exc):
                return None
            raise

    def snapshot(self) -> Snapshot:
        snap = Snapshot(issues={i.number: i for i in self.fetch_issues()},
                        milestones=self.fetch_milestones(), pulls=self.fetch_pulls())
        try:
            snap.project = self.fetch_project()
        except MissingScope as exc:
            snap.project_error = f"missing project scope: {exc}"
        try:
            snap.branch_protection = self.fetch_branch_protection("main")
        except GitHubError as exc:
            snap.branch_protection_error = str(exc)
            snap.notes.append(f"branch protection unreadable: {exc}")
        return snap

    # -- writes ---------------------------------------------------------------
    def post_comment(self, number: int, body: str) -> Comment:
        out = self._rest("POST", f"repos/{self.repo}/issues/{number}/comments", {"body": body})
        return Comment(id=out["id"], author=out["user"]["login"], body=out["body"],
                       created_at=out["created_at"], edited=False)

    def set_status(self, project: ProjectInfo, item_id: str, option_name: str) -> None:
        option = project.options[option_name]
        self._run(["project", "item-edit", "--id", item_id, "--project-id", project.project_id,
                   "--field-id", project.status_field_id, "--single-select-option-id", option])

    def read_status(self, item_id: str) -> str | None:
        out = self._graphql_pages(
            'query($id:ID!){node(id:$id){... on ProjectV2Item{fieldValueByName(name:"Status"){'
            '... on ProjectV2ItemFieldSingleSelectValue{name}}}}}', {"id": item_id})
        value = out[0]["data"]["node"]["fieldValueByName"] or {}
        return value.get("name")

    def add_labels(self, number: int, labels: list[str]) -> None:
        self._rest("POST", f"repos/{self.repo}/issues/{number}/labels", {"labels": labels})

    def remove_label(self, number: int, label: str) -> None:
        try:
            self._rest("DELETE", f"repos/{self.repo}/issues/{number}/labels/{label}")
        except GitHubError as exc:
            if "Label does not exist" not in str(exc):
                raise

    def ensure_label(self, name: str, color: str, description: str) -> bool:
        existing = json.loads(self._run(["api", "--paginate", "--slurp", f"repos/{self.repo}/labels?per_page=100"]))
        if name in {l["name"] for page in existing for l in page}:
            return False
        self._rest("POST", f"repos/{self.repo}/labels", {"name": name, "color": color, "description": description})
        return True


# ------------------------------------------------------------------------- fake


@dataclass
class FakeGitHub:
    """In-memory GitHub used by tests and offline rehearsals."""

    snapshot_data: Snapshot
    actor: str = "quaat"
    fail_next: list[str] = field(default_factory=list)  # e.g. ["post_comment:ambiguous"]
    log: list[tuple] = field(default_factory=list)
    _next_comment_id: int = 1000

    def _maybe_fail(self, op: str) -> str | None:
        for i, spec in enumerate(self.fail_next):
            name, _, mode = spec.partition(":")
            if name == op:
                del self.fail_next[i]
                return mode
        return None

    def snapshot(self) -> Snapshot:
        if self._maybe_fail("snapshot") == "unavailable":
            raise GitHubError("GitHub unavailable")
        return self.snapshot_data

    def post_comment(self, number: int, body: str) -> Comment:
        mode = self._maybe_fail("post_comment")
        if mode == "rate":
            raise RateLimited("rate limited")
        if mode == "unavailable":
            raise GitHubError("GitHub unavailable")
        self._next_comment_id += 1
        comment = Comment(self._next_comment_id, self.actor, body, "2026-10-28T00:00:00Z", False)
        self.snapshot_data.issues[number].comments.append(comment)
        self.log.append(("comment", number, comment.id))
        if mode == "ambiguous":  # write landed but the caller never heard back
            raise AmbiguousWrite("timeout after write")
        return comment

    def set_status(self, project: ProjectInfo, item_id: str, option_name: str) -> None:
        mode = self._maybe_fail("set_status")
        if mode == "unavailable":
            raise GitHubError("GitHub unavailable")
        if option_name not in project.options:
            raise GitHubError(f"unknown option {option_name}")
        for item in project.items.values():
            if item.item_id == item_id:
                item.status = option_name
                item.option_id = project.options[option_name]
                self.log.append(("status", item.issue, option_name))
                if mode == "ambiguous":
                    raise AmbiguousWrite("timeout after write")
                return
        raise GitHubError(f"unknown item {item_id}")

    def read_status(self, item_id: str) -> str | None:
        for item in self.snapshot_data.project.items.values():
            if item.item_id == item_id:
                return item.status
        return None

    def add_labels(self, number: int, labels: list[str]) -> None:
        issue = self.snapshot_data.issues[number]
        for label in labels:
            if label not in issue.labels:
                issue.labels.append(label)
        self.log.append(("labels+", number, tuple(labels)))

    def remove_label(self, number: int, label: str) -> None:
        issue = self.snapshot_data.issues[number]
        if label in issue.labels:
            issue.labels.remove(label)
            self.log.append(("labels-", number, label))

    def ensure_label(self, name: str, color: str, description: str) -> bool:
        self.log.append(("ensure_label", name))
        return False


def milestone_index(snapshot: Snapshot) -> dict[str, Milestone]:
    """Map stable milestone keys (M0, M1, ...) to milestone objects; reject duplicates."""
    out: dict[str, Milestone] = {}
    for m in snapshot.milestones:
        key = milestone_key(m.title)
        if key is None:
            continue
        if key in out:
            raise GitHubError(f"duplicate milestone key {key}: {out[key].title!r} and {m.title!r}")
        out[key] = m
    return out
