# Conventions

- **Branches:** `agent/<issue-number>-<short-slug>`, created by `claim --apply` in a worktree
  under `.worktrees/`.
- **Commits:** imperative subject under 72 characters; the body states the issue, the
  criteria addressed (`AC-n`) and the documents updated. No "fix" commits that silently
  alter previously reviewed evidence: any change after a review request moves the candidate
  head and requires a fresh review.
- **Pull requests:** scope; the criteria matrix (criterion → location → check → result →
  evidence → documentation); checks run with results; documentation impact and audit
  result; limitations; a link to the issue's summary comment.
- **Merges:** by the maintainer. The coordinator never merges unless the policy explicitly
  delegates it (`merge.delegated_to_coordinator`).
- **Tags and releases:** maintainer only (for example the baseline tag in #4).
- **Bootstrap:** the workflow itself was introduced on an isolated feature branch with a
  bootstrap issue and pull request; it does not reorder M0–M6 or mark any product task Done.
