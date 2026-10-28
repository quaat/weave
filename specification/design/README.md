# Weave documentation design

A coordinated HTML and PDF presentation for the Weave 0.2 draft specification.
The bundle changes presentation and build configuration; it does not define or
modify the language. It retains `weave_lexer`, `weave_check`,
`weave_singlehtml`, and the existing provenance location.

## Integration in this repository

The bundle is installed in `specification/docs/`. Paths below are relative to
`specification/`.

| Bundle file | Installed at | Purpose |
| --- | --- | --- |
| `conf.py` | `docs/conf.py` | Sphinx, HTML, PDF, validation, and provenance configuration |
| `_static/weave.css` | `docs/_static/weave.css` | Typography, components, responsive and print adjustments; plus `weave-check` status styling |
| `_static/weave-favicon.svg` | `docs/_static/weave-favicon.svg` | Small vector monogram |
| `_templates/sidebar/brand.html` | `docs/_templates/sidebar/brand.html` | Brand and draft identifier |
| `_templates/page.html` | `docs/_templates/page.html` | Provenance footer; also keeps the former single-page link-tag suppression and D0/N2 note |
| `_latex/weave.sty` | `docs/_latex/weave.sty` | PDF cover, headings, running headers, and spacing |
| `requirements.txt` | merged into `requirements.txt` | Complete pinned dependency set |
| `preview/weave-design-specimen.pdf` | `design/weave-design-specimen.pdf` | Synthetic design specimen (not specification content) |

<!-- docs-audit: external preview/weave-design-specimen.pdf -- the bundle's own layout, left column of the table -->

Integration changes beyond copying:

- The Alabaster `docs/_templates/layout.html` was removed; Furo does not
  render pages through `layout.html`. Its footer and single-page link-tag
  override moved into `page.html`.
  <!-- docs-audit: external docs/_templates/layout.html layout.html -- removed during integration; named as history -->
- `docs/_ext/weave_singlehtml.py` only replaces the single-page sidebar when the
  theme is Alabaster; Furo's sidebar is used as is.
- The three SVG figures gained PDF companions and are referenced as
  `diagram.*`, so XeLaTeX receives PDF and HTML keeps SVG.
- Builds stay in `_build/` at the specification root (not `docs/_build`).

### Python dependencies

Python 3.11 or newer is required. From `specification/`:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

The tested baseline stays on Sphinx 8.2.3. Upgrade Sphinx separately after
testing the private Weave extensions.

### PDF and diagram dependencies

For Debian/Ubuntu, install the native tools and complete DejaVu font family:

```sh
sudo apt-get update
sudo apt-get install -y make latexmk texlive-xetex texlive-latex-extra \
  texlive-fonts-recommended texlive-lang-english fonts-dejavu graphviz
```

On other systems, install the equivalent TeX Live or MacTeX packages, Graphviz,
and the DejaVu fonts, including italic and bold variants. `xelatex`, `latexmk`,
`makeindex`, and `dot` must be on `PATH`. The Python `graphviz` package alone
does not supply the `dot` executable. An English index uses `makeindex`; for
Unicode-aware index sorting, install `xindy` and set `latex_use_xindy = True`.

## Build

Run these commands from `specification/` after activating the environment:

```sh
make html          # or: python -m sphinx -n -W --keep-going -b html docs _build/html
make singlehtml
make latexpdf      # requires XeLaTeX, latexmk, makeindex, DejaVu fonts
make linkcheck
```

The primary outputs are `_build/html/index.html` and
`_build/latex/weave-specification.pdf`. `latexpdf` compiles the PDF;
the `latex` builder alone only writes its input files. Link checking requires
network access and can fail when a remote host is unavailable.

Serial builds are intentional: the parallel safety of the private extensions
is unknown. Enable parallel Sphinx builds only after checking them. Treat
Sphinx warnings as errors, and also inspect the final `.log` for unresolved
references, missing glyphs, or overfull boxes: successful LaTeX compilation
does not make those warnings fatal. For release reproducibility, pin the native
toolchain as well and set `SOURCE_DATE_EPOCH` to the release commit timestamp.

## What changed

| Component | Contribution |
| --- | --- |
| Furo | Responsive navigation, search, theme switching, restrained light/dark palettes |
| `sphinx_design` | Cards, responsive grids, tabs, and explanatory dropdowns |
| `sphinx_copybutton` | Copyable examples without deleting literal language operators |
| `sphinx.ext.mathjax` | Browser equations; the LaTeX builder typesets PDF equations natively |
| `sphinx.ext.graphviz` | SVG graphs in HTML and vector PDF graphs in LaTeX |
| `accessible-pygments` | High-contrast syntax styles for both colour modes |
| XeLaTeX + `weave.sty` | A4 typesetting, serif prose, sans serif headings, cover, bookmarks, and index |

