Sources, provenance, and change history
=============================================

Source hierarchy
----------------------

The specification is grounded in these project artifacts, inspected on
28 October 2026:

.. list-table::
   :header-rows: 1
   :widths: 25 45 30

   * - Artifact
     - Role
     - Treatment
   * - weave-inventory-proof.zip, version 3
     - Current parser, checker, coloured analyser, durable model, tests, nets
     - Primary implementation baseline
   * - weave-agent-kit.zip
     - Older version-2 teaching guide, examples, manifest, runner conventions
     - Teaching examples rechecked against version 3
   * - claude-code-weave-merge-sort.md
     - Proposed pure-function and fork/join implementation task
     - Proposal only; no implementation claim
   * - claude-code-tiny-shop.md
     - Application brief for the restricted effectful language
     - Context; no additional accepted syntax

The agent kit's statement that no durable runtime exists describes its older
bundled snapshot. Version 3 adds a narrow process-crash model. Conversely,
version 3 does not implement the later merge-sort brief's pure functions or
scheduler. This document reconciles those boundaries explicitly.

The exact original archive checksums and byte-level hashes of included reference
files are recorded in ``PROVENANCE.json``. Included reference files retain their
original bytes. Python caches are excluded from the delivered snapshot.

Traceability
------------------

.. list-table::
   :header-rows: 1

   * - Specification area
     - Primary source anchors under reference/prototype
   * - Lines, indentation, types
     - ``checker.py: tree, split_commas, type_of, parameters``
   * - Net grammar and ownership
     - ``checker.py: parse_net, validate``
   * - Aggregate arithmetic
     - ``checker.py: linear_expression, prove``
   * - F0 signatures and moves
     - ``checker.py: check_flow, apply_call, check_body``
   * - Question-mark transformation
     - ``checker.py: lower_questions, lower_flow_source``
   * - N0 ordering
     - ``checker.py: explore_order``
   * - N1 parsing and families
     - ``coloured.py: parse_coloured, prove_colours``
   * - Coloured firing and search
     - ``coloured.py: Unfolding, explore_colours``
   * - Scripted F0 execution
     - ``simulate.py: simulate``
   * - Crash model
     - ``durable.py: Provider, Runtime, run_crash_cases``
   * - Negative language and protocol cases
     - ``tests/test_checker.py``, ``test_composition.py``,
       ``test_rejection_and_propagation.py``, ``test_coloured.py``
   * - Recovery acceptance
     - ``tests/test_durable.py``

Function names are stable reading anchors for this snapshot, not a published
Python API. This package's scripts import them solely for reproducibility.

Distribution status
-------------------------

The Weave-authored specification sources and the Weave-authored portions of its
built editions, the reference prototype snapshot and the teaching kit are
released under the MIT License, Copyright (c) 2026 Thomas F. Hagelien. The
license text is in ``LICENSE`` at the root of the
`project repository <https://github.com/quaat/weave>`_. The PDF cover and the
HTML footer print the same copyright line, taken from one Sphinx setting.

Third-party material, including theme code in the HTML editions and fonts
embedded in PDF files, keeps its own copyright and terms. ``REUSE.toml`` at the
repository root records licensing per path without changing the bytes of the
reference snapshot. The third-party material and its notices are listed in
:ref:`chapters/provenance:Third-party notices` below; the repository's
``follow-up`` record lists the remaining release items.

Third-party notices
-------------------------

The Weave MIT grant does not cover the third-party material below; each item keeps
its own copyright and licence. This section is part of every edition (HTML,
single page, PDF and text), so the notices and licence texts travel with each
edition. In the repository, ``REUSE.toml`` records the same terms per file and
``LICENSES/`` holds the licence texts.

Fonts embedded in PDF files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Identified from the font names in the PDFs, the fonts' own name tables and
notices, and, for the diagrams, glyph outlines identical to DejaVu Sans 2.37.
The built PDF embeds the fonts installed where it is built; the versions below
come from a local build with DejaVu 2.37 and TeX Live 2024.

