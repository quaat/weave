PYTHON ?= python3
SPHINXOPTS ?= -n -W --keep-going

.PHONY: html singlehtml text latex latexpdf linkcheck grammar-audit validate validate-offline diagrams clean
html singlehtml text latex linkcheck:
	$(PYTHON) -m sphinx $(SPHINXOPTS) -b $@ docs _build/$@
latexpdf:
	$(PYTHON) -m sphinx -M latexpdf docs _build $(SPHINXOPTS)
grammar-audit:
	$(PYTHON) scripts/grammar_audit.py
validate: validate-offline linkcheck
validate-offline:
	$(PYTHON) scripts/validate.py
	$(PYTHON) scripts/grammar_audit.py
	$(PYTHON) scripts/refresh_reference_pages.py --check
	$(PYTHON) -B -m unittest discover -s tests -q
	$(PYTHON) scripts/test_reference.py
	$(PYTHON) -m sphinx $(SPHINXOPTS) -b html docs _build/html
	$(PYTHON) scripts/audit_html.py _build/html
diagrams:
	$(PYTHON) scripts/render_diagrams.py
	$(PYTHON) scripts/diagrams_to_pdf.py
clean:
	rm -rf _build
