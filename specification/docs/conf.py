"""Weave specification: Furo HTML and a coordinated XeLaTeX PDF.

Keep this file beside your existing index.rst and _ext/ directory. Install the
companion _static/, _templates/, and _latex/ files as described in README.md.
"""

from pathlib import Path
import json
import os
import re
import sys

from sphinx.errors import ConfigError


DOCS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS_DIR / "_ext"))

# Project metadata ------------------------------------------------------------
project = "Weave"
author = "Danio project"
copyright = "2026, Danio project; distribution terms not specified"
version = "0.2"
release = "0.2-draft"
language = "en"
needs_sphinx = "8.2"
root_doc = "index"

# Authoring and validation ----------------------------------------------------
extensions = [
    "weave_lexer",
    "weave_check",
    "weave_singlehtml",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.mathjax",
    "sphinx.ext.graphviz",
    "sphinx_design",
    "sphinx_copybutton",
]
autosectionlabel_prefix_document = True
nitpicky = True
show_warning_types = True
smartquotes = False
templates_path = ["_templates"]
exclude_patterns = [
    "_build", "_build/**", "build", "build/**",
    ".venv", ".venv/**", "venv", "venv/**",
    "Thumbs.db", ".DS_Store", "README.md",
]

highlight_language = "weave"
pygments_style = "a11y-high-contrast-light"
pygments_dark_style = "a11y-high-contrast-dark"  # Furo-specific.

numfig = True
numfig_secnum_depth = 1
numfig_format = {
    "figure": "Figure %s",
    "table": "Table %s",
    "code-block": "Listing %s",
    "section": "Section %s",
}
math_numfig = True
math_eqref_format = "Eq. {number}"

# Keep the original provenance contract, with actionable errors. This checks
# the stored digest's format; it does not recompute or authenticate the source.
_provenance_path = DOCS_DIR.parent / "PROVENANCE.json"
try:
    _provenance = json.loads(_provenance_path.read_text(encoding="utf-8"))
    _reference_sha256 = _provenance["sources"][0]["sha256"]
except (OSError, UnicodeError, ValueError, KeyError, IndexError, TypeError) as exc:
    raise ConfigError(
        f"Cannot read provenance from {_provenance_path}. Expected a JSON "
        "object with a nonempty sources array and sources[0].sha256."
    ) from exc
if not isinstance(_reference_sha256, str) or not re.fullmatch(
    r"[0-9a-fA-F]{64}", _reference_sha256
):
    raise ConfigError("PROVENANCE.json: sources[0].sha256 must be a 64-digit hex SHA-256.")

# HTML -----------------------------------------------------------------------
html_theme = "furo"
html_title = "Weave language specification · Draft 0.2"
html_short_title = "Weave specification"
html_static_path = ["_static"]
html_css_files = ["weave.css"]
html_favicon = "_static/weave-favicon.svg"
html_show_sourcelink = True
html_copy_source = True
html_use_index = True
html_domain_indices = False
html_last_updated_fmt = None
html_permalinks_icon = "§"
html_search_language = "en"

# Furo supplies its own responsive sidebar and search. Do not carry over
# Alabaster's html_sidebars, fixed_sidebar, page_width, or sidebar_width.
html_theme_options = {
    "navigation_with_keys": False,
    "top_of_page_buttons": ["view"],
    "source_repository": "https://github.com/quaat/weave/",
    "source_branch": "main",
    "source_directory": "specification/docs/",
    "announcement": (
        "<strong>Draft 0.2</strong>"
        "<span class='weave-announcement-divider' aria-hidden='true'> / </span>"
        "Weave language specification"
    ),
    "light_css_variables": {
        "font-stack": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "font-stack--monospace": "'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
        "color-brand-primary": "#0b6b63",
        "color-brand-content": "#08645e",
        "color-foreground-primary": "#182c32",
        "color-foreground-secondary": "#465c60",
        "color-foreground-muted": "#51656a",
        "color-background-primary": "#fbfcfa",
        "color-background-secondary": "#f1f5f1",
        "color-background-hover": "#e7efea",
        "color-background-border": "#d6e1dc",
        "color-sidebar-background": "#f1f5f1",
        "color-sidebar-brand-text": "#182c32",
        "color-announcement-background": "#113d3b",
        "color-announcement-text": "#f3fcf8",
        "color-admonition-background": "#f1f5f1",
        "weave-code-background": "#ffffff",
        "weave-accent-soft": "#d9eee5",
        "weave-shadow": "0 8px 28px rgba(20, 55, 47, .055)",
    },
    "dark_css_variables": {
        "color-brand-primary": "#88dcc2",
        "color-brand-content": "#9fe6d0",
        "color-foreground-primary": "#e8f1ed",
        "color-foreground-secondary": "#b7cbc3",
        "color-foreground-muted": "#a1b7af",
        "color-background-primary": "#101b20",
        "color-background-secondary": "#16272c",
        "color-background-hover": "#20383b",
        "color-background-border": "#30484a",
        "color-sidebar-background": "#122127",
        "color-sidebar-brand-text": "#e8f1ed",
        "color-announcement-background": "#173f3d",
        "color-announcement-text": "#e8f6f0",
        "color-admonition-background": "#16272c",
        "weave-code-background": "#121212",
        "weave-accent-soft": "#1b3d38",
        "weave-shadow": "0 8px 28px rgba(0, 0, 0, .12)",
    },
}
html_context = {
    "reference_snapshot_sha256": _reference_sha256,
    "weave_tagline": "Functional Petri nets",
    # Search target for the single-page edition's sidebar box, relative to its
    # index.html. The published site sets "../search.html"; empty hides it.
    "weave_singlehtml_search_url": os.environ.get("WEAVE_SINGLEHTML_SEARCH_URL", ""),
}