.. list-table::
   :header-rows: 1
   :widths: 22 12 26 18 22

   * - Font
     - Version
     - Embedded in
     - Licence (SPDX)
     - Copyright
   * - DejaVu Sans, DejaVu Sans Bold
     - 2.35, 2.37
     - design specimen PDF, the three diagram PDFs, the built PDF
     - Bitstream-Vera AND LicenseRef-Arev-Fonts
     - 2003 Bitstream, Inc.; 2006 Tavmjong Bah (Arev glyphs); DejaVu changes are
       in the public domain
   * - DejaVu Sans Mono, DejaVu Serif, DejaVu Serif Bold, DejaVu Serif Italic
     - 2.35, 2.37
     - design specimen PDF, the built PDF
     - Bitstream-Vera
     - 2003 Bitstream, Inc.; DejaVu changes are in the public domain
   * - Computer Modern and AMS symbol fonts, AMS Type 1 release (CMR, CMMI,
       CMSY, CMEX, MSBM)
     - 003.002
     - design specimen PDF, the built PDF
     - OFL-1.1-RFN
     - 1997, 2009 American Mathematical Society, with Reserved Font Names

Bitstream Vera is a trademark of Bitstream, Inc.

Theme and Sphinx files in the HTML editions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Both HTML editions copy these files into their static directories. Versions are
pinned in ``requirements.txt``; licences and holders are from each package's
installed licence file. "Notice in file" says whether the shipped file itself
carries its notice.

