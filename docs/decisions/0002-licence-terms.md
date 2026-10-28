# 0002: Licence terms for implementation, specification and assets

- **Status:** Proposed (awaiting maintainer decision)
- **Issue:** [quaat/weave#2](https://github.com/quaat/weave/issues/2), milestone M0
- **Prepared against:** base revision `6564a0399f10cea02a7274a9e67ce98efd75af14`, 28 October 2026
- **Decision owner:** the maintainer. This document proposes; it does not decide.

This is a decision-preparation record. It assesses the current state against each acceptance
criterion of #2, lists the rights questions that only the maintainer can answer, and gives
draft decision text. It changes no licence file, licence statement, SPDX identifier, build
configuration, provenance record or pinned snapshot, and it does not tick any criterion.

## Summary and assumed terms

Following the maintainer's direction, this proposal assumes **one licence, the MIT License,
for everything distributed from this repository**:

- code: the prototype working copy, the vendored and reference prototype snapshots, the agent
  kit, the specification's build scripts and Sphinx extensions, and the workflow tooling;
- specification text: the Sphinx sources and the built editions (multi-page HTML,
  single-page HTML and PDF);
- examples: every Weave program (`*.weave`) and teaching or demo material;
- distributed assets: diagrams, the favicon, the design specimen PDF and generated reports.

Whether MIT is right, and who the rights holders are, is the maintainer's choice to confirm.

The repository already carries these terms. Commit `2faeef8` ("Add MIT license and expand the
README") added an MIT `LICENSE` at the root and replaced the earlier "no licence" notes in
`README.md`, `specification/README.md`, `specification/docs/chapters/provenance.rst`,
`agent-kit/docs/prototype-status.md` and the `copyright` string in
`specification/docs/conf.py`. The Context paragraph of #2, which describes the material as
having no licence granted, predates that commit and is out of date. What #2 still needs is
the maintainer's recorded decision and confirmation of rights holders (AC-1), plus the
remaining per-file and PDF work (AC-3, AC-5).

## AC-1 Provenance and rights holders

### What the records show

**Git history.** The base revision has 18 commits, all dated 28 October 2026. Every commit was
authored under one of two Git identities that carry the same personal name as the copyright
line in `LICENSE`: 15 were authored locally, and 3 were created through the GitHub web
interface (two pull-request merges and one workflow file that is no longer tracked). No other
human author or committer appears. 14 of the 18 commit messages carry a `Co-Authored-By`
trailer naming an AI coding assistant; this includes every commit touching `inventory-proof/`,
`agent-kit/`, `specification/`, `tools/weave_workflow/`, `docs/development/`, `.claude/`,
`LICENSE` and `README.md`, and 6 of the 8 commits touching `.github/`. The first commit
(`2e0e7fe`) imported the specification, the prototype and the agent kit together, so Git
history starts at the import and does not show who wrote the imported material before it.

**Provenance manifests.** `specification/PROVENANCE.json` lists four inputs under `sources`,
each identified only by file name, a library file identifier, a version (or none) and a
SHA-256 digest. There is no author, rights-holder or licence field:

| Input | Version | Role (from `specification/docs/chapters/provenance.rst`) | Where it is used |
| --- | --- | --- | --- |
| weave-inventory-proof.zip | 3 | Primary implementation baseline | `specification/reference/prototype/`, vendored into `agent-kit/.agents/skills/weave/assets/prototype/`; `inventory-proof/` started byte-identical |
| weave-agent-kit.zip | none recorded | Older teaching guide, examples, manifest, runner conventions | `agent-kit/`, teaching examples in `specification/examples/` |
| claude-code-weave-merge-sort.md | none recorded | Proposed pure-function and fork/join task | No record says; its subject matches `agent-kit/demos/merge_sort/` and the kit's pure-function extension |
| claude-code-tiny-shop.md | none recorded | Application brief | No record says; its subject matches `agent-kit/demos/tiny_shop/` |

`agent-kit/PROVENANCE.json` records `kit_version` 0.1.0, the same prototype archive as its
`source` (same digest), per-file digests of the vendored snapshot, one kit-authored extension
(`agent-kit/.agents/skills/weave/scripts/weave_pure/`, marked as not part of the upstream
snapshot) and the snapshot history. It has no author or rights-holder field either.

The design bundle described in `specification/design/README.md` (Furo theme configuration,
templates, LaTeX style and `specification/design/weave-design-specimen.pdf`) was integrated in
the first commit. It is not listed as a source in either manifest.

### Inventory of distributed sources

| Source | Files at base | What the records show |
| --- | --- | --- |
| `inventory-proof/` (prototype working copy, reports, nets) | 39 | Derived from the v3 archive; edited in 2 commits; no licence text of its own |
| `agent-kit/` (kit, runner, skill, docs, examples, demos) | 126 | Derived from weave-agent-kit.zip and the v3 archive; edited in 4 commits; `agent-kit/CHANGELOG.md` records the MIT statement |
| `agent-kit/.agents/skills/weave/assets/prototype/` (vendored snapshot, pinned) | 39 | Byte-identical to the v3 archive per `agent-kit/PROVENANCE.json`; contains no licence or copyright text |
| `agent-kit/examples/` and `agent-kit/demos/` | 34 and 23 | Examples from weave-agent-kit.zip per `specification/docs/chapters/provenance.rst`; no record states who wrote the demos |
| `specification/` (Sphinx sources, rules, Makefile) | 154 | Imported in the first commit, edited in 7 commits |
| `specification/reference/prototype/` (reference snapshot, pinned) | 39 | Original bytes of the v3 archive per `specification/PROVENANCE.json`; contains no licence or copyright text |
| `specification/scripts/` and `specification/docs/_ext/` | 8 and 3 | Build and validation scripts and Sphinx extensions; no separate record |
| `specification/examples/` and other `*.weave` programs | 32 files in the directory; 114 `*.weave` files in the repository | Teaching examples from weave-agent-kit.zip, rechecked against v3 |
| `specification/grammar/` | 2 | Grammar sources; no separate record |
| Design assets: `specification/design/weave-design-specimen.pdf`, `specification/docs/_static/diagrams/`, `specification/docs/_static/weave-favicon.svg`, `specification/docs/_latex/weave.sty`, templates | 1 PDF, 6 diagram files, 1 favicon | Specimen PDF metadata names "Danio project" as author; diagrams are drawn by `specification/scripts/render_diagrams.py` and converted by `specification/scripts/diagrams_to_pdf.py` |
| Generated reports and recorded outputs: `inventory-proof/REPORT.md` and the other files `demo.py` writes, `specification/validation/` | 16 in `specification/validation/` | Outputs of the repository's own scripts and builds |
| Built editions (HTML, single page, PDF) | not tracked | Produced by CI; include theme and Sphinx static assets from pinned dependencies |
| `tools/weave_workflow/` and `docs/development/` | 32 and 14 | Created in the workflow bootstrap (`4804662`) and later commits |
| `.claude/` and `.github/` | 12 and 4 | Agent configuration and CI workflows |

Third-party material that is or may be distributed:

- `specification/design/weave-design-specimen.pdf` embeds subsets of the DejaVu font family and
  of Computer Modern; each diagram PDF in `specification/docs/_static/diagrams/` embeds a subset
  of DejaVu Sans (measured with `pdffonts`, below). No font files are tracked.
- The built PDF is set in DejaVu fonts (`specification/docs/conf.py`), so it embeds them too.
- The built HTML editions contain the Furo theme's and Sphinx's static files. The dependencies
  are pinned in `specification/requirements.txt` and not vendored in the repository;
  `inventory-proof/requirements.txt` lists none. MathJax loads from a CDN and is not
  distributed (`specification/design/README.md`).

### Open rights questions for the maintainer

These are questions, not findings. This proposal does not answer them.

1. Who authored or generated each of the four inputs in `specification/PROVENANCE.json`
   (weave-inventory-proof.zip v3, weave-agent-kit.zip, claude-code-weave-merge-sort.md,
   claude-code-tiny-shop.md), and under what terms were they obtained?
2. Who authored the design bundle (theme configuration, templates, LaTeX style, design
   specimen PDF), and is it covered by the same answer?
3. Does any employer, funder, institution or contract hold rights in any part of the work,
   or impose terms on its publication?
4. Does the copyright line in `LICENSE` name the correct holder or holders for all of the
   material above?
5. The specification's `author` setting, the PDF cover and the design specimen's metadata name
   "Danio project", while the copyright line names an individual. Which name should appear as
   author and which as copyright holder?
6. Is any third-party material distributed beyond what is listed above (fonts embedded in
   PDFs, theme assets in built editions, quoted text, diagrams or code adapted from elsewhere),
   and does any of it need its own notice?
7. Most commits carry an AI co-author trailer. Does the maintainer want the decision to say
   anything about AI-assisted contributions?
8. Should future contributions be accepted under the same terms by stating so (as
   `README.md` does now), or by another mechanism such as a sign-off requirement?

## AC-2 LICENSE

**Current state.** `LICENSE` exists at the repository root and contains the standard MIT
License text with one copyright line for 2026. It was added in `2faeef8`. No other licence
file is tracked (command D below).

**Assessment under the assumed terms.** If MIT covers code and prose alike, one `LICENSE`
satisfies AC-2 and no `LICENSE-docs` is needed. Trade-off, for the record only: applying MIT to
specification prose is legally workable but unusual, and Creative Commons Attribution 4.0
(CC BY 4.0) is the common alternative for documentation. The maintainer chose MIT, so this
proposal does not recommend a change.

**Follow-up.** Once the decision is recorded, confirm or correct the copyright line in
`LICENSE` according to the answers to questions 4 and 5.

## AC-3 SPDX identifiers or per-directory statement

**Measured state.** No tracked file contains an SPDX identifier, and no file in the worktree
does outside `_build`, `_site` and `.git`. There is no REUSE metadata. The only per-directory
statements are prose sentences in `specification/README.md` and
`agent-kit/docs/prototype-status.md`. `inventory-proof/` has no statement of its own; the
root `README.md` says the licence covers the whole repository.

**Recommended follow-up** (separate implementation issue, after the decision is recorded).
Options, not mutually exclusive:

1. **SPDX headers in authored source files.** Add `SPDX-License-Identifier: MIT` and an
   `SPDX-FileCopyrightText` line to Python, Sphinx extension, LaTeX style, CSS, template and
   workflow files written in this repository. Do not add headers to files whose bytes are
   pinned or regenerated: the pinned snapshots, generated reports and the documentation map's
   generated section.
2. **Per-directory statements.** A short licence paragraph in each component README
   (`inventory-proof/`, `agent-kit/`, `specification/`, `tools/weave_workflow/`) naming the
   terms and pointing to `LICENSE`. This covers examples, diagrams and other assets that
   cannot carry a header.
3. **REUSE-style metadata.** A single REUSE.toml file (or the older dep5 file) at the root
   that assigns licence and copyright by path pattern, with the licence text in a LICENSES
   directory. This is how the pinned snapshots
   (`specification/reference/prototype/`, `agent-kit/.agents/skills/weave/assets/prototype/`)
   and binary assets can be covered without changing their bytes, which keeps both
   `PROVENANCE.json` manifests and the documentation audit's hash checks valid.

Whichever option is chosen, the pinned snapshots must keep their original bytes; any statement
about them lives outside the snapshot directories.

## AC-4 "No licence" statements

**Measured state.** No tracked file outside the pinned snapshots contains a "no licence" style
statement, and neither pinned snapshot does (commands E and F below). The same search run at
the parent of `2faeef8` finds six such lines, in `README.md`,
`agent-kit/docs/prototype-status.md`, `specification/README.md`,
`specification/docs/chapters/provenance.rst` (two lines) and `specification/docs/conf.py`, so
the pattern does detect the earlier wording and `2faeef8` removed it.

`specification/docs/conf.py` currently sets:

```python
author = "Danio project"
copyright = "2026, Thomas F. Hagelien. MIT License"
```

**Follow-up.** None for removal. If the answers to questions 4 and 5 change the holder, update
`LICENSE`, the licence sections of `README.md` and `specification/docs/chapters/provenance.rst`,
and the `copyright` string together.

## AC-5 Specification footer and PDF cover

**HTML footer.** `specification/docs/_templates/page.html` extends the theme footer
(`super()`), which prints the `copyright` setting, and adds the reference-snapshot digest. A
local HTML build in the main checkout made after `2faeef8` shows
"Copyright © 2026, Thomas F. Hagelien. MIT License" in the footer; an older local single-page
build made before `2faeef8` still shows the former "distribution terms not specified" string.
The HTML footer therefore follows `conf.py` and will reflect the terms after any rebuild. The
published site was not checked (no network access during preparation).

**PDF cover.** `specification/docs/_latex/weave.sty` defines the cover (`\weavemaketitle`): the
label "DANIO PROJECT", the title, the tagline, the release, the `author` setting
("Danio project") and the reference-snapshot digest. It shows **no copyright or licence
line**, and the PDF has no copyright page. The running footer reads "Weave / Draft
specification" and the page number. PDF metadata takes its author from the same setting. In
the PDF, the terms appear only in the body, in the "Distribution status" section built from
`specification/docs/chapters/provenance.rst`. No built PDF was available to inspect; this
assessment comes from the style file and `conf.py`.

**Follow-up.** Add a copyright and licence line to the PDF cover, or a short colophon page
after it, driven from the `copyright` setting so HTML and PDF cannot drift. Settle the
author name on the cover and in the PDF metadata according to question 5. Then rebuild both
editions and confirm the footer, the cover and the published site.

## Commands run

All commands were run from the worktree root at the base revision.

| Ref | Command | Exit | Result |
| --- | --- | --- | --- |
| A | `git grep -n -I 'SPDX-License-Identifier'` | 1 | no matches |
| B | `git grep -n -I -i 'spdx'` | 1 | no matches |
| C | `grep -rIl --exclude-dir=_build --exclude-dir=_site --exclude-dir=.git 'SPDX-License-Identifier' .` | 1 | no matches (tracked and untracked files) |
| D | see below | 0 | only `LICENSE` |
| E | see below (outside pinned snapshots) | 1 | no matches |
| F | see below (pinned snapshots only) | 1 | no matches |
| G | `git grep -n -I -i -E 'licen[cs]'` | 0 | licence mentions only in `LICENSE`, the MIT statements listed under AC-4, `agent-kit/CHANGELOG.md`, workflow and agent policy (`.claude/agents/weave-safety-reviewer.md`, `docs/development/`, `tools/weave_workflow/policy.json`) and `specification/design/README.md` (MathJax note) |
| H | `pdfinfo FILE` and `pdffonts FILE` for each of the four tracked PDFs | 0 | font subsets and metadata as reported under AC-1 |

```bash
# D: licence-like files
git ls-files | grep -i -E '(^|/)(LICEN[CS]E|COPYING|NOTICE)[^/]*$|\.reuse|dep5'

# E: "no licence" phrasings outside the pinned snapshots
git grep -n -I -i -E 'no licen|not licensed|unlicensed|no license has been granted|no licence has been granted|all rights reserved|licen[cs]e (was|has been) not|did not supply a (source )?licen|distribution terms not|no new licen|without a licen' -- . ':!specification/reference/prototype' ':!agent-kit/.agents/skills/weave/assets/prototype'

# F: the same pattern, pinned snapshots only
git grep -n -I -i -E 'no licen|not licensed|unlicensed|no license has been granted|no licence has been granted|all rights reserved|licen[cs]e (was|has been) not|did not supply a (source )?licen|distribution terms not|no new licen|without a licen' -- specification/reference/prototype agent-kit/.agents/skills/weave/assets/prototype

# Control: the same pattern at the parent of 2faeef8 finds six lines (exit 0)
git grep -n -I -i -E 'no licen|not licensed|unlicensed|no license has been granted|no licence has been granted|all rights reserved|licen[cs]e (was|has been) not|did not supply a (source )?licen|distribution terms not|no new licen|without a licen' 2faeef8^ -- .
```

## Draft decision text

The maintainer can adapt this text and record it on #2 using the maintainer decision form.
Bracketed parts need the maintainer's answers.

> Weave is distributed under the MIT License. This covers all code (prototype, vendored and
> reference prototype snapshots, agent kit, build scripts and workflow tooling), the
> specification text and its built editions, all examples, and distributed assets, unless a
> file states otherwise. No separate documentation licence is used.
>
> Rights holders: [holder or holders]. The four inputs recorded in
> `specification/PROVENANCE.json` and the design bundle were [authored by / obtained from]
> [source] under [terms], which permit distribution under MIT. [No / The following] employer,
> funder, institution or contract holds rights in the work: [details].
>
> Third-party material: [fonts embedded in PDFs, theme assets in built editions, other]
> remain under their own licences [and are acknowledged in …].
>
> Follow-up: per-file or per-directory licence identification, PDF cover and colophon, and a
> check of the copyright line, as listed in decision record 0002.

## Follow-up work

After the decision is recorded, one implementation issue should:

1. correct `LICENSE` and the copyright statements if the rights-holder answers require it;
2. add SPDX identifiers or per-directory statements, or REUSE-style metadata, covering code,
   specification, examples and assets, with the pinned snapshots covered from outside their
   directories (AC-3);
3. add the copyright and licence line to the PDF cover or a colophon and settle the cover's
   author name (AC-5);
4. add notices for any third-party material the maintainer identifies (question 6);
5. rebuild the HTML, single-page and PDF editions and check the footer, cover and published
   site;
6. update this record's status to point at the recorded decision.

## What this proposal does not do

- It does not choose or record the licence, and it does not tick any criterion of #2 or record
  maintainer evidence.
- It does not change `LICENSE`, any licence statement, any SPDX identifier,
  `specification/docs/conf.py`, the HTML footer or the PDF cover.
- It does not name rights holders beyond what the repository records and Git history show;
  open points are listed as questions.
- It does not modify either `PROVENANCE.json` or the pinned prototype snapshots.
- It gives no legal advice; the trade-offs noted are for orientation only.