# Copy tokens exactly: never strip '$', '>>>', or '...' using a blanket regex.
# Pygments-tagged console prompts/output and line numbers are excluded instead.
copybutton_exclude = ".linenos, .gp, .go"
copybutton_selector = "div:not(.no-copybutton) > div.highlight > pre"

# Pin the browser math runtime. For an offline site, vendor its FULL es5 tree
# under _static/mathjax/es5/ and use the local path documented in README.md.
mathjax_path = "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-mml-chtml.js"
mathjax3_config = {"tex": {"tags": "ams", "useLabelIds": True}}

# Vector output in HTML; Sphinx's Graphviz extension produces PDF for LaTeX.
graphviz_output_format = "svg"
graphviz_dot_args = [
    "-Gbgcolor=white", "-Gpad=0.25", "-Granksep=0.5",
    "-Nfontname=DejaVu Sans", "-Nfontsize=11",
    "-Ncolor=#0b6b63", "-Nfontcolor=#182c32", "-Npenwidth=1.4",
    "-Ecolor=#5a7974", "-Earrowsize=0.7",
]

# PDF: an independent, coordinated typesetting system -------------------------
latex_engine = "xelatex"
latex_documents = [
    (root_doc, "weave-specification.tex", "Weave language specification", author, "manual"),
]
latex_toplevel_sectioning = "chapter"
latex_show_pagerefs = True
latex_show_urls = "footnote"
latex_domain_indices = False
latex_use_xindy = False  # English index; makeindex is included in TeX Live.
latex_additional_files = ["_latex/weave.sty"]
latex_elements = {
    "papersize": "a4paper",
    "pointsize": "11pt",
    "cmappkg": "",  # XeLaTeX supplies Unicode mapping; cmap is for pdfLaTeX.
    "extraclassoptions": "oneside,openany",
    "geometry": r"\usepackage[margin=25mm,headheight=16pt,headsep=9mm,footskip=12mm]{geometry}",
    "fontpkg": r"""
\setmainfont{DejaVu Serif}
\setsansfont{DejaVu Sans}[Scale=MatchLowercase]
\setmonofont{DejaVu Sans Mono}[Scale=0.84]
""",
    "fncychap": "",
    "preamble": (
        r"\usepackage{weave}" + "\n"
        + r"\newcommand{\WeaveReferenceSnapshot}{" + _reference_sha256 + "}\n"
    ),
    "maketitle": r"\weavemaketitle",
    "tableofcontents": r"\sphinxtableofcontents",
    "sphinxsetup": ",".join([
        "TitleColor={RGB}{24,44,50}",
        "InnerLinkColor={RGB}{11,107,99}",
        "OuterLinkColor={RGB}{11,107,99}",
        "VerbatimColor={RGB}{243,247,244}",
        "VerbatimBorderColor={RGB}{214,225,220}",
        "VerbatimHighlightColor={RGB}{219,239,228}",
        "TableRowColorHeader={RGB}{225,237,230}",
        "TableRowColorOdd={RGB}{255,255,255}",
        "TableRowColorEven={RGB}{245,248,245}",
        "verbatimwithframe=true",
        "verbatimwrapslines=true",
        "verbatimforcewraps=true",
        "verbatimborder=0.5pt",
    ]),
}

# Link checking remains strict; add only narrowly justified exceptions.
linkcheck_timeout = 15
linkcheck_retries = 2
linkcheck_workers = 3
linkcheck_anchors = True