The obsolete Alabaster sidebar templates and width options are removed.
Furo keeps its default navigation structure; two small template overrides add
the brand and provenance. Custom CSS and those overrides should be rechecked
when upgrading Furo, since theme internals can change.

`nitpicky`, document-prefixed section labels, source links, source copying,
numbered figures, literal punctuation, and the general index remain enabled.
The provenance loader now reports a readable configuration error for a missing
file, invalid JSON/schema, or a malformed digest. It validates the *recorded
digest format*, not the authenticity or content of the referenced source.

## Authoring for both formats

- Put `:numbered:` on the main `toctree` if you want chapter/section numbers in
  HTML. `numfig` alone numbers captioned figures, tables, and listings.
- Give figures, tables, code blocks, and equations captions or labels; use
  `:numref:` and `:eq:` to reference them. Keep explicit labels for important
  normative clauses; heading-derived labels change when headings change.
- Use `.. container:: weave-lead` for a short introductory paragraph.
- Put landing-page navigation grids inside `.. only:: html`. Sphinx Design
  preserves their text in LaTeX, but a web card grid is not a PDF page layout.
  Keep the real `toctree` outside the conditional so all chapters enter the PDF.
- Reserve dropdowns for supplementary notes. Required language rules should
  remain visible. Tabs and dropdowns become ordinary visible content in PDF;
  their web appearance does not carry over.
- Add `:class: no-copybutton` to non-runnable output examples. Literal `$`,
  `>>>`, and `...` are never removed by a blanket prompt regular expression.
  Use the `console` lexer for shell transcripts so `.gp` and `.go` identify
  prompts and output; these and line numbers are excluded from copying.
- Use math roles/directives for notation. XeLaTeX and the selected fonts cover
  many Unicode symbols, but no font covers every glyph; inspect unusual syntax.
- Graphviz graphs are kept on a white surface in either browser theme so their
  independently rendered colours stay readable. Use `:alt:` for descriptions.
- For pre-existing SVG illustrations, supply matching PDF files and reference
  them as `.. image:: diagram.*`, letting each builder select a supported
  format. Graphviz-generated diagrams already handle this automatically.
- The LaTeX PDF is not a tagged, PDF/UA accessibility-certified document. The
  visual checks here are not a full accessibility audit.

### Offline equations

The default HTML configuration loads **MathJax 3.2.2** from jsDelivr only on
pages containing equations. An offline site or a restrictive CSP needs a
locally hosted copy. Download the official `mathjax@3.2.2` package, copy its
entire `es5/` directory (including fonts and dynamically loaded modules) to
`docs/_static/mathjax/es5/`, and retain its license. Then change:
<!-- docs-audit: planned docs/_static/mathjax/es5/ -- only exists if MathJax is vendored -->

```python
mathjax_path = "mathjax/es5/tex-mml-chtml.js"
```

Do not prefix this setting with `_static/`: Sphinx adds that prefix for local
JavaScript assets. The rest of the design uses installed system fonts and
bundled assets; it does not load web fonts.

## Validation

The bundle was originally smoke-tested in isolation (Python 3.12, synthetic
fixture). After integration with the real specification (Python 3.13.5,
pinned packages):

- `html`, `singlehtml`, `text`, and `latex` builders succeed with `-n -W`
  (warnings as errors), including all `weave-check` examples.
- `scripts/audit_html.py` reports no broken local links, anchors, or assets in
  either HTML edition, and every page carries the snapshot hash.
- `make validate-offline` passes.
- XeLaTeX compiles a 101-page PDF with no missing glyphs or unresolved
  references; the log has only minor overfull-box warnings from long code lines
  and page-spanning listings.

Not yet checked: external links (needs network), pagination review of the
complete PDF, and Furo's rendering on mobile with the real content.

## Primary references

- [Furo customization](https://pradyunsg.me/furo/customisation/)
- [Furo colour and syntax-highlighting configuration](https://pradyunsg.me/furo/customisation/colors/)
- [Sphinx LaTeX customization](https://www.sphinx-doc.org/en/master/latex.html)
- [Sphinx Graphviz extension](https://www.sphinx-doc.org/en/master/usage/extensions/graphviz.html)
- [Sphinx Copybutton configuration](https://sphinx-copybutton.readthedocs.io/en/latest/use.html)
- [Sphinx Design tabs](https://sphinx-design.readthedocs.io/en/latest/tabs.html)
