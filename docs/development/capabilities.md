# Installed capabilities and known gaps

Observed on 2026-10-28 during bootstrap on the maintainer's workstation. Re-check with
`python3 -m tools.weave_workflow capabilities`; installed behaviour is authoritative over
anything remembered or documented elsewhere.

## Versions

| Tool | Observed | Notes |
| --- | --- | --- |
| Claude Code | 2.1.312 | `~/.local/bin/claude` |
| GitHub CLI | 2.103.2 | `gh api --paginate --slurp` supported |
| Codex CLI | codex-cli 0.162.1 first on the maintainer's `PATH` (`~/.nvm/versions/node/v25.9.0/bin/codex`); codex-cli 0.139.0 also installed at `/usr/local/bin/codex` | Both support `codex exec --sandbox read-only`, `--ephemeral`, `--output-schema`, `-o`, `--json`, `-C`, `-c`. The version actually used is recorded as provenance on every review |
| Python | 3.13.5 | workflow tooling targets 3.11+; standard library only |
| Rust | cargo 1.89.0, rustc 1.89.0, rustup 1.29.1 | in `~/.cargo/bin`, not on the default `PATH`; `cargo-clippy` and `cargo-audit` installed. 1.89.0 is the channel pinned in `rust-toolchain.toml` (issue #9); the workspace builds offline because its four crates (`weave-syntax`, `weave-check`, `weave-eval`, `weave-cli`) have no third-party dependencies. Worker sandboxes cannot read `~/.cargo/bin`, so cargo runs outside the sandbox, and a `make validate-offline` without `cargo` on `PATH` records both Rust comparisons, the grammar audit's and the P0 differential's, as not established |
| autonomous-development | not installed as a Claude Code plugin | see below |

## Verified

| Capability | How it was verified |
| --- | --- |
| Codex structured output | Live contract test with codex-cli 0.162.1: `codex exec --sandbox read-only --ephemeral -c mcp_servers={} --output-schema tools/weave_workflow/schemas/review-result.v1.schema.json --json` returned a schema-valid object; the JSONL stream carried `thread.started` with a thread id (used as session provenance). Codex accepts `pattern` and `enum` in the schema |
| Codex has no MCP servers configured | `codex mcp list`; the reviewer additionally runs with `-c mcp_servers={}` |
| GitHub GraphQL dependency fields | `Issue.blockedBy`, `Issue.blocking`, `Issue.subIssues`, `Issue.parent` and `stateReason` return data for `quaat/weave` |
| Hook events in the installed Claude Code | The 2.1.312 binary contains `SessionStart`, `SessionEnd`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `SubagentStart`, `SubagentStop`, `Stop`, `PreCompact`, and the output fields `hookSpecificOutput`, `permissionDecision`, `permissionDecisionReason`, `updatedInput`, `additionalContext`, `stop_hook_active` |
| Issues and milestones | Live read: 60 issues (#2–#61), 7 open milestones M0–M6, one pull request; no native blocked-by or sub-issue relationships yet |
| Branch protection | `main` is not protected (HTTP 404 from the protection endpoint) |
| Project board (Projects v2 #3) | After `gh auth refresh -s project` (2026-10-28): project "Weave" `PVT_kwHOAAi_6c4BpKJl`, Status field `PVTSSF_lAHOAAi_6c4BpKJlzhnnAgg`, options Todo `f75ad846`, In Progress `47fc9ee4`, In Review `22ef89ec`, Done `98236657`; no missing or extra options; all 61 open issues are on the board. IDs are rediscovered on every run, never hard-coded |

## Not verified or unavailable

| Capability | Status | Consequence and remedy |
| --- | --- | --- |
| Built-in project automations | Not readable through the API. Observed effect: bootstrap issue #62 was added to the board and set to In Progress without any workflow write, so automations are active | Inspect the project's workflow settings by hand. The "item closed → Done" move after a merged PR from the claim's branch is recognised and recorded through the Done gate ([transitions.md](transitions.md)); disable any other rule that moves items to Done or In Review automatically. `reconcile` reports every other status change it did not record as a conflict |
| `agent_type` in subagent `PreToolUse` payloads, and `updatedInput` being honoured | **Unverified live.** A headless probe session was refused by the session's permission classifier | Worker guards depend on it. The evidence hooks log payload key names during a run, so the first real run verifies it; until then treat worker credential removal as best effort |
| autonomous-development controller | Not installed as a plugin (`~/.claude/plugins/installed_plugins.json` lists codex, duckdb-skills, example-skills, document-skills and agent-sparring). A local checkout of v0.3.0 exists outside this repository | The review gate uses the built-in `codex exec` adapter, which follows the same principles (fresh read-only Codex, schema-validated output, fail-closed gates). Installing the plugin and mapping its review gate is a follow-up, not a second controller |
| Codex ChatGPT login refresh | Codex logged `invalid_refresh_token` errors, but the configured provider still answered | Run `codex login` if reviews start failing with authentication errors |
| End-to-end run | Not performed | No real Codex review of a task and no authorised board transition have run; the offline suite covers the scenarios with fake adapters |
| File conflicts between concurrent issues | Declared allowed paths only | `claim` refuses a task whose allowed paths may overlap those of another held claim, In Progress or In Review ([scheduling.md](scheduling.md)). Worker edits are confined to allowed paths only when the run records a delegation's `allowed_paths` for the hook, and the diffs of concurrent branches are not compared with each other, so integration can still meet merge conflicts |
| Multi-host coordinator exclusivity | Not provided | Single-host OS lock only; see [github-adapter.md](github-adapter.md) |
| OS-level worker isolation | Not provided | Subagents share the coordinator's user and keyring; see [roles.md](roles.md) |
| `gh` `workflow` scope | Absent | Pushes that touch `.github/workflows/` go over SSH |
