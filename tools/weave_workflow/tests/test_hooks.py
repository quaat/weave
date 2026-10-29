"""Scenarios 5 and 7: worker restrictions, guards, stop behaviour, cancellation checkpoints."""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.weave_workflow import hooks
from tools.weave_workflow.state import Store

from .support import ROOT


class HookHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["WEAVE_WORKFLOW_STATE"] = self.tmp
        self.store = Store(Path(self.tmp))

    def tearDown(self):
        del os.environ["WEAVE_WORKFLOW_STATE"]

    def call(self, event, **payload):
        payload.setdefault("cwd", str(ROOT))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hooks.main(event, io.StringIO(json.dumps(payload)))
        out = buf.getvalue().strip()
        return rc, json.loads(out) if out else None

    def decision(self, out):
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def start_run(self, **extra):
        self.store.set_active_run({"run_id": "run-test-0001", "active_issue": 6, **extra})


class GuardTests(HookHarness):
    def test_workers_cannot_use_github_or_push(self):
        for cmd in ("gh issue comment 6 --body x", "gh project item-edit --id X", "git push origin HEAD",
                    "curl -X POST https://api.github.com/repos/quaat/weave/issues", "codex exec hi",
                    "git remote set-url origin x", "cd a && gh api -X PATCH repos/x"):
            with self.subTest(cmd=cmd):
                _, out = self.call("PreToolUse", tool_name="Bash", tool_input={"command": cmd}, agent_type="weave-implementer")
                self.assertEqual(self.decision(out), "deny")

    def test_worker_shell_has_credentials_removed(self):
        _, out = self.call("PreToolUse", tool_name="Bash", tool_input={"command": "python3 -m unittest", "timeout": 5},
                           agent_type="weave-verifier")
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["permissionDecision"], "allow")
        self.assertTrue(hso["updatedInput"]["command"].startswith("unset GH_TOKEN"))
        self.assertTrue(hso["updatedInput"]["command"].endswith("python3 -m unittest"))
        self.assertEqual(hso["updatedInput"]["timeout"], 5)

    def test_worker_cannot_edit_protected_paths_or_leave_allowed_paths(self):
        for path in ("specification/PROVENANCE.json", ".github/workflows/ci.yml",
                     "agent-kit/.agents/skills/weave/assets/prototype/checker.py", "tools/weave_workflow/policy.json"):
            with self.subTest(path=path):
                _, out = self.call("PreToolUse", tool_name="Edit", tool_input={"file_path": str(ROOT / path)},
                                   agent_type="weave-implementer")
                self.assertEqual(self.decision(out), "deny")
        self.start_run(delegations={"weave-implementer": {"allowed_paths": ["inventory-proof/**"]}})
        _, out = self.call("PreToolUse", tool_name="Write", tool_input={"file_path": str(ROOT / "agent-kit/README.md")},
                           agent_type="weave-implementer")
        self.assertEqual(self.decision(out), "deny")
        rc, out = self.call("PreToolUse", tool_name="Write", tool_input={"file_path": str(ROOT / "inventory-proof/x.py")},
                            agent_type="weave-implementer")
        self.assertIsNone(out)

    def test_main_session_guards(self):
        _, out = self.call("PreToolUse", tool_name="Bash", tool_input={"command": "git push --force origin main"})
        self.assertEqual(self.decision(out), "deny")
        _, out = self.call("PreToolUse", tool_name="Bash", tool_input={"command": "gh pr merge 3 --squash"})
        self.assertEqual(self.decision(out), "ask")
        _, out = self.call("PreToolUse", tool_name="Bash", tool_input={"command": "git reset --hard HEAD~1"})
        self.assertEqual(self.decision(out), "ask")

    def test_direct_board_writes_only_guarded_during_a_run(self):
        cmd = {"command": "gh project item-edit --id X --field-id Y"}
        _, out = self.call("PreToolUse", tool_name="Bash", tool_input=cmd)
        self.assertIsNone(out)  # ordinary work outside a run is not disturbed
        self.start_run()
        _, out = self.call("PreToolUse", tool_name="Bash", tool_input=cmd)
        self.assertEqual(self.decision(out), "ask")

    def test_guard_fails_closed_for_workers(self):
        rc, _ = self.call("PreToolUse", tool_name="Edit", tool_input={"file_path": 42}, agent_type="weave-implementer")
        self.assertEqual(rc, 2)


