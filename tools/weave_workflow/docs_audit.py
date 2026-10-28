"""Offline documentation drift audit driven by ``docmap.json``.

Repository scope checks every managed document. Change scope (``--base``) adds
the checks that depend on what changed: the documentation impact list, the
changelog requirement, new or removed documents, moved boundary statements and
new uses of the protected evidence vocabulary.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict, dataclass, field
from pathlib import Path

DOCMAP_PATH = Path(__file__).resolve().parent / "docmap.json"
DOC_EXTS = {".md", ".rst", ".txt", ".py", ".json", ".weave", ".yml", ".yaml", ".toml", ".lark",
            ".sty", ".svg", ".pdf", ".html", ".css", ".bat", ".cfg", ".ini", ".sh", ".jsonl"}
MARKER_RE = re.compile(r"docs-audit:\s*(planned|external)\s+(.+?)(?:\s--\s.*?)?\s*(?:-->|$)", re.M)
GEN_BEGIN = "<!-- BEGIN GENERATED: docmap -->"
GEN_END = "<!-- END GENERATED: docmap -->"


@dataclass
class Finding:
    severity: str  # "error" blocks; "warning" needs review
    check: str
    path: str
    message: str


@dataclass
class AuditResult:
    scope: str
    head_sha: str | None
    findings: list[Finding] = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    @property
    def result(self) -> str:
        return "FAIL" if any(f.severity == "error" for f in self.findings) else "PASS"

    @property
    def error_count(self) -> int:
        return sum(f.severity == "error" for f in self.findings)

    def to_dict(self) -> dict:
        return {"result": self.result, "scope": self.scope, "head_sha": self.head_sha,
                "error_count": self.error_count, "counts": self.counts,
                "findings": [asdict(f) for f in self.findings]}


# ------------------------------------------------------------------ helpers


def glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def matches(path: str, patterns: list[str]) -> bool:
    return any(glob_re(p).match(path) for p in patterns)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def repo_files(repo: Path) -> list[str]:
    tracked = git(repo, "ls-files", "-z").split("\0")
    others = git(repo, "ls-files", "-z", "--others", "--exclude-standard").split("\0")
    return sorted({p for p in tracked + others if p and (repo / p).exists()})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_docmap(path: Path = DOCMAP_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def managed_docs(repo: Path, docmap: dict, files: list[str]) -> list[str]:
    hist = docmap["historical_documents"]["paths"]
    return [f for f in files if matches(f, docmap["managed_documents"]) and not matches(f, hist)]


def component_of(path: str) -> str | None:
    head = path.split("/", 1)[0]
    return head if head in {"inventory-proof", "agent-kit", "specification"} else None


# ------------------------------------------------------------------ repository checks


def check_paths(repo: Path, docmap: dict, docs: list[str], findings: list[Finding]) -> int:
    ignore = set(docmap["ignore_path_segments"])
    checked = 0
    for doc in docs:
        text = (repo / doc).read_text(encoding="utf-8")
        planned = marked(text)
        tokens = re.findall(r"``([^`\n]+)``|`([^`\n]+)`|\]\(([^)\s#]+)(?:#[^)]*)?\)", text)
        for groups in tokens:
            token = next(t for t in groups if t).strip()
            if not _path_like(token):
                continue
            norm = token.rstrip("/")
            if norm in planned or token in planned or set(norm.split("/")) & ignore:
                continue
            bases = [repo / Path(doc).parent]
            if component_of(doc):
                bases.append(repo / component_of(doc))
            for pattern, extra in docmap.get("path_bases", {}).items():
                if matches(doc, [pattern]):
                    bases += [repo / e for e in extra]
            bases.append(repo)
            if any((b / norm).exists() for b in bases):
                checked += 1
                continue
            first = norm.split("/")[0]
            ext = Path(norm).suffix
            if "/" in norm and not any((b / first).exists() for b in bases) and ext not in DOC_EXTS:
                continue  # not a repository path (e.g. owner/repo, Ok/Err)
            if "/" not in norm and ext not in DOC_EXTS:
                continue
            if "/" not in norm and not _repo_has_basename(repo, norm):
                findings.append(Finding("error", "path", doc, f"`{token}` does not exist (mark planned paths with a docs-audit: planned comment)"))
                continue
            if "/" in norm:
                findings.append(Finding("error", "path", doc, f"`{token}` does not exist (mark planned paths with a docs-audit: planned comment)"))
            checked += 1
    return checked


_BASENAMES: dict[Path, set[str]] = {}


def _repo_has_basename(repo: Path, name: str) -> bool:
    if repo not in _BASENAMES:
        _BASENAMES[repo] = {Path(p).name for p in repo_files(repo)}
    return name in _BASENAMES[repo]


def marked(text: str) -> set[str]:
    """Tokens declared as planned targets or external/historical paths by a docs-audit comment."""
    return {tok.strip() for m in MARKER_RE.finditer(text) for tok in m.group(2).split()}


def code_spans(text: str) -> list[str]:
    """Fenced and indented code blocks plus inline code spans (Markdown and reStructuredText)."""
    spans = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    spans += re.findall(r"(?m)^::\s*\n\n((?:[ \t]+.*\n|\n)+)", text)
    spans += re.findall(r"(?m)^\.\. code-block::.*\n(?:[ \t]+:.*\n)*\n((?:[ \t]+.*\n|\n)+)", text)
    spans += [a or b for a, b in re.findall(r"``([^`\n]+)``|`([^`\n]+)`", text)]
    return spans


def _path_like(token: str) -> bool:
    if token.startswith(("http:", "https:", "-", "$", "~", "<", "@", "/")) or " " in token:
        return False
    if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", token) or "*" in token or ".." in token:
        return False
    if token.startswith(".") and "/" not in token and token.count(".") == 1:
        return False  # a bare extension such as ".weave"
    return "/" in token or Path(token).suffix in DOC_EXTS


def _weave_subcommands(repo: Path, docmap: dict) -> set[str]:
    out = subprocess.run([sys.executable, *docmap["commands"]["weave.py"]["argv"]], cwd=repo,
                         capture_output=True, text=True).stdout
    m = re.search(r"\{([a-z,\-]+)\}", out)
    return set(m.group(1).split(",")) if m else set()


def _make_targets(repo: Path, docmap: dict) -> set[str]:
    cfg = docmap["commands"]["make"]
    text = (repo / cfg["makefile"]).read_text(encoding="utf-8")
    targets = set(re.findall(r"(?m)^([A-Za-z][\w-]*)\s*:(?!=)", text))
    return targets | set(cfg["sphinx_builders"])


def _cli_subcommands() -> set[str]:
    from .cli import build_parser
    parser = build_parser()
    for action in parser._actions:
        if action.choices and isinstance(action.choices, dict):
            return set(action.choices)
    return set()


def check_commands(repo: Path, docmap: dict, docs: list[str], findings: list[Finding]) -> int:
    weave = _weave_subcommands(repo, docmap)
    targets = _make_targets(repo, docmap)
    cli = _cli_subcommands()
    checked = 0
    for doc in docs:
        text = (repo / doc).read_text(encoding="utf-8")
        planned = marked(text)
        code = "\n".join(code_spans(text))
        for m in re.finditer(r"weave\.py\s+(?:--json\s+)?([a-z][a-z-]*)", text):
            checked += 1
            if m.group(1) not in weave and m.group(1) not in planned:
                findings.append(Finding("error", "command", doc, f"`weave.py {m.group(1)}` is not a weave.py subcommand"))
        for m in re.finditer(r"(?m)(?:^|&&|;|\$)[ \t]*make[ \t]+((?:[a-z][\w-]*[ \t]*)+)", code):
            for target in m.group(1).split():
                if "=" in target:
                    break
                checked += 1
                if target not in targets and target not in planned:
                    findings.append(Finding("error", "command", doc, f"`make {target}` is not a target of {docmap['commands']['make']['makefile']}"))
        for m in re.finditer(r"-m\s+tools\.weave_workflow\s+([a-z][a-z-]*)", text):
            checked += 1
            if m.group(1) not in cli and m.group(1) not in planned:
                findings.append(Finding("error", "command", doc, f"`tools.weave_workflow {m.group(1)}` is not a CLI subcommand"))
    return checked


def known_codes(repo: Path, docmap: dict, files: list[str]) -> set[str]:
    codes: set[str] = set()
    for f in files:
        if matches(f, docmap["diagnostic_code_sources"]):
            codes |= set(re.findall(r"\bE\d{3}\b", (repo / f).read_text(encoding="utf-8", errors="replace")))
    return codes


def check_codes(repo: Path, docmap: dict, docs: list[str], files: list[str], findings: list[Finding]) -> int:
    codes = known_codes(repo, docmap, files)
    checked = 0
    for doc in docs:
        for code in sorted(set(re.findall(r"\bE\d{3}\b", (repo / doc).read_text(encoding="utf-8")))):
            checked += 1
            if code not in codes:
                findings.append(Finding("error", "diagnostic", doc, f"{code} is not emitted by any checker or defined in rules.json"))
    return checked


def _iter_tests(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _iter_tests(t)
        else:
            yield t


def claim_value(repo: Path, source: dict) -> tuple[str, ...]:
    kind = source["type"]
    if kind == "unittest-count":
        base = repo / source["dir"]
        start = base / source["start"]
        sys.path[:0] = [str(base), str(start)]
        try:
            suite = unittest.TestLoader().discover(str(start), top_level_dir=str(start))
            broken = [t for t in _iter_tests(suite) if type(t).__name__ in ("_FailedTest", "ModuleImportFailure")]
            if broken:
                raise ValueError(f"test modules failed to import: {[str(t) for t in broken][:3]}")
            return (str(suite.countTestCases()),)
        finally:
            for p in (str(base), str(start)):
                sys.path.remove(p)
            for name in [n for n, m in sys.modules.items() if getattr(m, "__file__", "") and str(base) in str(m.__file__)]:
                del sys.modules[name]
    if kind == "file-regex":
        m = re.search(source["regex"], (repo / source["path"]).read_text(encoding="utf-8"))
        if not m:
            raise ValueError(f"source pattern not found in {source['path']}")
        return m.groups()
    if kind == "command-regex":
        out = subprocess.run([sys.executable, *source["argv"]], cwd=repo / source["cwd"],
                             capture_output=True, text=True, timeout=120).stdout
        m = re.search(source["regex"], out)
        if not m:
            raise ValueError(f"source pattern not found in output of {source['argv']}")
        return m.groups()
    raise ValueError(f"unknown claim source {kind}")


def check_claims(repo: Path, docmap: dict, findings: list[Finding]) -> int:
    checked = 0
    for claim in docmap["claims"]:
        try:
            value = tuple(v.replace(",", "") for v in claim_value(repo, claim["source"]))
        except Exception as exc:  # noqa: BLE001 - reported, never ignored
            findings.append(Finding("error", "claim", claim["id"], f"cannot compute source value: {exc}"))
            continue
        for occ in claim["occurrences"]:
            doc = repo / occ["doc"]
            text = doc.read_text(encoding="utf-8") if doc.exists() else ""
            found = list(re.finditer(occ["regex"], text))
            if not found:
                findings.append(Finding("error", "claim", occ["doc"], f"claim {claim['id']}: anchor /{occ['regex']}/ not found; update the document or docmap.json"))
                continue
            for m in found:
                checked += 1
                stated = tuple(g.replace(",", "") for g in m.groups())
                if stated != value:
                    findings.append(Finding("error", "claim", occ["doc"], f"claim {claim['id']}: document states {stated}, artefact gives {value}"))
    return checked


def check_synced(repo: Path, docmap: dict, findings: list[Finding]) -> int:
    checked = 0
    for pair in docmap["synced_copies"]:
        a, b = repo / pair["a"], repo / pair["b"]
        checked += 1
        if not (a.exists() and b.exists()) or a.read_bytes() != b.read_bytes():
            findings.append(Finding("error", "synced-copy", pair["b"], f"differs from {pair['a']}"))
    for man in docmap["provenance_manifests"]:
        data = json.loads((repo / man["manifest"]).read_text(encoding="utf-8"))
        for rel, expected in data[man["key"]].items():
            checked += 1
            path = repo / man["base"] / rel
            if not path.exists():
                findings.append(Finding("error", "provenance", man["manifest"], f"{man['base']}/{rel} is missing"))
            elif sha256(path) != expected:
                findings.append(Finding("error", "provenance", man["manifest"], f"{man['base']}/{rel} hash differs from the manifest"))
    return checked


def check_generated(repo: Path, docmap: dict, findings: list[Finding], only: set[str] | None = None) -> int:
    checked = 0
    for gen in docmap["generated_documents"]:
        if only is not None and not set(gen["paths"]) & only:
            continue
        check = gen["check"]
        checked += 1
        if check["type"] == "command":
            proc = subprocess.run([sys.executable, *check["argv"]], cwd=repo / check["cwd"], capture_output=True, text=True)
            if proc.returncode != 0:
                findings.append(Finding("error", "generated", ", ".join(gen["paths"]),
                                        f"differs from generator output; regenerate with `{gen['generator']}`"))
        elif check["type"] == "regenerate-in-copy":
            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / "copy"
                shutil.copytree(repo / check["dir"], copy, ignore=shutil.ignore_patterns("__pycache__"))
                proc = subprocess.run([sys.executable, *check["argv"]], cwd=copy, capture_output=True, text=True, timeout=300)
                if proc.returncode != 0:
                    findings.append(Finding("error", "generated", check["dir"], f"generator failed: {proc.stderr.strip()[-300:]}"))
                    continue
                for rel in gen["paths"]:
                    name = Path(rel).relative_to(check["dir"])
                    if (copy / name).read_bytes() != (repo / rel).read_bytes():
                        findings.append(Finding("error", "generated", rel, f"differs from generator output (hand-edited or stale); regenerate with `{gen['generator']}`"))
        elif check["type"] == "identical":
            if (repo / check["source"]).read_bytes() != (repo / gen["paths"][0]).read_bytes():
                findings.append(Finding("error", "generated", gen["paths"][0], f"differs from {check['source']}; regenerate with `{gen['generator']}`"))
        elif check["type"] == "docs-map":
            doc = repo / gen["paths"][0]
            if not doc.exists() or render_docs_map(docmap) not in doc.read_text(encoding="utf-8"):
                findings.append(Finding("error", "generated", gen["paths"][0], f"generated section is stale; regenerate with `{gen['generator']}`"))
    return checked


def render_docs_map(docmap: dict) -> str:
    """The generated section of docs/development/documentation-map.md."""
    lines = [GEN_BEGIN, "", "### Impact rules", "",
             "| Rule | Artefact changed | Triggered by | Documents that must be updated | How claims are verified |",
             "| --- | --- | --- | --- | --- |"]
    for r in docmap["impact_rules"]:
        req = list(r["require"]) + [f"{k} (when {', '.join(v)} change)" for k, v in r.get("conditional", {}).items()]
        lines.append(f"| `{r['id']}` | {r['artefact']} | {', '.join(f'`{w}`' for w in r['when'])} | "
                     f"{', '.join(f'`{d}`' for d in req)} | {r['verified_by']} |")
    nr = docmap["new_or_removed_document_rule"]
    lines.append(f"| `new-or-removed-doc` | {nr['artefact']} | added or deleted managed documents | "
                 f"{', '.join(f'`{d}`' for d in nr['require'])} | audit compares the change to this map |")
    lines += ["", "### Managed documents", ""] + [f"- `{p}`" for p in docmap["managed_documents"]]
    lines += ["", "### Historical records (not claim-checked)", ""] + [f"- `{p}`" for p in docmap["historical_documents"]["paths"]]
    lines += ["", "### Generated documents (regenerate, never hand-edit)", "",
              "| Documents | Generator |", "| --- | --- |"]
    for g in docmap["generated_documents"]:
        lines.append(f"| {', '.join(f'`{p}`' for p in g['paths'])} | `{g['generator']}` |")
    lines += ["", "### Synced copies and provenance", ""]
    lines += [f"- `{p['b']}` is identical to `{p['a']}`" for p in docmap["synced_copies"]]
    lines += [f"- every file in `{m['manifest']}` → `{m['key']}` hashes to its recorded SHA-256 under `{m['base']}/`"
              for m in docmap["provenance_manifests"]]
    lines += ["", "### Verified claims", "", "| Claim | Source of truth | Documents |", "| --- | --- | --- |"]
    for c in docmap["claims"]:
        src = c["source"]
        where = src.get("path") or src.get("dir") or " ".join(src.get("argv", []))
        docs = ", ".join(sorted({"`" + o["doc"] + "`" for o in c["occurrences"]}))
        lines.append(f"| `{c['id']}` | {src['type']}: `{where}` | {docs} |")
    lines += ["", GEN_END]
    return "\n".join(lines)


# ------------------------------------------------------------------ change checks


def changed_files(repo: Path, base: str) -> dict[str, str]:
    """Map path -> status (A, M, D, R) between base and the working tree, including untracked."""
    out: dict[str, str] = {}
    for line in git(repo, "diff", "--name-status", "-M", base).splitlines():
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R":
            out[parts[1]] = "D"
            out[parts[2]] = "A"
        else:
            out[parts[1]] = status
    for p in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        out[p] = "A"
    return out


def diff_lines(repo: Path, base: str, path: str) -> tuple[list[str], list[str]]:
    if not (repo / path).exists():
        return [], []
    try:
        text = git(repo, "diff", "-U0", base, "--", path)
    except subprocess.CalledProcessError:
        return [], []
    if not text and path in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        return (repo / path).read_text(encoding="utf-8").splitlines(), []
    added = [l[1:] for l in text.splitlines() if l.startswith("+") and not l.startswith("+++")]
    removed = [l[1:] for l in text.splitlines() if l.startswith("-") and not l.startswith("---")]
    return added, removed


def required_documents(docmap: dict, changes: dict[str, str]) -> dict[str, list[str]]:
    """Documentation impact: required document -> rule ids that require it."""
    req: dict[str, list[str]] = {}
    documents = set(docmap["managed_documents"]) | {d for r in docmap["impact_rules"] for d in r["require"]}
    for rule in docmap["impact_rules"]:
        triggers = [p for p in changes if matches(p, rule["when"]) and not matches(p, sorted(documents))]
        if not triggers:
            continue
        for doc in rule["require"]:
            if "{component}" in doc:
                for t in triggers:
                    comp = component_of(t)
                    if comp:
                        req.setdefault(doc.replace("{component}", comp), []).append(rule["id"])
            else:
                req.setdefault(doc, []).append(rule["id"])
        for doc, when in rule.get("conditional", {}).items():
            if any(matches(p, when) for p in changes):
                req.setdefault(doc, []).append(rule["id"])
    return req


def audit(repo: Path, docmap: dict | None = None, base: str | None = None, impact: list[dict] | None = None) -> AuditResult:
    docmap = docmap or load_docmap()
    head = None
    try:
        head = git(repo, "rev-parse", "HEAD").strip()
    except subprocess.CalledProcessError:
        pass
    result = AuditResult(scope="change" if base else "repository", head_sha=head)
    files = repo_files(repo)
    docs = managed_docs(repo, docmap, files)
    f = result.findings
    result.counts["managed_documents"] = len(docs)
    result.counts["paths"] = check_paths(repo, docmap, docs, f)
    result.counts["commands"] = check_commands(repo, docmap, docs, f)
    result.counts["diagnostic_codes"] = check_codes(repo, docmap, docs, files, f)
    result.counts["claims"] = check_claims(repo, docmap, f)
    result.counts["synced_and_provenance"] = check_synced(repo, docmap, f)
    result.counts["generated"] = check_generated(repo, docmap, f)
    if base:
        _change_checks(repo, docmap, base, impact, result)
    return result


def _change_checks(repo: Path, docmap: dict, base: str, impact: list[dict] | None, result: AuditResult) -> None:
    f = result.findings
    changes = changed_files(repo, base)
    result.counts["changed_files"] = len(changes)
    required = required_documents(docmap, changes)
    declared = {i["path"]: i for i in (impact or []) if not i["path"].startswith("(")}  # "(…)" marks computed entries
    for doc, rules in sorted(required.items()):
        if doc in changes:
            continue
        item = declared.get(doc)
        if item and item.get("status") == "not-applicable" and item.get("justification"):
            continue
        f.append(Finding("error", "impact", doc, f"required by {', '.join(sorted(set(rules)))} but not updated and not justified as not applicable"))
    for doc, item in declared.items():
        if item.get("status") in ("required", "added-by-implementer") and doc not in changes:
            f.append(Finding("error", "impact", doc, "listed in the documentation impact but not updated"))
    for rule in docmap["impact_rules"]:
        log = rule.get("changelog")
        if log and any(rule["id"] in r for r in required.values()):
            added, _ = diff_lines(repo, base, log)
            if not (repo / log).exists():
                f.append(Finding("error", "changelog", log, "changelog required but missing"))
            elif not [l for l in added if l.strip()]:
                f.append(Finding("error", "changelog", log, "no changelog entry for this change"))
    hist = docmap["historical_documents"]["paths"]
    doc_like = [p for p, s in changes.items() if s in "AD" and (matches(p, docmap["managed_documents"]) or matches(p, hist))]
    if doc_like:
        for need in docmap["new_or_removed_document_rule"]["require"]:
            if need not in changes:
                f.append(Finding("error", "doc-map", need, f"documents added or removed ({', '.join(sorted(doc_like))}) but the documentation map was not updated"))
    boundary = docmap["boundary"]
    authoritative = docmap["protected_vocabulary"]["authoritative"]
    flagged: set[tuple[str, str]] = set()
    for path, status in sorted(changes.items()):
        if status == "D" or not matches(path, docmap["managed_documents"]) or matches(path, hist):
            continue
        added, removed = diff_lines(repo, base, path)
        if not matches(path, ["specification/**"]):
            moved = [l for l in removed if re.search(boundary["phrases"], l)]
            if moved:
                missing = [p for p in boundary["requires"] if p not in changes]
                if missing:
                    f.append(Finding("error", "boundary", path,
                                     f"boundary statement removed ({moved[0].strip()[:80]!r}) without updating {', '.join(missing)}"))
        if not matches(path, authoritative):
            for line in added:
                for label in docmap["protected_vocabulary"]["labels"]:
                    if re.search(rf"\b{re.escape(label)}\b", line) and (path, label) not in flagged:
                        flagged.add((path, label))
                        f.append(Finding("warning", "vocabulary", path, f"new use of protected label {label}: review that it carries the specification's meaning"))
    gen_changed = {p for p in changes if any(p in g["paths"] for g in docmap["generated_documents"])}
    if gen_changed:
        result.counts["generated_changed"] = len(gen_changed)
