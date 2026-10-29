"""Dry-run report: field mappings, milestone graph, eligibility, blockers, proposed
operations, documentation audit and unverified capabilities. Performs no remote writes."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import docs_audit
from .capabilities import inspect
from .reconcile import reconcile
from .scheduler import plan as make_plan
from .state import Store, utcnow


def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def dry_run_report(repo: Path, store: Store, adapter, policy: dict, run_audit: bool = True) -> str:
    from .cli import active_claims, gate_events, held_claims
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    caps = inspect(repo)
    snap = adapter.snapshot()
    p = make_plan(snap, policy, gate_events(store, snap, policy), active_claims(store), sorted(held_claims(store)))
    L = [f"# Weave workflow dry-run report", "",
         f"Generated {utcnow()} at `{head[:12]}` with policy version {policy['policy_version']}. "
         "No remote writes were performed.", ""]
    L += ["## Tools and permissions", "", "| Item | Observed |", "| --- | --- |"]
    for key in ("claude_code", "gh", "gh_scopes", "gh_project_scope", "gh_project_write_scope", "gh_workflow_scope",
                "codex", "codex_login", "codex_exec_output_schema", "autonomous_development_installed", "cargo", "rustc", "python"):
        L.append(f"| `{key}` | {_md_cell(caps.get(key))} |")
    L += ["", "## Project field mapping", ""]
    if snap.project:
        pr = snap.project
        L += [f"- Project: {pr.title} (`{pr.project_id}`)", f"- Status field: `{pr.status_field_id}`"]
        for name in policy["project"]["status_options"]:
            L.append(f"  - {name}: `{pr.options.get(name, 'MISSING')}`")
        extra = [o for o in pr.options if o not in policy["project"]["status_options"]]
        if extra:
            L.append(f"- Unexpected Status options (left untouched): {extra}")
        on_board = set(pr.items)
        missing = sorted(n for n, i in snap.issues.items() if i.state == "open" and n not in on_board)
        L.append(f"- Issues on the board: {len(on_board)}; open issues not on the board: {missing or 'none'}")
    else:
        L.append(f"**Unavailable:** {snap.project_error}. Status IDs are not guessed; transitions stay blocked until the "
                 "token has the `project` scope (`gh auth refresh -s project`).")
    L += ["", "## Milestone graph", "",
          "| Key | GitHub milestone | Epic | Requires | Open/closed tasks | Exit gate | First reasons |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    by_key = {m.key: m for m in snap.milestones if m.key}
    for key in p.milestone_order:
        spec = policy["milestones"][key]
        m = by_key.get(key)
        members = [i for i in snap.issues.values() if i.milestone_key == key and "epic" not in i.labels]
        open_n = sum(i.state == "open" for i in members)
        g = p.gates[key]
        L.append(f"| {key} | {f'#{m.number} {m.title}' if m else 'missing'} | #{spec['epic']} | "
                 f"{', '.join(spec['requires']) or 'Start'} | {open_n}/{len(members) - open_n} | "
                 f"{'passed' if g.passed else 'not passed'} | {_md_cell('; '.join(g.reasons[:2]))} |")
    L += ["", "### Blocking dependencies", ""]
    for e in sorted(p.graph.edges.values(), key=lambda e: (e.blocked, e.blocker)):
        L.append(f"- #{e.blocked} is blocked by #{e.blocker} — {'; '.join(e.provenance)}")
    if not p.graph.edges:
        L.append("- none recorded")
    L += ["", "### Graph findings", ""] + ([f"- {f}" for f in p.graph.findings] or ["- none (no cycles or contradictions)"])
    ctx = sorted(p.graph.contextual.items())
    L += ["", f"Contextual mentions (not blocking) were found on {len(ctx)} issues; they are listed by `plan --json` for maintainer review."]
    L += ["", f"## Scheduling: current milestone {p.current or '-'}", "",
          "| Issue | Eligible | Work type | Reasons | Notes |", "| --- | --- | --- | --- | --- |"]
    for c in sorted(p.candidates, key=lambda c: c.sequence):
        L.append(f"| #{c.issue} {_md_cell(c.title[:60])} | {'yes' if c.eligible else 'no'} | {c.work_type} | "
                 f"{_md_cell('; '.join(c.reasons)) or '-'} | {_md_cell('; '.join(c.notes)) or '-'} |")
    L += ["", f"**Next task:** {f'#{p.next.issue} {p.next.title}' if p.next else 'none'}"
          + (f" — stop reason: {p.stop_reason}" if p.stop_reason else ""), ""]
    if p.provisional_next:
        L += [f"**Provisional next task** (once the board is readable and confirms Todo): "
              f"#{p.provisional_next.issue} {p.provisional_next.title} ({p.provisional_next.work_type})", ""]
    shown = p.next or p.provisional_next
    if shown:
        L += ["Proposed operations (not performed):", "",
              f"1. `python3 -m tools.weave_workflow claim {shown.issue}` (dry run), then with `--apply`: acquire the coordinator lock; publish CLAIMED, DOCS_IMPACT and PLAN on #{shown.issue}; create worktree and branch `agent/{shown.issue}-<slug>`; transition Todo → In Progress through the gate.",
              "2. Delegate implementation with the validated task packet; publish DELEGATED before work starts.",
              "3. Verify, run the change-scope documentation audit, local and safety reviews, then `review --apply` for the independent Codex review.",
              ""]
    L += [f"- Active implementation issues: {p.active or 'none'}",
          f"- Unscheduled (no milestone; reported, not assigned): {', '.join(f'#{n}' for n in p.unscheduled) or 'none'}",
          f"- Deferred (excluded unless activated): {', '.join(f'#{n}' for n in p.deferred) or 'none'}"]
    for req in policy.get("cross_milestone_requirements", []):
        L.append(f"- #{req['issue']} is owned by {req['owner_milestone']} and required by the {req['required_by']} exit gate (scheduled once)")
    for exc in policy.get("early_start_exceptions", []):
        L.append(f"- Early-start exception for {', '.join(f'#{n}' for n in exc['issues'])}: {exc['allowed_scope']} "
                 f"({'active' if policy.get('early_start_exceptions_active') else 'inactive'}; source: {exc['source']})")
    for d in policy.get("decision_tasks", []):
        L.append(f"- #{d['issue']} is a decision task: {d['decision']}; Done needs the maintainer's recorded decision")
    for a in policy.get("maintainer_actions", []):
        L.append(f"- #{a['issue']} needs maintainer action: {a['action']}")
    if run_audit:
        res = docs_audit.audit(repo)
        L += ["", "## Documentation audit (whole repository)", "",
              f"Result **{res.result}**: " + ", ".join(f"{k}={v}" for k, v in res.counts.items()), ""]
        L += [f"- {f.severity}: [{f.check}] `{f.path}` — {f.message}" for f in res.findings] or ["- no residual drift"]
    rec = reconcile(repo, store, adapter, policy, apply=False)
    L += ["", "## Reconciliation (read-only)", "",
          f"- Pending outbox messages: {rec['outbox_pending']}",
          f"- Active claims: {rec['claims'] or 'none'}",
          f"- Conflicts: {rec['conflicts'] or 'none'}",
          f"- Rejected envelopes: {len(rec['rejected_envelopes'])}",
          f"- Agent worktrees: {rec['worktrees'] or 'none'}"]
    L += ["", "## Unverified capabilities and manual prerequisites", ""]
    gaps = []
    if not caps.get("gh_project_scope"):
        gaps.append("The gh token lacks `project` scope: board fields, item IDs and Status cannot be read or written. Run `gh auth refresh -s project`.")
    if snap.branch_protection is None:
        gaps.append("`main` has no branch protection: required checks and human reviews are not enforced by GitHub. Configure protection (maintainer action).")
    if set(policy["actors"]["coordinator_logins"]) & set(policy["actors"]["maintainer_logins"]):
        gaps.append("The coordinator posts with the maintainer's account; maintainer decisions are told apart only by the `/weave-decision` form and the ledger. A dedicated bot account or GitHub App is recommended.")
    if not caps.get("autonomous_development_installed"):
        gaps.append("`autonomous-development` is not installed as a Claude Code plugin; the review gate uses the built-in `codex exec` adapter.")
    gaps.append("Subagents share the coordinator's process and keyring; hooks scrub GitHub and SSH credentials from worker shells, but this is not an OS-level boundary.")
    gaps.append("No end-to-end run has been performed: no real Codex review of a task and no authorised transition have run.")
    L += [f"- {g}" for g in gaps]
    return "\n".join(L) + "\n"