class LifecycleHookTests(HookHarness):
    def test_inert_without_a_run(self):
        for event in ("Stop", "SessionStart", "PreCompact", "SessionEnd", "SubagentStart", "PostToolUse"):
            with self.subTest(event=event):
                self.assertEqual(self.call(event, session_id="s"), (0, None))
        self.assertEqual(self.store.records(), [])

    def test_stop_blocks_at_most_twice_and_never_recurses(self):
        self.start_run()
        self.store.enqueue({"event_id": "ev-pending-0001", "issue_number": 6, "text": "x",
                            "event": {"kind": "PROGRESS"}, "digest": "d", "sequence": 1})
        _, out = self.call("Stop", session_id="s1", stop_hook_active=True)
        self.assertIsNone(out)
        blocks = [self.call("Stop", session_id="s2")[1] for _ in range(3)]
        self.assertEqual([b and b["decision"] for b in blocks], ["block", "block", None])
        self.assertIn("not yet delivered", blocks[0]["reason"])
        self.assertEqual(self.store.read_checkpoint()["pending_messages"], ["ev-pending-0001"])

    def test_checkpoints_on_compact_end_and_cancellation(self):
        self.start_run()
        self.call("PreCompact", trigger="auto")
        self.assertIn("pre-compact", self.store.read_checkpoint()["reason"])
        self.call("SessionEnd", reason="exit")
        self.assertIn("session end", self.store.read_checkpoint()["reason"])
        self.assertTrue(any(r.get("phase") == "session-ended" for r in self.store.records("run")))
        from tools.weave_workflow.cli import main
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["run", "stop", "--reason", "user cancelled"]), 0)
        self.assertIsNone(self.store.active_run())
        self.assertEqual(self.store.read_checkpoint()["status"], "stopped")

    def test_evidence_and_docs_audit_queue(self):
        self.start_run()
        self.call("SubagentStart", agent_id="a1", agent_type="weave-implementer")
        self.call("PostToolUse", tool_name="Edit", tool_input={"file_path": str(ROOT / "agent-kit/README.md")},
                  agent_type="weave-implementer")
        self.assertEqual([r["agent_type"] for r in self.store.records("subagent")], ["weave-implementer"])
        self.assertTrue(self.store.records("evidence")[0]["docs_audit_queued"])
        self.assertIn("agent-kit/README.md", json.loads((self.store.root / "docs-audit-pending.json").read_text()))

    def test_docs_audit_queue_uses_the_edited_files_own_tree(self):
        self.start_run()
        other = Path(tempfile.mkdtemp()) / "tree"
        self.addCleanup(shutil.rmtree, other.parent, True)
        (other / "tools/weave_workflow").mkdir(parents=True)
        (other / "notes").mkdir()
        subprocess.run(["git", "init", "-q"], cwd=other, check=True)
        docmap = json.loads((ROOT / "tools/weave_workflow/docmap.json").read_text())
        docmap["managed_documents"].append("notes/*.md")    # managed only by the other tree's map
        (other / "tools/weave_workflow/docmap.json").write_text(json.dumps(docmap))
        for name in ("notes/guide.md", "scratch.md"):
            (other / name).write_text("x\n")
            self.call("PostToolUse", tool_name="Edit", tool_input={"file_path": str(other / name)})  # cwd: ROOT
        queued = json.loads((self.store.root / "docs-audit-pending.json").read_text())
        self.assertEqual(len(queued), 1)
        self.assertTrue(queued[0].endswith("notes/guide.md"), queued)

    def test_session_start_context(self):
        self.start_run()  # a run record from before concurrent claims: a single active_issue
        _, out = self.call("SessionStart", source="resume")
        self.assertIn("reconcile", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("on issues #6,", out["hookSpecificOutput"]["additionalContext"])
        self.call("PreCompact", trigger="auto")
        self.assertEqual(self.store.read_checkpoint()["active_issues"], [6])
        self.assertNotIn("active_issue", self.store.read_checkpoint())

    def test_every_active_issue_is_named_and_checkpointed(self):
        self.store.set_active_run({"run_id": "run-test-0001", "active_issues": [6, 7]})
        _, out = self.call("SessionStart", source="resume")
        self.assertIn("on issues #6, #7,", out["hookSpecificOutput"]["additionalContext"])
        self.call("PreCompact", trigger="auto")
        self.assertEqual(self.store.read_checkpoint()["active_issues"], [6, 7])


class SettingsTests(unittest.TestCase):
    def test_settings_register_every_handler(self):
        settings = json.loads((ROOT / ".claude/settings.json").read_text())
        self.assertEqual(set(settings["hooks"]), set(hooks.HANDLERS))
        for entries in settings["hooks"].values():
            for entry in entries:
                for h in entry["hooks"]:
                    self.assertIn(".claude/hooks/weave_hook.py", h["command"])

    def test_worker_agents_match_policy(self):
        policy = json.loads((ROOT / "tools/weave_workflow/policy.json").read_text())
        names = sorted(p.stem for p in (ROOT / ".claude/agents").glob("*.md"))
        self.assertEqual(names, sorted(policy["worker_agent_types"]))
        for p in (ROOT / ".claude/agents").glob("*.md"):
            front = p.read_text().split("---")[1]
            if "reviewer" in p.stem or p.stem in ("weave-verifier", "weave-investigator"):
                self.assertNotIn("Edit", front)
                self.assertNotIn("Write", front)


if __name__ == "__main__":
    unittest.main()
