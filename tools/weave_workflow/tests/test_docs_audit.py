"""Scenarios 9 and 10: guidance and provenance intact; documentation drift is detected and blocks."""
import json
import shutil
import subprocess
import unittest

from tools.weave_workflow import docs_audit

from .support import ROOT, repo_copy


class RepositoryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = docs_audit.audit(ROOT)

    def test_repository_has_no_residual_drift(self):
        self.assertEqual(self.result.result, "PASS", [f.__dict__ for f in self.result.findings])
        self.assertGreater(self.result.counts["claims"], 5)
        self.assertGreater(self.result.counts["synced_and_provenance"], 70)

    def test_existing_guidance_is_kept_and_claude_md_is_short(self):
        self.assertEqual((ROOT / "agent-kit/CLAUDE.md").read_text().strip(), "@AGENTS.md")
        self.assertTrue((ROOT / "agent-kit/AGENTS.md").exists())
        claude = (ROOT / "CLAUDE.md").read_text()
        self.assertTrue(claude.startswith("@AGENTS.md"))
        self.assertLess(len(claude.splitlines()), 150)

    def test_snapshots_and_policy_are_protected(self):
        policy = json.loads((ROOT / "tools/weave_workflow/policy.json").read_text())
        for path in ("specification/reference/prototype/", "agent-kit/.agents/skills/weave/assets/prototype/",
                     "specification/PROVENANCE.json", "agent-kit/PROVENANCE.json"):
            self.assertIn(path, policy["protected_paths"])

    def test_documentation_map_is_current(self):
        text = (ROOT / "docs/development/documentation-map.md").read_text()
        self.assertIn(docs_audit.render_docs_map(docs_audit.load_docmap()), text)


class DriftTests(unittest.TestCase):
    """Each test mutates a throwaway copy of the repository and expects the audit to fail."""

    def setUp(self):
        self.repo = repo_copy()

    def tearDown(self):
        shutil.rmtree(self.repo.parent, ignore_errors=True)

    def edit(self, rel, old, new):
        p = self.repo / rel
        text = p.read_text()
        self.assertIn(old, text, f"fixture text missing in {rel}")
        p.write_text(text.replace(old, new, 1))

    def findings(self, base=None, impact=None, severity="error"):
        res = docs_audit.audit(self.repo, base=base, impact=impact)
        return res, [(f.check, f.path, f.message) for f in res.findings if f.severity == severity]

    def assertFinding(self, findings, check, path_part=""):
        self.assertTrue(any(c == check and path_part in p for c, p, _ in findings), findings)

    def test_baseline_copy_passes(self):
        res, errors = self.findings()
        self.assertEqual(res.result, "PASS", errors)

    def test_changed_count_is_detected(self):
        self.edit("README.md", "# 143 tests, including", "# 144 tests, including")
        res, errors = self.findings()
        self.assertEqual(res.result, "FAIL")
        self.assertFinding(errors, "claim", "README.md")

    def test_count_change_in_artefact_without_doc_update(self):
        self.edit("inventory-proof/tests/test_checker.py", "class ", "class ExtraTest(__import__('unittest').TestCase):\n    def test_extra(self):\n        pass\n\n\nclass ", )
        _, errors = self.findings()
        self.assertFinding(errors, "claim", "README.md")

    def test_removed_path_is_detected(self):
        (self.repo / "agent-kit/docs/commands.md").unlink()
        _, errors = self.findings()
        self.assertFinding(errors, "path")

    def test_unknown_command_is_detected(self):
        self.edit("agent-kit/README.md", "\n", "\nRun `python3 scripts/weave.py frobnicate` first.\n")
        _, errors = self.findings()
        self.assertFinding(errors, "command", "agent-kit/README.md")

    def test_unknown_diagnostic_is_detected(self):
        self.edit("inventory-proof/README.md", "\n", "\nThe checker reports E999 for this case.\n")
        _, errors = self.findings()
        self.assertFinding(errors, "diagnostic", "inventory-proof/README.md")

    def test_synced_copy_divergence_is_detected(self):
        self.edit("agent-kit/docs/weave.md", "\n", "\nAn unsynced edit.\n")
        _, errors = self.findings()
        self.assertFinding(errors, "synced-copy")

    def test_hand_edited_generated_document_is_flagged(self):
        self.edit("inventory-proof/ACTUAL_OUTPUT.txt", "states=841", "states=842")
        _, errors = self.findings()
        self.assertFinding(errors, "generated", "inventory-proof/ACTUAL_OUTPUT.txt")
        self.assertFinding(errors, "claim")

    def test_provenance_tamper_is_detected(self):
        self.edit("specification/reference/prototype/checker.py", "\n", "\n# tampered\n")
        _, errors = self.findings()
        self.assertFinding(errors, "provenance", "specification/PROVENANCE.json")

    def test_boundary_moved_without_specification_update(self):
        line = next(l for l in (self.repo / "README.md").read_text().splitlines() if "is specified, not implemented" in l)
        self.edit("README.md", line + "\n", "")
        _, errors = self.findings(base="HEAD")
        self.assertFinding(errors, "boundary", "README.md")
        for rel in ("status.rst", "limitations.rst", "design-history.rst"):
            self.edit(f"specification/docs/chapters/{rel}", "\n", "\n\n")
        _, errors = self.findings(base="HEAD")
        self.assertFalse([e for e in errors if e[0] == "boundary"])

    def test_code_change_without_mapped_documents_fails_and_impact_justification_is_honoured(self):
        self.edit("agent-kit/scripts/weave.py", "\n", "\n# behaviour change\n")
        _, errors = self.findings(base="HEAD")
        self.assertFinding(errors, "impact", "agent-kit/README.md")
        self.assertFinding(errors, "changelog", "agent-kit/CHANGELOG.md")
        required = docs_audit.required_documents(docs_audit.load_docmap(), {"agent-kit/scripts/weave.py": "M"})
        impact = [{"path": d, "reason": "r", "status": "not-applicable", "justification": "comment only"} for d in required]
        self.edit("agent-kit/CHANGELOG.md", "## Unreleased\n", "## Unreleased\n\n- Commented the runner.\n")
        _, errors = self.findings(base="HEAD", impact=impact)
        self.assertEqual(errors, [])

    def test_declared_impact_must_be_applied(self):
        _, errors = self.findings(base="HEAD", impact=[{"path": "README.md", "reason": "r", "status": "required"}])
        self.assertFinding(errors, "impact", "README.md")

    def test_new_document_requires_map_update(self):
        (self.repo / "docs/development/new-policy.md").write_text("# New\n")
        _, errors = self.findings(base="HEAD")
        self.assertFinding(errors, "doc-map")

    def test_protected_vocabulary_is_flagged_for_review(self):
        self.edit("agent-kit/README.md", "\n", "\nThe merge sort is PROVED correct.\n")
        res, warnings = self.findings(base="HEAD", severity="warning")
        self.assertFinding(warnings, "vocabulary", "agent-kit/README.md")


class CliAuditTests(unittest.TestCase):
    def test_cli_exit_status_reflects_result(self):
        proc = subprocess.run(["python3", "-m", "tools.weave_workflow", "docs-audit", "--json"], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:])
        self.assertEqual(json.loads(proc.stdout)["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
