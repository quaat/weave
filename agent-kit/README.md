# Weave agent starter kit

A self-contained starting point for teaching Codex or Claude Code the currently
implemented Weave fragment: language guidance, accepted and rejected examples,
and a portable skill containing the existing prototype and a small CLI.

The source snapshot is `weave-inventory-proof.zip`, version 3, saved on
2026-10-28. It includes `?` lowering, runtime consumer sealing, rejection-evidence
checks, and scripted single-order execution. Version 3 also bundles coloured nets
(`coloured.py`) and a process-crash reference model (`durable.py`). The runner
does not expose them yet; see `docs/prototype-status.md`. This kit adds packaging and tooling,
plus one explicitly separate extension: pure `fn` programs with integer lists,
direct recursion, and a cooperative fork/join scheduler (`check-pure`/`run-pure`,
implemented outside the vendored prototype, which it does not modify). See
`docs/prototype-status.md` for limitations. That extension and its `merge_sort` demo
are not the specified language and do not complete the concurrent fork/join merge-sort
brief (`claude-code-weave-merge-sort.md`), which is quaat/weave#42 (M6). Specified
sequential merge sort is a P0 conformance application, run with the repository's
`weave` command rather than this kit (quaat/weave#11).

## Start

Extract the ZIP and enter `weave-agent-kit`. Use Python 3.11 or newer;
CPython **3.12.14** is the tested reference version in `.python-version`.
No `pip install`, network access, API key, container, or third-party package is
required. On systems where Python is named `python`, replace `python3` below.

```bash
python3 scripts/weave.py doctor
python3 scripts/weave.py examples
python3 scripts/weave.py check examples/valid/checkout_propagating.weave
python3 scripts/weave.py simulate examples/valid/checkout_propagating.weave --entry checkout_propagating --outcome all
```

The simulator uses symbolic scalar parameters and one scripted foreign reply.
It does not contact a payment provider or start a durable/asynchronous runtime.

Every claim the runner prints carries one of the result labels of the specification,
which has seven. The runner emits six of them (`PROVED`, `CHECKED WITHIN BOUNDS`,
`CHECKED flow`, `SCRIPTED / passed scenario`, `VIOLATED`, `NOT ESTABLISHED`), as a
`LABEL statement` line or a JSON `claim_label`; the seventh, `CHECKED pure`, is stated
only by the P0 `weave` command (quaat/weave#10), and the kit's label lint accepts all seven.
Tool status and the runtime status of a run are reported separately and are not
evidence; see `docs/commands.md`. `tests/test_result_labels.py` lints the output of
every command for this.

## Use with an agent

Open the extracted folder as the working project in Codex or Claude Code.
`AGENTS.md` is the shared guidance; `CLAUDE.md` imports it for Claude Code.

- Codex skill: `.agents/skills/weave/`.
- Claude Code adapter: `.claude/skills/weave/SKILL.md`, which points to the same
  canonical skill and bundled implementation.
- Start with a task such as: “Use the weave skill to check
  `examples/valid/checkout_propagating.weave` and simulate all three outcomes.”

This ZIP does not install a personal skill in ChatGPT. To reuse the skill in
another repository, copy the entire `.agents/skills/weave/` directory to that
repository's `.agents/skills/weave/` for Codex, or to `.claude/skills/weave/` for
Claude Code. The canonical skill is self-contained. Its runner works by absolute
path from any current directory. Supply your flow path and optionally `--net`.
The standalone `examples` command needs `--manifest` pointing to this kit's
teaching manifest; `test` always runs the bundled prototype's regressions.

When integrating into an existing project, merge the relevant `AGENTS.md` rules
and `CLAUDE.md` import instead of replacing existing instructions. The kit
contains hidden `.agents` and `.claude` directories; include them when copying.

## Contents

| Path | Purpose |
| --- | --- |
| `AGENTS.md`, `CLAUDE.md` | Shared agent entry points |
| `docs/weave.md` | Implemented syntax, semantics, and examples |
| `docs/commands.md` | CLI options, outputs, and exit codes |
| `docs/prototype-status.md` | Guarantees and explicit exclusions |
| `examples/` | Teaching fixtures and machine-readable expectations |
| `scripts/weave.py` | Short repository command |
| `.agents/skills/weave/` | Canonical portable skill, runner, guide, and prototype |
| `.claude/skills/weave/` | Repository-local adapter to the canonical skill |
| `tests/` | Packaging/CLI regressions, the result-label lint, and pure-extension tests |
| `demos/` | Applications: `tiny_shop` (flows) and `merge_sort` (pure extension) |
| `docs/validation.md` | Validation performed for this release |
| `PROVENANCE.json` | Exact input identity and prototype file integrity records |

## Check changes

```bash
python3 scripts/weave.py examples
python3 scripts/weave.py test
python3 -B -m unittest discover -s tests -q
```

For a focused prototype test module:

```bash
python3 scripts/weave.py test --pattern test_rejection_and_propagation.py
```

Only explicit output options write files. For example:

```bash
python3 scripts/weave.py lower examples/valid/checkout_propagating.weave --output lowered.weave
python3 scripts/weave.py analyze --certificate proof.json
python3 scripts/weave.py verify proof.json
```

Keep the portable guide synchronized after editing `docs/weave.md`:

```bash
python3 scripts/sync_skill_reference.py
```

This package reduces repeated setup, implementation reading, and success-output
volume. No model-token or monetary savings have been measured. Net checks are
reused within a batch; there is no persistent cache that could become stale.
