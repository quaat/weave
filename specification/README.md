# Weave language specification

**Draft 0.2 · 28 October 2026**

A source-grounded specification of Weave's implemented functional Petri-net
language, with separate profiles for legacy nets, coloured nets, and the
process-crash reference model. New D0 waiting/identity semantics and N2
evidence/correlation design rules are explicit **unimplemented targets**. Proposed pure functions and fork/join are explicitly
outside the implemented profiles.

## Read

Build the HTML reference (below) and open `_build/html/index.html`. The editable
source is in `docs/`; the consolidated grammar is `grammar/weave.ebnf`.
Start with **Status and conformance**, then **Language overview**.
The status chapter's profile matrix names, for each profile (F0, N0, N1, R0 and
the targets D0 and N2), where it is specified, implemented and tested, and the
command that produces its evidence. **Claims, baseline and pinned identifiers**
(`docs/chapters/baseline.rst`) lists the public claims with their profile and
command, and the procedure that reproduces the baseline from a fresh clone.

## Build (Python 3.11+)

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m sphinx -n -W --keep-going -b html docs _build/html
```

On Windows, activate with `.venv\Scripts\activate` in Command Prompt.
Normal builds need no network access after dependency installation, except that
pages with equations load MathJax from a CDN when viewed.
`requirements.txt` pins the complete validated dependency set.

```bash
python -m sphinx -n -W -b singlehtml docs _build/singlehtml
python -m sphinx -n -W -b text docs _build/text
python -m sphinx -M latexpdf docs _build -n -W --keep-going   # PDF
python scripts/validate.py
python scripts/test_reference.py
python scripts/grammar_audit.py
python scripts/rule_coverage.py --check
python scripts/diagnostic_map.py
make validate
```

`make html`, `make singlehtml`, and `make latexpdf` build the reference. `make validate` runs
source, grammar, documentation, upstream tests, strict HTML, and external link
checks. `scripts/rule_coverage.py` regenerates `docs/chapters/rule-coverage.rst`
from `rules.json`, `examples/manifest.json` and `tests/rule-coverage.json`; its
`--check` mode runs in `make validate` through `tests/test_rule_coverage.py`.
`tests/test_diagnostics.py` runs the `scripts/diagnostic_map.py` check and one
diagnostic fixture per code. `make validate-offline` omits only the external linkcheck step.
`make.bat html` and `make.bat latexpdf` provide the Windows builds.

### PDF

The PDF (`_build/latex/weave-specification.pdf`) is typeset with XeLaTeX. On
Debian/Ubuntu:

```bash
sudo apt-get install -y make latexmk texlive-xetex texlive-latex-extra \
  texlive-fonts-recommended texlive-lang-english fonts-dejavu
```

LaTeX warnings are not fatal; inspect `_build/latex/weave-specification.log`
for missing glyphs, unresolved references, or overfull boxes.

## Presentation

HTML uses Furo with `sphinx-design`, `sphinx-copybutton`, and accessible
Pygments styles; the PDF uses `docs/_latex/weave.sty`. See
[`design/README.md`](design/README.md) for the design rationale and authoring
conventions for both formats, and `design/weave-design-specimen.pdf` for the
synthetic design specimen.

| Path | Purpose |
| --- | --- |
| `docs/conf.py` | Sphinx, HTML, PDF, validation, and provenance configuration |
| `docs/_static/weave.css` | Typography, components, responsive and print styles |
| `docs/_templates/` | Furo brand sidebar and provenance footer |
| `docs/_latex/weave.sty` | PDF cover, headings, running headers, spacing |
| `docs/_ext/` | Weave lexer, build-time `weave-check`, single-page repairs |
| `docs/_static/diagrams/` | SVG figures (HTML) with PDF companions (LaTeX); `make diagrams` regenerates both |

## Contents

- Lexical structure, EBNF, names, types, linearity, declarations, semantics,
  foreign outcomes, and verification contracts.
- Normative conformance cases, rule IDs, inference rules, generated grammar audit,
  and build-time `weave-check` tests of inline and included examples.
- A profile matrix, the public claims with their profile and supporting command,
  a generated rule-coverage page (a test or a pending-implementation entry for
  each rule ID), the source-to-model trust boundary, and a reproducible baseline
  with pinned identifiers and a proposed baseline tag.
- Three static diagrams, a lease tutorial, counterexample walkthroughs,
  protocol comparison, rationale, security, and documented design-history gaps.
- Syntax highlighting, searchable HTML, glossary, general index, and source links.
- Provenance, implementation discrepancies, open decisions, and validation results.
- A pinned reference prototype snapshot (`reference/prototype/`) for
  reproducible checks; `scripts/validate.py` verifies it against `PROVENANCE.json`,
  which also records its one reviewed refresh (quaat/weave#6, diagnostic spans).
- `diagnostics.json`, the machine-readable code-to-rule map; the diagnostics
  chapter's tables are generated from it by `scripts/refresh_reference_pages.py`,
  and `scripts/diagnostic_map.py` checks that every code the prototype and the
  agent kit can emit is mapped.

The primary source is `weave-inventory-proof.zip`, version 3. Teaching examples
originate in the older `weave-agent-kit.zip` and are rechecked against version 3.
Draft/profile identifiers are editorial identifiers, not upstream release numbers.

The Weave-authored specification sources and the Weave-authored portions of the
built editions, and the reference prototype snapshot, are released under the MIT
License; see [`LICENSE`](../LICENSE) at the repository root. The PDF cover and
the HTML footer print the same copyright line, from the `copyright` setting in
`docs/conf.py`. Third-party material, including theme code and fonts embedded in
PDF files, keeps its own copyright and terms. [`REUSE.toml`](../REUSE.toml)
records licensing per path, including the fonts embedded in the committed PDFs.
The "Third-party notices" section of `docs/chapters/provenance.rst` lists the
third-party material in each edition with its licence texts, and
[`follow-up`](../follow-up) lists the remaining release items.
