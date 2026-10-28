#!/usr/bin/env python3
"""Audit local HTML links, assets and pinned snapshot footers."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import argparse
import json

ROOT=Path(__file__).resolve().parents[1]

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=set()
        self.duplicates=set()
        self.links=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if "id" in attrs:
            if attrs["id"] in self.ids:self.duplicates.add(attrs["id"])
            self.ids.add(attrs["id"])
        if tag=="a" and "name" in attrs:self.ids.add(attrs["name"])
        for attr in ("href","src"):
            if attr in attrs:self.links.append(attrs[attr])

def audit(folder):
    pages={}
    expected=json.loads((ROOT/"PROVENANCE.json").read_text())["sources"][0]["sha256"]
    errors=[]
    count=0
    for p in folder.rglob("*.html"):
        parser=Page()
        content=p.read_text(encoding="utf-8")
        parser.feed(content)
        pages[p.resolve()]=parser
        for id in sorted(parser.duplicates):errors.append(f"Duplicate ID in {p.name}: {id}")
        if expected not in content:errors.append(f"Missing snapshot footer: {p}")
    for path,page in pages.items():
        for href in page.links:
            url=urlsplit(href)
            if url.scheme or url.netloc:continue
            count+=1
            target=(path.parent/unquote(url.path)).resolve() if url.path else path
            if target.is_dir():target=target/"index.html"
            if not target.exists():
                errors.append(f"{path.name}: absent target {href}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                errors.append(f"{path.name}: absent anchor {href}")
    return {"pages":len(pages),"local_links_and_assets":count,"errors":errors,
            "snapshot_footer_sha256":expected}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("folder",nargs="?",type=Path,default=ROOT/"_build/html")
    args=ap.parse_args()
    result=audit(args.folder.resolve())
    print(json.dumps(result,indent=2))
    raise SystemExit(bool(result["errors"]))

if __name__=="__main__":main()

