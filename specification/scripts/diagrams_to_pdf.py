#!/usr/bin/env python3
"""Write a PDF companion beside each SVG diagram for the LaTeX/PDF builder.

HTML uses the SVG and LaTeX uses the PDF; chapters reference ``diagram.*``.
Requires ``cairosvg`` (``python -m pip install cairosvg``) and the Cairo library.
"""
from pathlib import Path
import cairosvg
ROOT=Path(__file__).resolve().parents[1]

def main():
    for svg in sorted((ROOT/"docs/_static/diagrams").glob("*.svg")):
        cairosvg.svg2pdf(url=str(svg),write_to=str(svg.with_suffix(".pdf")))
        print(svg.with_suffix(".pdf").relative_to(ROOT))

if __name__=="__main__":main()
