# 0002: Licence terms for implementation, specification and assets

- **Issue:** [quaat/weave#2](https://github.com/quaat/weave/issues/2), milestone M0
- **Recorded decision:** [maintainer comment on #2](https://github.com/quaat/weave/issues/2#issuecomment-6480423748), created
  2026-10-28T20:52:50Z: "Licence terms: MIT for all of Weave; rights holder as in LICENSE"
- **Status:** Decided — recorded by the maintainer on #2 (link above), 28 October 2026
- **Prepared against:** base revision `6564a0399f10cea02a7274a9e67ce98efd75af14`, 28 October 2026
- **Implemented on:** base `6516e2b23834aa8b9f036a9370a935b6c176a3a0`. The REUSE metadata from
  draft PR #64 (`7b2cb65`, cherry-picked as `cf1e3b6`) plus the cover and author change in
  `f32a168`.
- **Decision owner:** the maintainer. The decision text is the maintainer's; this record
  quotes it and does not add to it.

This is the decision record for #2, together with the implementation that goes with it. It
assesses each acceptance criterion, records the rights questions and the maintainer's answers,
and quotes the decision the maintainer recorded on #2. The change it documents adds per-path
licence metadata (AC-3), and a copyright and licence line on the PDF cover plus the author
rename (AC-5). It does not change the `LICENSE` text or its copyright holder, any provenance
record or any pinned snapshot byte, and it does not tick any criterion.

## Summary and decided terms

The maintainer decided **"Licence terms: MIT for all of Weave; rights holder as in LICENSE"**
(see [Recorded decision](#recorded-decision)). Except for third-party material, which keeps
its own licence, the MIT License covers:

- code: the prototype working copy, the vendored and reference prototype snapshots, the agent
  kit, the specification's build scripts and Sphinx extensions, and the workflow tooling;
- specification text: the Sphinx sources and the built editions (multi-page HTML,
  single-page HTML and PDF);
- examples: every Weave program (`*.weave`) and teaching or demo material;
- distributed assets: diagrams, the favicon, generated reports, and the Weave-authored content
  of the specimen and diagram PDFs (embedded fonts excluded; see
  [Third-party material](#third-party-material)).

The rights holder is the copyright holder named in `LICENSE`, and no separate documentation
licence is used. Earlier versions of this record took MIT as a working assumption at the
orchestrator's request; the recorded decision replaces that assumption.

The repository already contains MIT text. Besides adding `LICENSE`, commit `2faeef8` ("Add MIT
license and expand the README") replaced the earlier "no licence" notes in
`README.md`, `specification/README.md`, `specification/docs/chapters/provenance.rst`,
`agent-kit/docs/prototype-status.md` and the `copyright` string in
`specification/docs/conf.py`. The Context paragraph of #2, which describes the material as
having no licence granted, predates that commit and is out of date. The maintainer has
now recorded the decision, including the rights-holder confirmation (AC-1). This change
delivers the per-path licence metadata (AC-3) and the PDF cover notice (AC-5); the sections
below say what remains in the root `follow-up` record.

## AC-1 Provenance and rights holders

The recorded decision answers the rights-holder and provenance questions below.
- The rights holder is the copyright holder named in `LICENSE`.
- The four `specification/PROVENANCE.json` inputs and the design bundle were generated with
  ChatGPT for this project. In the decision's words: "The copyright holder releases them under
  the MIT License to the extent the holder has rights in AI-generated material."
- No employer, funder, institution or contract holds rights or sets conditions.

The decision excludes third-party material from the grant. The maintainer answered question
6 ("don't know"), so that material was identified from the files themselves; see
[Third-party material](#third-party-material). The sections that follow it are the evidence
gathered before the decision.

### Third-party material

The full notices are in the "Third-party notices" section of
`specification/docs/chapters/provenance.rst`. That section is built into every edition and
gives version, SPDX licence, holder and the verbatim licence texts. In the repository,
`REUSE.toml` and `LICENSES/` record the same terms. Evidence is measured at `f39c1cd`; commands
F0–F5 and R8–R9 are under [Commands run](#commands-run).

- **Fonts in the four committed PDFs and the built PDF.**
  - DejaVu fonts. The specimen's subsets keep their name tables, which give version 2.35 (2.37
    for Sans Bold) and a licence string naming the Bitstream Vera licence. DejaVu Sans and Sans
    Bold also name the Arev licence of Tavmjong Bah.
  - The diagram subsets have no name table, but every compared glyph is identical to the
    installed DejaVu Sans 2.37, which names both licences.
  - Licences: Bitstream-Vera (2003 Bitstream, Inc.) and LicenseRef-Arev-Fonts (2006 Tavmjong
    Bah). DejaVu's own changes are public domain.
  - The specimen's Computer Modern fonts are the AMS Type 1 release 003.002 (Notice: 1997, 2009
    American Mathematical Society, with Reserved Font Names), licensed OFL-1.1-RFN.
  - A locally compiled specification PDF embeds the same families: DejaVu 2.37 and the AMS
    fonts CMR, CMMI, CMSY, CMEX and MSBM.
- **Files in the built HTML editions.** All 40 static files were matched by hash to their
  packages, or traced to Sphinx and Pygments templates.
  - Furo 2025.12.19 (MIT, Pradyun Gedam), bundling normalize.css 8.0.1 (MIT) and gumshoe 5.1.2
    (MIT).
  - sphinx-basic-ng 1.0.0b2 (MIT).
  - Sphinx 8.2.3 (BSD-2-Clause).
  - sphinx-design 0.7.0 (MIT).
  - sphinx-copybutton 0.5.2 (MIT), shipping clipboard.js 2.0.8 (MIT).
  - Pygments 2.21.0 (BSD-2-Clause) with accessible-pygments 0.0.5 (BSD-3-Clause).
  - Only furo.css, furo.js (via furo.js.LICENSE.txt) and clipboard.min.js carry their own
    notices; for the rest, the notices section supplies them.
  - MathJax is loaded from a CDN and not redistributed.
- **Open points** (root `follow-up`):
  - The gumshoe holder wording differs between Furo's shipped notice ("(c) 2019 Chris
    Ferdinandi") and the upstream licence file (Go Make Things, LLC; the 5.1.2 tag's file
    could not be retrieved).
  - A diagram PDF copied on its own carries no font notice.
  - The release PDF and the published site have not been checked.

### What the records show

**Git history.** This paragraph describes history up to the first base, `6564a03`. The later
base `6516e2b` adds one more non-merge commit (the first `REUSE.toml`), created through the
GitHub web interface under the second identity below, with no AI co-author trailer. The
commits of this candidate are not described here.

The first base has 18 commits, all dated 28 October 2026: 15 non-merge
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
| claude-code-weave-merge-sort.md | none recorded | Proposed pure-function and fork/join task | Distributed as `agent-kit/claude-code-weave-merge-sort.md`, whose SHA-256 equals the recorded digest; its subject matches `agent-kit/demos/merge_sort/` and the kit's pure-function extension |
| claude-code-tiny-shop.md | none recorded | Application brief | Distributed as `agent-kit/claude-code-tiny-shop.md`, whose SHA-256 equals the recorded digest; its subject matches `agent-kit/demos/tiny_shop/` |

Correction: an earlier version of this table said no record shows where the two briefs are
used. Both are tracked files in `agent-kit/`, and their digests match `specification/PROVENANCE.json`
(`sha256sum` on the two files).

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

These are the questions put to the maintainer. Questions 1–5, 7 and 8 are answered (see
[Maintainer answers](#maintainer-answers) below), and the answers are reflected in the
decision recorded on #2. Question 6 was answered "don't know", and the material was then
identified from the files (see [Third-party material](#third-party-material)).

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
   and does any of it need its own notice? *(Answered "don't know"; identified from the
   files.)*
7. 14 of the 15 non-merge commits carry an AI co-author trailer. Does the maintainer want the
   decision to say anything about AI-assisted contributions? *(Answered.)*
8. Should future contributions be accepted under the same terms by stating so (as
   `README.md` does now), or by another mechanism such as a sign-off requirement? *(Answered.)*

### Maintainer answers

The maintainer gave these answers to the orchestrator in conversation on 28 October 2026, and
the orchestrator relayed them for this record. The maintainer then recorded the decision on #2
(see [Recorded decision](#recorded-decision)), which reflects them. Each answer is quoted
verbatim as relayed.

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
- Question 6 was answered "don't know". The decision names fonts embedded in PDFs and theme
  and Sphinx assets and leaves further items to follow-up; that inventory is now recorded under
  [Third-party material](#third-party-material).

Separately, the repository's own commits carry AI co-author trailers naming a different
assistant (see Git history above). The AI statement in the recorded decision covers
AI-generated material generally.

## AC-2 LICENSE

**Current state.** At base `6564a03`, `LICENSE` exists at the repository root and contains
the standard MIT License text with one copyright line for 2026. It was added in `2faeef8`. No
other licence file is tracked at base (command D below).

**Assessment.** The decision applies MIT to code and prose alike and uses no separate
documentation licence, so one `LICENSE` satisfies AC-2 and no `LICENSE-docs` is needed. During
preparation this record noted that MIT is uncommon for prose and that Creative Commons
Attribution 4.0 (CC BY 4.0) is the usual choice for documentation; the maintainer chose MIT.

**Follow-up.** None. The decision keeps the rights holder as named in `LICENSE`, so
`LICENSE` needs no change. Answer 5 renames the author only; this change does that (see
AC-5). `LICENSES/MIT.txt`, added for REUSE tooling, is byte-identical to `LICENSE` (command R2).

## AC-3 SPDX identifiers or per-directory statement

**Measured state.** At base `6564a03`, no tracked file contains an SPDX identifier (commands A
and B below), and there is no REUSE metadata (command D). The only per-directory
statements are prose sentences in `specification/README.md` and
`agent-kit/docs/prototype-status.md`. `inventory-proof/` has no statement of its own; the
root `README.md` says the licence covers the whole repository.

**Options considered before this change** (not mutually exclusive):

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

**Delivered in this change (option 3).** Measured at `f32a168`; the PDF annotations and
font licences at `f39c1cd`. The commands are under [Commands run](#commands-run).

- `REUSE.toml` (REUSE Specification 3.3, configuration version 1, from PR #64) annotates 386
  exact paths, each with `precedence = "closest"`, so that a notice in a file or `.license`
  sidecar wins. Every path exists in the tree and none is listed twice (command R1).
  - Weave-authored material carries `SPDX-FileCopyrightText = "2026 Thomas F. Hagelien"` and
    `SPDX-License-Identifier = "MIT"`. This covers code, specification sources, examples,
    assets, both pinned snapshots, this record and `follow-up`.
  - The four committed PDFs carry the MIT grant for their Weave-authored content together
    with their embedded fonts' licences and holders, joined with AND (each PDF is one combined
    work): MIT, Bitstream-Vera and LicenseRef-Arev-Fonts for the diagrams, plus OFL-1.1-RFN for
    the specimen. Added in `f39c1cd`; the PDF bytes are unchanged.
  - The adapted Furo search form (`specification/docs/_templates/sidebar/search.html`) carries
    both the upstream notice and Weave's, under MIT.
  - Exact paths mean a new file is not covered until it is reviewed and annotated.
- The pinned snapshots are annotated from `REUSE.toml` without changing their bytes. Both
  provenance manifests still verify; that is the documentation audit's synced and provenance
  check.
- `LICENSES/MIT.txt` holds the licence text for REUSE tooling and is byte-identical to
  `LICENSE`, including its copyright line (command R2). REUSE does not need the generic
  template form; the per-file holder comes from `REUSE.toml`, and it is the same holder.
- The root `README.md`, `specification/README.md` and
  `specification/docs/chapters/provenance.rst` state that the MIT grant covers Weave-authored
  material, that third-party material keeps its own terms, and where the metadata lives.
- `LICENSES/Bitstream-Vera.txt` and `LICENSES/OFL-1.1-RFN.txt` are the canonical SPDX texts
  from `reuse download`, unedited (command F4). `LICENSES/LicenseRef-Arev-Fonts.txt` is the
  Arev section of the DejaVu Sans name table, verbatim (command F5). The SPDX list bundled
  with REUSE 5.1.1 (3.27.0) has `Bitstream-Vera` and `OFL-1.1-RFN` but no Arev or DejaVu
  identifier.
- `reuse lint` (REUSE 5.1.1) at `f39c1cd` exits 0 (command R8):

  ```text
  Bad licenses: 0; Deprecated licenses: 0; Licenses without file extension: 0;
  Missing licenses: 0; Unused licenses: 0;
  Used licenses: Bitstream-Vera, LicenseRef-Arev-Fonts, MIT, OFL-1.1-RFN; Read errors: 0;
  Files with copyright information: 388 / 388; Files with license information: 388 / 388
  Congratulations! Your project is compliant with version 3.3 of the REUSE Specification :-)
  ```

  Before the font licences were added (at `f32a168`), it exited 1. Its only findings then were
  the four PDFs, which `REUSE.toml` deliberately left unannotated until their font terms were
  known:

  ```text
  * specification/design/weave-design-specimen.pdf
  * specification/docs/_static/diagrams/handle-states.pdf
  * specification/docs/_static/diagrams/inventory-n0.pdf
  * specification/docs/_static/diagrams/r0-unknown.pdf
  Bad licenses: 0; Deprecated licenses: 0; Licenses without file extension: 0;
  Missing licenses: 0; Unused licenses: 0; Used licenses: MIT; Read errors: 0;
  Files with copyright information: 384 / 388; Files with license information: 384 / 388
  ```

**Remaining (root `follow-up`).**

- FU-01 residual: a diagram PDF copied on its own carries no font notice. Fixing that means
  regenerating the diagrams.
- FU-04: wording in `agent-kit/docs/prototype-status.md`; licence texts in independently
  shipped archives; a pinned REUSE check in CI, now that lint passes.
- No per-file SPDX headers were added. `REUSE.toml` covers the same files without touching
  pinned or generated bytes.

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

This change sets `author = "Weave"` and leaves the `copyright` string unchanged (AC-5).

**Follow-up.** None. No "no licence" statement remains, and the decision keeps the holder named
in `LICENSE`, so the `copyright` string and the licence sections need no change.

## AC-5 Specification footer and PDF cover

The first two paragraphs describe the state at base, before this change.

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

**Delivered in this change.** Measured at `f32a168`, except the cover-geometry and
fail-closed points, which come from the review fixes in `6233a78`; the commands are under
[Commands run](#commands-run).

- `specification/docs/conf.py` sets `author = "Weave"` (answer 5), which is also the PDF
  metadata author. `copyright` is unchanged.
- A `config-inited` hook in `conf.py` runs at priority 900, after Sphinx's own
  `SOURCE_DATE_EPOCH` year correction at 800. It appends `\WeaveCopyright`, defined from the
  final `copyright` value with LaTeX specials escaped, to the LaTeX preamble. The PDF cover
  and the HTML footer therefore print one value. An empty `copyright` stops the build with a
  `ConfigError`.
- `specification/docs/_latex/weave.sty` prints "Copyright ©" and `\WeaveCopyright` on the
  cover, below the author line. Under it, a line says that third-party material, including
  embedded fonts, keeps its own terms, and points to `LICENSE`, `REUSE.toml` and `follow-up`
  in the project repository.
- The "DANIO PROJECT" label is removed rather than replaced with "WEAVE". The monogram, the
  title and the author line already say Weave, so a fourth instance would add nothing. The
  label's place is taken by an empty box, which keeps the monogram's baseline exactly where
  it was. Measured with `\pdfsavepos` in a minimal XeLaTeX cover built from the real
  `\weavemaketitle`, the baseline sits 39,782,916 sp (607.0391 pt) above the page bottom at
  base `6516e2b` and with this change. The earlier version (`9e5f6c8`), which used a starred
  space instead, put it at 38,838,151 sp (592.6232 pt), 14.4159 pt lower.
- If `\WeaveCopyright` is undefined, the cover raises a `\PackageError` instead of omitting
  the notice, so the PDF build fails loudly.
- Evidence:
  - `make latex` (exit 0) writes the line
    `\newcommand{\WeaveCopyright}{2026, Thomas F. Hagelien. MIT License}` and `\author{Weave}`
    into the generated `weave-specification.tex`.
  - With `SOURCE_DATE_EPOCH` set to 1 January 2025, the macro reads "2025, …", the same year
    Sphinx uses for the HTML footer.
  - `-D 'copyright=2026 A & B_C 100% #1'` yields `2026 A \& B\_C 100\% \#1`.
  - `-D 'copyright='` exits 2 with the `ConfigError`.
  - A local `xelatex` compile of the generated source (one pass; `latexmk` is not installed)
    exits 0, with 0 missing characters. `pdftotext` on page 1 reads the author "Weave", the line
    "Copyright © 2026, Thomas F. Hagelien. MIT License" and the third-party line, and
    `pdfinfo` reports Author "Weave". The cover was rendered and inspected.
  - The single-page HTML build prints the same "Copyright © 2026, Thomas F. Hagelien. MIT
    License" in its footer.
- No edition was rebuilt for release or published.

**Remaining (root `follow-up`).**

- FU-03: build and inspect the release PDF and both HTML editions from the pinned environment.
- FU-02: the specimen PDF's author metadata still says "Danio project". Its bytes are
  unchanged; it has no tracked source.
- FU-04: the HTML footer prints the copyright line but not the third-party pointer the PDF
  cover now has. `specification/docs/_templates/page.html` is outside this change.

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

### Commands for this change

Run from the worktree root. R1–R4 read commit `f32a168`. The other commands ran on a clean
worktree at that commit, with the pinned toolchains: the specification virtual environment's
Python and REUSE 5.1.1 from the workflow's REUSE virtual environment.

| Ref | Command | Exit | Result |
| --- | --- | --- | --- |
| R1 | Python: parse `git show f32a168:REUSE.toml` with `tomllib` and compare its paths with `git ls-tree -r --name-only f32a168` | 0 | 386 paths, 0 duplicates, 0 missing. Not annotated: `LICENSE`, `LICENSES/MIT.txt`, `REUSE.toml` and the four PDFs |
| R2 | `diff <(git show f32a168:LICENSE) <(git show f32a168:LICENSES/MIT.txt)` | 0 | identical |
| R3 | `git grep -n -i 'danio' f32a168 -- .` | 0 | no author-name use left. Hits: local paths recorded in `agent-kit/demos/*/artifacts`, this record and `follow-up` |
| R4 | `git grep -n 'WeaveCopyright' f32a168 -- specification/docs` | 0 | defined in `specification/docs/conf.py`, used in `specification/docs/_latex/weave.sty` |
| R5 | `reuse lint` | 1 | four PDFs only; summary under AC-3 |
| R6 | `make latex` (in `specification/`) | 0 | generated source carries the cover macro and `\author{Weave}` |
| R7 | `make validate-offline`, `make singlehtml text`, `python3 scripts/audit_html.py _build/singlehtml` (in `specification/`) | 0, 0, 0 | 33 pages, 3,191 references, 0 errors; 1 page, 491 references, 0 errors |

### Commands for the third-party evidence

Run from the worktree root. F0, F4, F5 and R8 read commit `f39c1cd` (F5 also reads the installed
font). F0 shows the four PDFs are byte-identical to base, so F1–F3, which read the worktree
copies, read the committed bytes.

| Ref | Command | Exit | Result |
| --- | --- | --- | --- |
| F0 | `git diff --stat 6516e2b f39c1cd -- '*.pdf'` | 0 | empty: PDF bytes unchanged |
| F1 | `pdffonts FILE`, `pdfinfo FILE` and `mutool extract -a FILE` for each PDF | 0 | font names, producers (xdvipdfmx 20220710; cairo 1.18.4), embedded font programs |
| F2 | Python with fontTools: name IDs 0, 5, 13 of each TrueType subset, and Notice and version of each CFF font | 0 | DejaVu versions and licence strings; AMS Notice and version 003.002 |
| F3 | Python with fontTools: glyph coordinates of each diagram subset against `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf` | 0 | 42, 49 and 51 glyphs identical, 0 different |
| F4 | `reuse download Bitstream-Vera OFL-1.1-RFN` in a scratch repository, then `cmp` with `git show f39c1cd:LICENSES/<id>.txt` | 0 | identical |
| F5 | Python: `git show f39c1cd:LICENSES/LicenseRef-Arev-Fonts.txt` against the Arev section of name ID 13 in the installed DejaVu Sans 2.37 | 0 | identical |
| R8 | `reuse lint` on a clean worktree at `f39c1cd` | 0 | 388/388, compliant |
| R9 | Python: SHA-256 of each file in `_build/html/_static` against the installed packages in the specification virtual environment; licence metadata and licence files from each `dist-info` | 0 | package, version, licence and holder per file, as in the notices section |

## Recorded decision

The maintainer recorded the decision on #2 in [this comment](https://github.com/quaat/weave/issues/2#issuecomment-6480423748) (created
2026-10-28T20:52:50Z). Below is its text, verbatim, after the line that identifies it as a
decision:

> Weave is distributed under the MIT License. Except for the third-party material named below, this covers all code (the prototype, the vendored and reference prototype snapshots, the agent kit, build scripts and workflow tooling), the specification text and its built editions, all examples, and assets authored for Weave, unless a file states otherwise. No separate documentation licence is used.
>
> The rights holder is the copyright holder named in `LICENSE`. The four inputs recorded in `specification/PROVENANCE.json` (weave-inventory-proof.zip v3, weave-agent-kit.zip, claude-code-weave-merge-sort.md and claude-code-tiny-shop.md) and the design bundle were generated with ChatGPT for this project. The copyright holder releases them under the MIT License to the extent the holder has rights in AI-generated material. No employer, funder, institution or contract holds rights in the work or sets conditions on it.
>
> Weave is developed with AI assistance, and the AI-generated material is released under the same terms.
>
> The author name is "Weave", replacing "Danio project". The copyright holder is unchanged.
>
> Third-party material distributed with or embedded in Weave, including fonts embedded in PDFs, theme and Sphinx assets in built editions, and further items to be identified in follow-up, is not covered by this grant and remains under its own licence. Its terms and notices will be recorded in REUSE-style metadata (REUSE.toml) at the repository root.
>
> Contributions are accepted under the same terms, as stated in `README.md`.
>
> Follow-up: path-based licence identification through REUSE metadata, covering code, specification, examples and assets without changing the pinned snapshots; an inventory and record of third-party terms and notices; a copyright and licence line on the PDF cover or a colophon; and renaming the author from "Danio project" to Weave in `specification/docs/conf.py`, the cover label in `specification/docs/_latex/weave.sty` and the metadata of `specification/design/weave-design-specimen.pdf`, as listed in decision record 0002.

Its follow-up paragraph was written before this change. This change delivers:
- the REUSE metadata (AC-3);
- the copyright and licence line on the PDF cover;
- the author rename in `specification/docs/conf.py` and in the cover in
  `specification/docs/_latex/weave.sty`, where the label was removed.

The remaining items, including the third-party inventory and the metadata of
`specification/design/weave-design-specimen.pdf`, stay in the root `follow-up` record (see
below).

## Follow-up work

The root `follow-up` record is the tracker; this list mirrors it. Completed:
- the rights-holder confirmation and the decision, recorded by the maintainer on #2 (FU-02);
- this record's status, which points at the recorded decision;
- the PDF cover notice (FU-04);
- the author rename in `specification/docs/conf.py` and the cover (FU-02);
- the third-party wording in `specification/README.md` and
  `specification/docs/chapters/provenance.rst` (FU-04, partly);
- the REUSE annotation of this record;
- the embedded fonts' identification, licence texts and REUSE annotations; `reuse lint` passes
  (FU-01);
- the third-party notices for every edition (FU-03, partly).

Still open:

1. **FU-01 residual.** A diagram PDF copied on its own carries no font notice; fixing that
   means regenerating the diagrams. Whether FU-01 still blocks a release is for the maintainer
   to reassess.
2. **FU-02.**
   - Identify any further holders.
   - Settle the specimen PDF's "Danio project" author metadata: edit it, regenerate the PDF
     from the original design bundle, or record that it keeps the old name.
3. **FU-03.**
   - Build and check the release PDF and the published site.
   - Review the design templates, CSS and extensions for copied material.
   - Settle the gumshoe holder wording.
   - Add a machine-readable SBOM.
4. **FU-04.**
   - Align `agent-kit/docs/prototype-status.md` and any other component statement with the
     third-party exception.
   - Ship the licence texts with independently distributed archives.
   - Add a pinned REUSE check to CI.
   - Add the third-party pointer to the HTML footer.
   - Reconcile #2's criteria with the evidence.

## What this record does not do

- It does not choose the licence. The maintainer recorded the decision on #2, and this record
  quotes it unchanged. It does not tick any criterion of #2 or record maintainer evidence.
- It does not change the `LICENSE` text or its copyright holder, or the `copyright` string
  the HTML footer prints. It does change the `author` setting and the PDF cover (AC-5).
- It does not change the bytes of the four committed PDFs, including
  `specification/design/weave-design-specimen.pdf`, and it does not rebuild or publish any
  edition.
- Its own findings name no rights holder beyond what the repository records and Git history
  show. The maintainer's answers and decision are quoted as given, and the remaining open
  point is listed as a question.
- It does not modify either `PROVENANCE.json` or the pinned prototype snapshots.
- It gives no legal advice; the trade-offs noted are for orientation only.