.. list-table::
   :header-rows: 1
   :widths: 20 24 14 24 18

   * - Component and version
     - Files
     - Licence (SPDX)
     - Copyright
     - Notice in file
   * - Furo 2025.12.19
     - furo.css, furo-extensions.css, furo.js, furo-extensions.js, their source
       maps, furo.js.LICENSE.txt
     - MIT
     - 2020 Pradyun Gedam
     - No
   * - normalize.css 8.0.1, bundled in furo.css
     - furo.css
     - MIT
     - Nicolas Gallagher and Jonathan Neal
     - Licence name and URL
   * - gumshoe 5.1.2, patched, bundled in furo.js
     - furo.js
     - MIT
     - "(c) 2019 Chris Ferdinandi", as shipped; the upstream licence file names
       Go Make Things, LLC
     - Yes, in furo.js.LICENSE.txt
   * - sphinx-basic-ng 1.0.0b2
     - skeleton.css, debug.css
     - MIT
     - 2021 Pradyun Gedam
     - No
   * - Sphinx 8.2.3
     - basic.css, doctools.js, searchtools.js, sphinx_highlight.js,
       language_data.js (with Sphinx's own Porter stemmer),
       documentation_options.js, graphviz.css, file.png, minus.png, plus.png
     - BSD-2-Clause
     - 2007-2025 the Sphinx team
     - No
   * - sphinx-design 0.7.0
     - sphinx-design.min.css, design-tabs.js
     - MIT
     - 2023 Chris Sewell
     - No
   * - sphinx-copybutton 0.5.2
     - copybutton.js, copybutton.css, copybutton_funcs.js, copy-button.svg,
       check-solid.svg
     - MIT
     - 2018 Chris Holdgraf
     - No
   * - clipboard.js 2.0.8, shipped with sphinx-copybutton
     - clipboard.min.js
     - MIT
     - Zeno Rocha
     - Yes
   * - Pygments 2.21.0 and accessible-pygments 0.0.5
     - pygments.css, generated by Pygments from the accessible-pygments
       high-contrast styles
     - BSD-2-Clause AND BSD-3-Clause
     - 2006-2022 the Pygments authors; 2022 Quansight Labs
     - No

MathJax 3.2.2 is loaded from a CDN when a page with equations is viewed; the
editions do not contain it. Python packages that run only during the build are
not redistributed.

Licence texts
~~~~~~~~~~~~~~~~~~~~~~

Bitstream Vera Fonts licence (Bitstream-Vera):

.. literalinclude:: ../../../LICENSES/Bitstream-Vera.txt
   :language: text

Arev Fonts licence (LicenseRef-Arev-Fonts), as stated in the DejaVu Sans name
table:

.. literalinclude:: ../../../LICENSES/LicenseRef-Arev-Fonts.txt
   :language: text

SIL Open Font License 1.1 (OFL-1.1-RFN):

.. literalinclude:: ../../../LICENSES/OFL-1.1-RFN.txt
   :language: text

MIT License, as used by sphinx-copybutton (Copyright (c) 2018 Chris Holdgraf),
normalize.css (Copyright © Nicolas Gallagher and Jonathan Neal), clipboard.js
(Copyright (c) Zeno Rocha) and gumshoe (see above); the permission notice and
disclaimer are:

.. literalinclude:: ../../../LICENSES/MIT.txt
   :language: text
   :lines: 5-

Furo:

.. code-block:: text

   Copyright (c) 2020 Pradyun Gedam <mail@pradyunsg.me>

   Permission is hereby granted, free of charge, to any person obtaining a copy
   of this software and associated documentation files (the "Software"), to
   deal in the Software without restriction, including without limitation the
   rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
   sell copies of the Software, and to permit persons to whom the Software is
   furnished to do so, subject to the following conditions:

   The above copyright notice and this permission notice shall be included in
   all copies or substantial portions of the Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
   FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE
   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
   FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
   IN THE SOFTWARE.

sphinx-basic-ng:

.. code-block:: text

   Copyright (c) 2021 Pradyun Gedam <mail@pradyunsg.me>

   Permission is hereby granted, free of charge, to any person obtaining a copy
   of this software and associated documentation files (the "Software"), to
   deal in the Software without restriction, including without limitation the
   rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
   sell copies of the Software, and to permit persons to whom the Software is
   furnished to do so, subject to the following conditions:

   The above copyright notice and this permission notice shall be included in
   all copies or substantial portions of the Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
   FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE
   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
   FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
   IN THE SOFTWARE.

sphinx-design:

.. code-block:: text

   MIT License Copyright (c) 2023 Chris Sewell

   Permission is hereby granted, free
   of charge, to any person obtaining a copy of this software and associated
   documentation files (the "Software"), to deal in the Software without
   restriction, including without limitation the rights to use, copy, modify, merge,
   publish, distribute, sublicense, and/or sell copies of the Software, and to
   permit persons to whom the Software is furnished to do so, subject to the
   following conditions:

   The above copyright notice and this permission notice
   (including the next paragraph) shall be included in all copies or substantial
   portions of the Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF
   ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
   MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
   EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
   OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
   FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
   THE SOFTWARE.

Sphinx:

.. code-block:: text

   Unless otherwise indicated, all code in the Sphinx project is licenced under the
   two clause BSD licence below.

   Copyright (c) 2007-2025 by the Sphinx team (see AUTHORS file).
   All rights reserved.

   Redistribution and use in source and binary forms, with or without
   modification, are permitted provided that the following conditions are
   met:

   * Redistributions of source code must retain the above copyright
     notice, this list of conditions and the following disclaimer.

   * Redistributions in binary form must reproduce the above copyright
     notice, this list of conditions and the following disclaimer in the
     documentation and/or other materials provided with the distribution.

   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
   "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
   LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
   A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
   HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
   LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
   DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
   THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
   OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Pygments:

.. code-block:: text

   Copyright (c) 2006-2022 by the respective authors (see AUTHORS file).
   All rights reserved.

   Redistribution and use in source and binary forms, with or without
   modification, are permitted provided that the following conditions are
   met:

   * Redistributions of source code must retain the above copyright
     notice, this list of conditions and the following disclaimer.

   * Redistributions in binary form must reproduce the above copyright
     notice, this list of conditions and the following disclaimer in the
     documentation and/or other materials provided with the distribution.

   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
   "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
   LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
   A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
   OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
   LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
   DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
   THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
   OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

accessible-pygments:

.. code-block:: text

   BSD 3-Clause License

   Copyright (c) 2022, Quansight Labs
   All rights reserved.

   Redistribution and use in source and binary forms, with or without
   modification, are permitted provided that the following conditions are met:

   1. Redistributions of source code must retain the above copyright notice, this
      list of conditions and the following disclaimer.

   2. Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.

   3. Neither the name of the copyright holder nor the names of its
      contributors may be used to endorse or promote products derived from
      this software without specific prior written permission.

   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
   AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
   IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
   DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
   FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
   DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
   SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
   CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
   OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
   OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Change history
--------------------

0.1-draft — 28 October 2026
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Initial specification package: consolidated grammar; lexical and static rules;
flow and net semantics; effects and recovery; exact proof/bounded-check scope;
diagnostics; implementation-discrepancy register; proposals separated from
supported syntax; Sphinx sources, checked examples, provenance, and build evidence.


Draft 0.2 — 28 October 2026
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Responds to the specification review: D-01/D-02 decisions, D0 identity and waiting
contract, N2 declared-evidence direction, explicit N0/N1 protocol differences,
F0 inference rules and stable IDs, centralized syntax constraints, generated
grammar audit, normative conformance appendix, checked inline documentation,
rationale/history/security, lease tutorial, SVG figures, trace walkthroughs,
R0 acceptance table, footer hash and build hygiene. The original prototype is
unchanged. The four earlier design drafts remain unavailable; their chronology
is not invented.
