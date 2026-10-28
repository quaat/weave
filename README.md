# Weave

Weave is an experimental, purely functional language that combines Petri nets
with nominal, linear flows. It aims at correctness, distributability,
parallelism, and fail safety. This repository holds the language's draft
specification, its proof-of-concept implementation, and a kit for agentic
coding with Weave.

| Directory | What it is | Entry point |
| --- | --- | --- |
| [`specification/`](specification/) | Sphinx project for the language specification (Draft 0.2): HTML via Furo, PDF via XeLaTeX, executable examples checked at build time | [`specification/README.md`](specification/README.md) |
| [`inventory-proof/`](inventory-proof/) | Proof-of-concept implementation (prototype v3): net parser, ownership validator, P-invariant prover, bounded order explorer, linear flow checker, scripted executor, coloured nets, and a process-crash reference model | [`inventory-proof/REPORT.md`](inventory-proof/REPORT.md) |
| [`agent-kit/`](agent-kit/) | Starter kit for Codex / Claude Code: `AGENTS.md`, a portable `weave` skill with a vendored prototype and CLI, examples, and demos (tiny shop, merge sort) | [`agent-kit/README.md`](agent-kit/README.md) |

Each project is self-contained, with its own README, tests, and requirements.
Run commands from inside the project's directory.

## Quick start

All three need Python 3.11 or newer. Only the specification has third-party
dependencies.

```bash
# Proof of concept (standard library only)
cd inventory-proof
python3 demo.py
python3 -m unittest discover -s tests -v

# Agent kit (standard library only)
cd agent-kit
python3 scripts/weave.py doctor
python3 -m unittest discover -s tests

# Specification
cd specification
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements.txt
make html              # _build/html/index.html
make latexpdf          # _build/latex/weave-specification.pdf (needs XeLaTeX + latexmk)
make validate-offline  # examples, grammar audit, tests, strict HTML build, link audit
```

## Prototype versions

The prototype exists in three places. Keep them as they are unless you also
update the recorded hashes.

| Location | Prototype version | Pinned by |
| --- | --- | --- |
| `inventory-proof/` | v3, the working copy for further development | Started byte-identical to the specification snapshot |
| `agent-kit/.agents/skills/weave/assets/prototype/` | v3, unchanged; the pure `fn` extension lives beside it in `scripts/weave_pure/` | `agent-kit/PROVENANCE.json` |
| `specification/reference/prototype/` | v3 (adds coloured nets `coloured.py` and the process-crash model `durable.py`) | `specification/PROVENANCE.json`, checked by `scripts/validate.py` |

The specification is grounded in v3. Changes made in `inventory-proof/` reach
the specification only when someone deliberately refreshes its snapshot and
`PROVENANCE.json`. The agent kit bundles the same v3 snapshot, but its runner
uses only the uncoloured checker and simulator.

## Status and license

This is research-stage work. It has no distributed runtime and no general
compiler, and the specification marks its unimplemented design targets
explicitly. No license has been chosen yet; choose distribution terms before
any public release.
