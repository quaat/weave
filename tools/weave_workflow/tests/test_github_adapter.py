"""GhCli against a fake `gh`: pagination completeness, missing scope, rate limits, safe writes."""
import json
import stat
import tempfile
import unittest
from pathlib import Path

from tools.weave_workflow.github import GhCli, GitHubError, MissingScope, RateLimited


def issue_node(n, comments_total=0):
    return {"number": n, "title": f"T{n}", "body": "b", "url": "u", "state": "OPEN", "stateReason": None,
            "labels": {"totalCount": 1, "nodes": [{"name": "roadmap"}]}, "milestone": None,
            "blockedBy": {"totalCount": 0, "nodes": []}, "subIssues": {"totalCount": 0, "nodes": []},
            "parent": None, "comments": {"totalCount": comments_total, "nodes": []}}


class FakeGh:
    def __init__(self, responses: dict):
        self.dir = Path(tempfile.mkdtemp())
        self.log = self.dir / "calls.jsonl"
        (self.dir / "responses.json").write_text(json.dumps(responses))
        script = self.dir / "gh"
        script.write_text(f"""#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
open({str(self.log)!r}, "a").write(json.dumps(args) + "\\n")
if "--input" in args:
    payload = json.load(open(args[args.index("--input") + 1]))
    open({str(self.log)!r}, "a").write(json.dumps({{"payload": payload}}) + "\\n")
responses = json.load(open({str(self.dir / 'responses.json')!r}))
for key, resp in responses.items():
    if key in " ".join(args):
        if "exit" in resp:
            sys.stderr.write(resp.get("stderr", "")); sys.exit(resp["exit"])
        print(json.dumps(resp["out"])); sys.exit(0)
sys.stderr.write("unexpected call"); sys.exit(1)
""")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        self.path = str(script)

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()]


def page(nodes, total):
    return {"data": {"repository": {"issues": {"totalCount": total, "pageInfo": {"hasNextPage": False, "endCursor": None},
                                               "nodes": nodes}}}}


class AdapterTests(unittest.TestCase):
    def cli(self, responses):
        fake = FakeGh(responses)
        return GhCli("quaat/weave", "quaat", 3, gh=fake.path, retries=2), fake

    def test_all_pages_are_combined_and_paginated(self):
        gh, fake = self.cli({"issues(first:50": {"out": [page([issue_node(1)], 2), page([issue_node(2)], 2)]}})
        self.assertEqual([i.number for i in gh.fetch_issues()], [1, 2])
        self.assertIn("--paginate", fake.calls()[0])
        self.assertIn("--slurp", fake.calls()[0])

    def test_incomplete_listing_is_an_error(self):
        gh, _ = self.cli({"issues(first:50": {"out": [page([issue_node(1)], 3)]}})
        with self.assertRaises(GitHubError):
            gh.fetch_issues()

    def test_missing_project_scope(self):
        gh, _ = self.cli({"projectV2": {"exit": 1, "stderr": "error: your authentication token is missing required scopes [read:project]"}})
        with self.assertRaises(MissingScope):
            gh.fetch_project()

    def test_rate_limit_backs_off_then_raises(self):
        gh, fake = self.cli({"comments": {"exit": 1, "stderr": "HTTP 429: API rate limit exceeded"}})
        import tools.weave_workflow.github as mod
        sleeps = []
        original = mod.time.sleep
        mod.time.sleep = sleeps.append
        try:
            with self.assertRaises(RateLimited):
                gh.post_comment(6, "x")
        finally:
            mod.time.sleep = original
        self.assertEqual(len(sleeps), 1)

    def test_comment_body_goes_through_a_json_file_not_argv(self):
        body = "multi-line $(rm -rf /) `danger`\n\"quoted\""
        gh, fake = self.cli({"issues/6/comments": {"out": {"id": 5, "user": {"login": "quaat"}, "body": body,
                                                           "created_at": "2026-10-28T00:00:00Z"}}})
        c = gh.post_comment(6, body)
        self.assertEqual(c.id, 5)
        calls = fake.calls()
        self.assertFalse(any(body in " ".join(a) for a in calls if isinstance(a, list)))
        self.assertEqual(calls[1]["payload"], {"body": body})

    def test_status_write_uses_resolved_ids(self):
        from tools.weave_workflow.model import ProjectInfo, ProjectItem
        gh, fake = self.cli({"item-edit": {"out": {}}})
        proj = ProjectInfo("PVT_1", "W", "PVTSSF_1", {"Todo": "o1", "In Progress": "o2"}, {6: ProjectItem("PVTI_6", 6, "Todo")})
        gh.set_status(proj, "PVTI_6", "In Progress")
        args = fake.calls()[0]
        for flag, value in (("--id", "PVTI_6"), ("--project-id", "PVT_1"), ("--field-id", "PVTSSF_1"),
                            ("--single-select-option-id", "o2")):
            self.assertEqual(args[args.index(flag) + 1], value)


if __name__ == "__main__":
    unittest.main()
