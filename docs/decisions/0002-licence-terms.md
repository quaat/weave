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

Commit `2faeef8` added an MIT `LICENSE` to the repository. At the orchestrator's request, this
proposal takes as its working assumption **one licence, the MIT License, for everything
distributed from this repository**, pending the maintainer's recorded decision:

- code: the prototype working copy, the vendored and reference prototype snapshots, the agent
  kit, the specification's build scripts and Sphinx extensions, and the workflow tooling;
- specification text: the Sphinx sources and the built editions (multi-page HTML,
  single-page HTML and PDF);
- examples: every Weave program (`*.weave`) and teaching or demo material;
- distributed assets: diagrams, the favicon, the design specimen PDF and generated reports.

This is an assumption, not a decision. Which terms apply, and who the rights holders are, is
for the maintainer to decide and record.

The repository already contains MIT text. Besides adding `LICENSE`, commit `2faeef8` ("Add MIT
license and expand the README") replaced the earlier "no licence" notes in
`README.md`, `specification/README.md`, `specification/docs/chapters/provenance.rst`,
`agent-kit/docs/prototype-status.md` and the `copyright` string in
`specification/docs/conf.py`. The Context paragraph of #2, which describes the material as
having no licence granted, predates that commit and is out of date. What #2 still needs is
the maintainer's recorded decision and confirmation of rights holders (AC-1), plus the
remaining per-file and PDF work (AC-3, AC-5).

## AC-1 Provenance and rights holders

### What the records show

**Git history.** The base revision has 18 commits, all dated 28 October 2026: 15 non-merge
commits and 3 merges. Every commit was authored under one of two Git identities, each carrying
a form of the same personal name as the copyright line in `LICENSE` (one includes a middle
initial, the other does not). 15 commits were authored locally under the first identity. 3 were
created through the GitHub web interface under the second: two pull-request merges and one
workflow file that is not tracked at base. No other human author or committer appears.

14 of the 15 non-merge commits carry a `Co-Authored-By` trailer naming an AI coding
assistant; no merge commit carries one. Every non-merge commit touching `inventory-proof/`,
`agent-kit/`, `specification/`, `tools/weave_workflow/`, `docs/development/`, `.claude/`,
`LICENSE` or `README.md` carries the trailer, as do 6 of the 7 non-merge commits touching
`.github/`. The exception is the web-created workflow file. The first commit (`2e0e7fe`)
imported the specification, the prototype and the agent kit together. Git history therefore
starts at the import and does not show who wrote the imported material before it.

Commit counts in this record follow one convention: the number of non-merge commits reachable
from base `6564a03` that touch the path, including the import commit where it applies
(`git rev-list --no-merges --count 6564a03 -- PATH`).

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
| `inventory-proof/` (prototype working copy, reports, nets) | 39 | Derived from the v3 archive; touched by 2 commits, including the import; no licence text of its own |
| `agent-kit/` (kit, runner, skill, docs, examples, demos) | 126 | Derived from weave-agent-kit.zip and the v3 archive; touched by 4 commits, including the import; `agent-kit/CHANGELOG.md` records the MIT statement |
| `agent-kit/.agents/skills/weave/assets/prototype/` (vendored snapshot, pinned) | 39 | Byte-identical to the v3 archive per `agent-kit/PROVENANCE.json`; contains no licence or copyright text |
| `agent-kit/examples/` and `agent-kit/demos/` | 34 and 23 | Examples from weave-agent-kit.zip per `specification/docs/chapters/provenance.rst`; no record states who wrote the demos |
| `specification/` (Sphinx sources, rules, Makefile) | 154 | Touched by 7 commits, including the import |
| `specification/reference/prototype/` (reference snapshot, pinned) | 39 | Original bytes of the v3 archive per `specification/PROVENANCE.json`; contains no licence or copyright text |
| `specification/scripts/` and `specification/docs/_ext/` | 8 and 3 | Build and validation scripts and Sphinx extensions; no separate record |
| `specification/examples/` and other `*.weave` programs | 32 files in the directory; 114 `*.weave` files in the repository | Teaching examples from weave-agent-kit.zip, rechecked against v3 |
| `specification/grammar/` | 2 | Grammar sources; no separate record |
| Design assets: `specification/design/weave-design-specimen.pdf`, `specification/docs/_static/diagrams/`, `specification/docs/_static/weave-favicon.svg`, `specification/docs/_latex/weave.sty`, templates | 1 PDF, 6 diagram files, 1 favicon | Specimen PDF metadata names "Danio project" as author; diagrams are drawn by `specification/scripts/render_diagrams.py` and converted by `specification/scripts/diagrams_to_pdf.py` |
| Generated reports and recorded outputs: `inventory-proof/REPORT.md` and the other files `demo.py` writes, `specification/validation/` | 16 in `specification/validation/` | Outputs of the repository's own scripts and builds |
| Built editions (HTML, single page, PDF) | not tracked | Produced by CI; include theme and Sphinx static assets from pinned dependencies |
| `tools/weave_workflow/` and `docs/development/` | 32 and 14 | Created in the workflow bootstrap (`4804662`); touched by 4 and 5 commits respectively, including the bootstrap |
| `.claude/` and `.github/` | 12 and 4 | Agent configuration and CI workflows; touched by 3 and 7 commits respectively |

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

These are questions, not findings. This proposal does not answer them. The maintainer has
since answered questions 1–5, 7 and 8, and question 6 is still open; see
[Maintainer answers](#maintainer-answers) below. The answers are not yet recorded on #2.

1. Who authored or generated each of the four inputs in `specification/PROVENANCE.json`
   (weave-inventory-proof.zip v3, weave-agent-kit.zip, claude-code-weave-merge-sort.md,
   claude-code-tiny-shop.md), and under what terms were they obtained? *(Answered.)*
2. Who authored the design bundle (theme configuration, templates, LaTeX style, design
   specimen PDF), and is it covered by the same answer? *(Answered.)*
3. Does any employer, funder, institution or contract hold rights in any part of the work,
   or impose terms on its publication? *(Answered.)*
4. Does the copyright line in `LICENSE` name the correct holder or holders for all of the
   material above? *(Answered.)*
5. The specification's `author` setting, the PDF cover and the design specimen's metadata name
   "Danio project", while the copyright line names an individual. Which name should appear as
   author and which as copyright holder? *(Answered.)*
6. Is any third-party material distributed beyond what is listed above (fonts embedded in
   PDFs, theme assets in built editions, quoted text, diagrams or code adapted from elsewhere),
   and does any of it need its own notice? *(Still open.)*
7. 14 of the 15 non-merge commits carry an AI co-author trailer. Does the maintainer want the
   decision to say anything about AI-assisted contributions? *(Answered.)*
8. Should future contributions be accepted under the same terms by stating so (as
   `README.md` does now), or by another mechanism such as a sign-off requirement? *(Answered.)*

### Maintainer answers

The maintainer gave these answers to the orchestrator in conversation on 28 October 2026, and
the orchestrator relayed them for this record. They are not yet recorded on #2, so they are
not a decision. Each answer is quoted verbatim.

| Question (short form) | Answer |
| --- | --- |
| 1. Who authored the four `specification/PROVENANCE.json` inputs, and on what terms? | "ChatGPT wrote all, it should be released under MIT license." |
| 2. Does the same answer cover the design bundle? | "yes" |
| 3. Does any employer, funder, institution or contract hold rights or impose terms? | "no" |
| 4. Does the copyright line in `LICENSE` name the correct holder? | "correct" |
| 5. Which name should appear as author, and which as copyright holder? | "It should be Weave (not Danio)" |
| 6. Is other third-party material distributed that needs a notice? | "don't know" |
| 7. Should the decision say anything about AI-assisted contributions? | "sure, this is an AI developed programming language" |
| 8. How are future contributions accepted? | "same terms by stating so" |

How this record reads the answers:

- Answers 1 and 2 cover the four inputs and the design bundle.
- Answer 5 changes the author name only ("Danio project" becomes Weave). The copyright holder
  stays as named in `LICENSE`, per answer 4.
- Answer 8 keeps the existing statement in `README.md`.
- Question 6 remains open, so the third-party list in the draft stays a placeholder.

Separately, the repository's own commits carry AI co-author trailers naming a different
assistant (see Git history above). The AI statement in the draft below is worded to cover
AI-generated material generally.

## AC-2 LICENSE

**Current state.** At base `6564a03`, `LICENSE` exists at the repository root and contains
the standard MIT License text with one copyright line for 2026. It was added in `2faeef8`. No
other licence file is tracked at base (command D below).

**Assessment under the working assumption.** If MIT covers code and prose alike, one `LICENSE`
satisfies AC-2 and no `LICENSE-docs` is needed. Note for the decision: MIT is uncommon for
prose, and Creative Commons Attribution 4.0 (CC BY 4.0) is the usual choice for
documentation. Whether MIT suits the specification text is for the maintainer to confirm.

**Follow-up.** Answer 4 ("correct") confirms the copyright line. Once that is recorded on
#2, `LICENSE` needs no change; answer 5 renames the author only (see Follow-up work).

## AC-3 SPDX identifiers or per-directory statement

**Measured state.** At base `6564a03`, no tracked file contains an SPDX identifier (commands A
and B below), and there is no REUSE metadata (command D). The only per-directory
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

**Measured state.** At base `6564a03`, no tracked file outside the pinned snapshots contains a
"no licence" style statement, and neither pinned snapshot does (commands E and F below). The
same search run at the parent of `2faeef8` finds six such lines, in `README.md`,
`agent-kit/docs/prototype-status.md`, `specification/README.md`,
`specification/docs/chapters/provenance.rst` (two lines) and `specification/docs/conf.py`, so
the pattern does detect the earlier wording and `2faeef8` removed it.

At base `6564a03`, `specification/docs/conf.py` sets:

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
The HTML footer therefore follows `conf.py` and will show whatever `copyright` string is set
when the site is next rebuilt. The
published site was not checked (no network access during preparation).

**PDF cover.** `specification/docs/_latex/weave.sty` defines the cover (`\weavemaketitle`): the
label "DANIO PROJECT", the title, the tagline, the release, the `author` setting
("Danio project") and the reference-snapshot digest. It shows **no copyright or licence
line**, and the PDF has no copyright page. The running footer reads "Weave / Draft
specification" and the page number. PDF metadata takes its author from the same setting. In
the PDF, the MIT statement appears only in the body, in the "Distribution status" section built from
`specification/docs/chapters/provenance.rst`. No built PDF was available to inspect; this
assessment comes from the style file and `conf.py`.

**Follow-up.** Add a copyright and licence line to the PDF cover, or a short colophon page
after it, driven from the `copyright` setting so HTML and PDF cannot drift. Settle the
author name on the cover and in the PDF metadata according to question 5. Then rebuild both
editions and confirm the footer, the cover and the published site.

## Commands run

Every measurement is pinned to a revision, so it reads the same however this branch moves; the
search commands would otherwise match the patterns quoted in this record. All were run from the
worktree root. A, B and D–G read base `6564a03`. The control reads the parent of `2faeef8`. H
reads the four PDFs in the worktree; `git diff --stat 6564a03 HEAD -- '*.pdf'` is empty, so
they are the files tracked at base. An earlier worktree scan, labelled C, was dropped: it would
also match this record.

| Ref | Command | Exit | Result |
| --- | --- | --- | --- |
| A | `git grep -n -I 'SPDX-License-Identifier' 6564a03 -- .` | 1 | no matches |
| B | `git grep -n -I -i 'spdx' 6564a03 -- .` | 1 | no matches |
| D | see below | 0 | only `LICENSE` |
| E | see below (outside pinned snapshots) | 1 | no matches |
| F | see below (pinned snapshots only) | 1 | no matches |
| G | `git grep -n -I -i -E 'licen[cs]' 6564a03 -- .` | 0 | licence mentions only in `LICENSE`, the MIT statements listed under AC-4, `agent-kit/CHANGELOG.md`, workflow and agent policy (`.claude/agents/weave-safety-reviewer.md`, `docs/development/`, `tools/weave_workflow/policy.json`) and `specification/design/README.md` (MathJax note) |
| H | `pdfinfo FILE` and `pdffonts FILE` for each of the four PDFs | 0 | font subsets and metadata as reported under AC-1 |
| Control | see below | 0 | six lines, listed under AC-4 |

```bash
# D: licence-like files tracked at base
git ls-tree -r --name-only 6564a03 | grep -i -E '(^|/)(LICEN[CS]E|COPYING|NOTICE)[^/]*$|\.reuse|dep5'

# E: "no licence" phrasings at base, outside the pinned snapshots
git grep -n -I -i -E 'no licen|not licensed|unlicensed|no license has been granted|no licence has been granted|all rights reserved|licen[cs]e (was|has been) not|did not supply a (source )?licen|distribution terms not|no new licen|without a licen' 6564a03 -- . ':!specification/reference/prototype' ':!agent-kit/.agents/skills/weave/assets/prototype'

# F: the same pattern at base, pinned snapshots only
git grep -n -I -i -E 'no licen|not licensed|unlicensed|no license has been granted|no licence has been granted|all rights reserved|licen[cs]e (was|has been) not|did not supply a (source )?licen|distribution terms not|no new licen|without a licen' 6564a03 -- specification/reference/prototype agent-kit/.agents/skills/weave/assets/prototype

# Control: the same pattern at the parent of 2faeef8
git grep -n -I -i -E 'no licen|not licensed|unlicensed|no license has been granted|no licence has been granted|all rights reserved|licen[cs]e (was|has been) not|did not supply a (source )?licen|distribution terms not|no new licen|without a licen' 2faeef8^ -- .
```

## Draft decision text

This text reflects the maintainer answers above and is written for the maintainer to post on
#2 using the maintainer decision form. Bracketed parts are optional or still open.

> **Licence terms for Weave (#2)**
>
> Weave is distributed under the MIT License. Except for the third-party material named
> below, this covers all code (the prototype, the vendored and reference prototype snapshots,
> the agent kit, build scripts and workflow tooling), the specification text and its built editions, all examples, and assets authored
> for Weave, unless a file states otherwise. No separate documentation licence is used.
>
> The rights holder is the copyright holder named in `LICENSE`. The four inputs recorded in
> `specification/PROVENANCE.json` (weave-inventory-proof.zip v3, weave-agent-kit.zip,
> claude-code-weave-merge-sort.md and claude-code-tiny-shop.md) and the design bundle were
> generated with ChatGPT for this project. The copyright holder releases them under the MIT
> License [optional: to the extent the holder has rights in AI-generated material]. No
> employer, funder, institution or contract holds rights in the work or sets conditions on it.
>
> Weave is developed with AI assistance, and the AI-generated material is released under the
> same terms.
>
> The author name is "Weave" [option: "the Weave project"], replacing "Danio project". The
> copyright holder is unchanged.
>
> Third-party material distributed with or embedded in Weave, including [fonts embedded in
> PDFs, theme and Sphinx assets in built editions; further items to be identified in
> follow-up], is not covered by this grant and remains under its own licence. Its terms and
> notices will be recorded in [a third-party notices file at the repository root / the
> REUSE-style metadata of AC-3 option 3].
>
> Contributions are accepted under the same terms, as stated in `README.md`.
>
> Follow-up: per-file or per-directory licence identification; an inventory and record of
> third-party terms and notices; a copyright and licence line on the PDF cover or a colophon;
> and renaming the author from "Danio project" to Weave in `specification/docs/conf.py`, in
> the cover label in `specification/docs/_latex/weave.sty` and in the metadata of
> `specification/design/weave-design-specimen.pdf`, as listed in decision record 0002.

The bracketed clause in the second paragraph is optional. Whether copyright exists in purely
AI-generated material varies by jurisdiction, and the clause avoids claiming more than the
holder may have; this is orientation, not legal advice.

## Follow-up work

After the decision is recorded, one implementation issue should:

1. rename the author from "Danio project" to Weave (or the Weave project, if the maintainer
   picks that option): the `author` setting in `specification/docs/conf.py` (which also feeds
   the PDF metadata) and the "DANIO PROJECT" cover label in
   `specification/docs/_latex/weave.sty`. `specification/design/weave-design-specimen.pdf` has
   no tracked source, so its metadata cannot be regenerated from this repository; edit the
   metadata in place, regenerate the PDF from the original design bundle, or record that it
   keeps the old name. `LICENSE` keeps its copyright line (answer 4);
2. add SPDX identifiers or per-directory statements, or REUSE-style metadata, covering code,
   specification, examples and assets, with the pinned snapshots covered from outside their
   directories (AC-3);
3. add the copyright and licence line to the PDF cover or a colophon (AC-5);
4. inventory the third-party material, since question 6 is still open (answer: "don't
   know"). Start from the fonts embedded in PDFs and the theme and Sphinx assets in built
   editions. Record its terms and notices where the decision names: a third-party notices
   file or the REUSE-style metadata of AC-3 option 3;
5. rebuild the HTML, single-page and PDF editions and check the footer, cover, author name and
   published site;
6. update this record's status to point at the recorded decision.

## What this proposal does not do

- It does not choose or record the licence, and it does not tick any criterion of #2 or record
  maintainer evidence.
- It does not change `LICENSE`, any licence statement, any SPDX identifier,
  `specification/docs/conf.py`, the HTML footer or the PDF cover.
- Its own findings name no rights holder beyond what the repository records and Git history
  show. The maintainer's answers are quoted as relayed, and the remaining open point is
  listed as a question.
- It does not modify either `PROVENANCE.json` or the pinned prototype snapshots.
- It gives no legal advice; the trade-offs noted are for orientation only.
