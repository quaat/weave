# Weave

[![CI](https://github.com/quaat/weave/actions/workflows/ci.yml/badge.svg)](https://github.com/quaat/weave/actions/workflows/ci.yml)
[![Specification site](https://github.com/quaat/weave/actions/workflows/docs.yml/badge.svg)](https://github.com/quaat/weave/actions/workflows/docs.yml)

**Specification:** [HTML](https://quaat.github.io/weave/) ·
[PDF](https://quaat.github.io/weave/weave-specification.pdf)

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

## Continuous integration

| Workflow | Runs on | What it does |
| --- | --- | --- |
| [`ci.yml`](.github/workflows/ci.yml) | Pushes to `main`, pull requests | `inventory-proof`: unit tests, checks that `demo.py` regenerates the committed outputs, runs `durable.py` (Python 3.11–3.13). `agent-kit`: `doctor`, kit tests, example expectations, bundled prototype suite, and demo tests (Python 3.11–3.13). `specification`: `make validate-offline`, single-page and text builds, HTML link audit |
| [`docs.yml`](.github/workflows/docs.yml) | Pushes to `main`; pull requests that touch `specification/` | Builds the HTML site and the XeLaTeX PDF. The PDF is uploaded as a build artifact. On `main` the site, with the PDF, is deployed to GitHub Pages |

External link checking (`make linkcheck`) needs network access to many hosts,
so CI doesn't run it; run it locally before a release.

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
