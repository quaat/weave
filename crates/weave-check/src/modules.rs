// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! modules-1: loading and resolving the modules of a P0 program
//! (`specification/docs/chapters/names.rst`, "P0 modules").
//!
//! A program has one project root: the directory given with `--root`, or else
//! the entry file's directory. The module path `geo.shapes` names the file
//! `<root>/geo/shapes.weave`; every import, at any depth, resolves from the
//! same root, never from the process's working directory.
//!
//! Loading is an explicit-stack depth-first walk from the entry module that
//! follows imports in source order (`MOD-CHECK-1`). It reads, parses and lowers
//! each module when it is first reached, and rejects, at the import that
//! names it:
//!
//! * a path with no module file (`MOD-RESOLVE-1`, E601);
//! * a path whose segments differ in case from the names on disk, even on a
//!   case-insensitive file system (`MOD-RESOLVE-2`, E602);
//! * a path that leaves the root once symbolic links are resolved
//!   (`MOD-RESOLVE-3`, E603);
//! * an import that closes a cycle (`MOD-CYCLE-1`, E604), with every import of
//!   the cycle as a related span;
//! * any import when there is no project root (`MOD-ROOT-1`, E605).
//!
//! A module is identified by its canonical file (`MOD-RESOLVE-4`): two routes
//! to one file (through a symbolic link inside the root) load one module.
//! Syntax inside a top-level line that begins with `from` is E600
//! (`MOD-FILE-1`); every other fault in a module keeps its P0 code.
//!
//! The walk never recurses, so a chain of any length of imports is bounded by
//! memory, not by the stack. The loaded modules are then checked in the walk's
//! post-order, every module after the modules it imports
//! ([`crate::check::Builder::check_module`]).

use crate::ast::FileAst;
use crate::check::Builder;
use crate::typed::{Program, SourceFile, Sources};
use std::collections::{HashMap, HashSet};
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use weave_syntax::diagnostic::PURE_SYNTAX_CODE;
use weave_syntax::{Diagnostic, FileId, Span, Start};

/// A malformed import declaration, or one after the first declaration.
pub const IMPORT_SYNTAX_CODE: &str = "E600";
/// No module file for an import path.
pub const NOT_FOUND_CODE: &str = "E601";
/// An import path whose case differs from the names on disk.
pub const CASE_CODE: &str = "E602";
/// An import path that leaves the project root.
pub const ESCAPE_CODE: &str = "E603";
/// An import cycle.
pub const CYCLE_CODE: &str = "E604";
/// No project root for an import, or an entry file outside the given root.
pub const ROOT_CODE: &str = "E605";

/// File extension of a module file.
pub const EXTENSION: &str = "weave";
/// The module name of an entry file that has no module path.
pub const ANONYMOUS_MODULE: &str = "<entry>";

/// The entry file of a check or run.
#[derive(Clone, Debug)]
pub struct Entry {
    /// The name diagnostics use for the entry file (as the user gave it).
    pub name: String,
    pub text: String,
    /// The file on disk; `None` for standard input.
    pub path: Option<PathBuf>,
}

/// The project root.
#[derive(Clone, Debug)]
pub struct Root {
    /// The root as the user gave it (or the entry's directory as given):
    /// imported modules are named by joining it with their relative path.
    pub display: PathBuf,
    /// The canonical root directory.
    pub canonical: PathBuf,
    /// Given with `--root`. Only an explicit root can exclude the entry
    /// (E605); the implicit root is the directory of the entry path as
    /// written, so it contains the entry even when the entry is a symbolic
    /// link to a file elsewhere.
    pub explicit: bool,
}

/// A rejected program: the first diagnostic and every file loaded before it,
/// so the diagnostic's spans can be located.
#[derive(Clone, Debug)]
pub struct Failure {
    pub diagnostic: Box<Diagnostic>,
    pub sources: Sources,
}

pub(crate) fn module_error(
    code: &'static str,
    message: impl Into<String>,
    span: Span,
) -> Diagnostic {
    Diagnostic::new(code, "module", message, span)
}

/// E605 at `span`: an import in a program without a project root.
pub fn no_root(span: Span) -> Diagnostic {
    module_error(
        ROOT_CODE,
        "This file has no project root, so it cannot import: give its directory with --root, or check it from a file.",
        span,
    )
}

/// Is `line` a top-level line whose first word is `word`?
fn starts_with_word(line: &str, word: &str) -> bool {
    line.strip_prefix(word)
        .is_some_and(|rest| !rest.starts_with(|c: char| c.is_ascii_alphanumeric() || c == '_'))
}

/// Does `text` use module-file syntax: a top-level line (no indentation)
/// whose first word is `from` or `export`? A file without one is read as a
/// P0 `pure-file`, exactly as by a P0 checker.
pub fn uses_module_syntax(text: &str) -> bool {
    text.lines()
        .any(|l| starts_with_word(l, "from") || starts_with_word(l, "export"))
}

/// Is byte `offset` of `text` on a top-level line whose first word is `from`?
fn on_import_line(text: &str, offset: usize) -> bool {
    let offset = offset.min(text.len());
    let start = text
        .get(..offset)
        .and_then(|before| before.rfind('\n'))
        .map_or(0, |i| i + 1);
    text.get(start..)
        .is_some_and(|line| starts_with_word(line, "from"))
}

/// Parse and lower one module's text in `file`. Faults keep their P0 codes,
/// except that a lexical or syntax fault on an import line is E600.
pub fn parse_module(text: &str, file: FileId) -> Result<FileAst, Diagnostic> {
    let module = uses_module_syntax(text);
    let start = if module {
        Start::ModuleFile
    } else {
        Start::PureFile
    };
    let parsed = weave_syntax::parse(text, start).map_err(|mut d| {
        if module
            && d.code == PURE_SYNTAX_CODE
            && matches!(d.stage, "lexical" | "syntax")
            && on_import_line(text, d.span.start)
        {
            d.code = IMPORT_SYNTAX_CODE;
            d.message = format!(
                "{} An import declaration is 'from a.b import x, y as z' on one line, before the first declaration.",
                d.message
            );
        }
        d.span = d.span.in_file(file);
        d
    })?;
    let mut cst = parsed;
    cst.set_file(file);
    crate::lower::lower(&cst)
}

/// One directory's names: as a set for exact lookup, and in a list for the
/// case-insensitive search that tells a case mismatch from a missing name.
type Listing = (HashSet<OsString>, Vec<OsString>);

/// Cached directory listings, by canonical directory; `None` when unreadable.
#[derive(Default)]
struct Listings {
    dirs: HashMap<PathBuf, Option<Listing>>,
}

enum Lookup {
    Found,
    Case(String),
    Missing,
}

impl Listings {
    fn lookup(&mut self, dir: &Path, name: &str) -> Lookup {
        let entry = self.dirs.entry(dir.to_path_buf()).or_insert_with(|| {
            std::fs::read_dir(dir).ok().map(|it| {
                let names: Vec<OsString> =
                    it.filter_map(|e| e.ok().map(|e| e.file_name())).collect();
                (names.iter().cloned().collect(), names)
            })
        });
        let Some((exact, names)) = entry else {
            return Lookup::Missing;
        };
        if exact.contains(&OsString::from(name)) {
            return Lookup::Found;
        }
        let lower = name.to_lowercase();
        match names
            .iter()
            .filter_map(|n| n.to_str())
            .find(|n| n.to_lowercase() == lower)
        {
            Some(n) => Lookup::Case(n.to_string()),
            None => Lookup::Missing,
        }
    }
}

/// Why an import path did not resolve.
enum Unresolved {
    Missing(String),
    Case { written: String, on_disk: String },
    Escapes(PathBuf),
}

/// Resolve the dotted path `segments` from `root` (`MOD-RESOLVE-1` to
/// `MOD-RESOLVE-3`): each segment must be the exact name of a directory, the
/// last with `.weave` the exact name of a file, and the directories and file
/// must canonicalise to paths inside the root.
fn resolve(root: &Root, segments: &[&str], listings: &mut Listings) -> Result<PathBuf, Unresolved> {
    let mut path = root.display.clone();
    let mut relative = PathBuf::new();
    let count = segments.len();
    for (i, segment) in segments.iter().enumerate() {
        let name = if i + 1 == count {
            format!("{segment}.{EXTENSION}")
        } else {
            (*segment).to_string()
        };
        // Listings are keyed by canonical directory.
        let dir = std::fs::canonicalize(&path).unwrap_or_else(|_| path.clone());
        match listings.lookup(&dir, &name) {
            Lookup::Found => {}
            Lookup::Case(on_disk) => {
                return Err(Unresolved::Case {
                    written: relative.join(&name).display().to_string(),
                    on_disk: relative.join(on_disk).display().to_string(),
                });
            }
            Lookup::Missing => return Err(Unresolved::Missing(expected(segments))),
        }
        path.push(&name);
        relative.push(&name);
        let canonical =
            std::fs::canonicalize(&path).map_err(|_| Unresolved::Missing(expected(segments)))?;
        if !canonical.starts_with(&root.canonical) {
            return Err(Unresolved::Escapes(relative.clone()));
        }
        let is_file = canonical.is_file();
        if (i + 1 == count) != is_file {
            return Err(Unresolved::Missing(expected(segments)));
        }
        if i + 1 == count {
            return Ok(canonical);
        }
    }
    Err(Unresolved::Missing(expected(segments)))
}

/// The relative file a dotted path names: `a/b/c.weave`.
fn expected(segments: &[&str]) -> String {
    format!("{}.{EXTENSION}", segments.join("/"))
}

/// The dotted module path of the canonical file `canonical` under `root`, or
/// `None` when it is not a `.weave` file inside the root.
fn module_name(root: &Root, canonical: &Path) -> Option<String> {
    let relative = canonical.strip_prefix(&root.canonical).ok()?;
    let stem = relative.with_extension("");
    if relative.extension()?.to_str()? != EXTENSION {
        return None;
    }
    let parts: Vec<&str> = stem
        .components()
        .map(|c| c.as_os_str().to_str())
        .collect::<Option<_>>()?;
    if parts.is_empty() {
        return None;
    }
    Some(parts.join("."))
}

struct Loaded {
    ast: FileAst,
    /// Module index of each import's target, filled while walking.
    targets: Vec<usize>,
}

/// The project root for `entry`: `explicit` (from `--root`) if given, else
/// the directory of the entry path as written (canonicalised, so the
/// directory of a symbolic link, not of its target); `None` for standard
/// input without `--root`.
/// An explicit root must be a directory, an `Err` with a message otherwise.
pub fn project_root(entry: &Entry, explicit: Option<&Path>) -> Result<Option<Root>, String> {
    let display = match (explicit, &entry.path) {
        (Some(dir), _) => dir.to_path_buf(),
        (None, Some(file)) => match file.parent() {
            Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
            _ => PathBuf::from("."),
        },
        (None, None) => return Ok(None),
    };
    let canonical = std::fs::canonicalize(&display)
        .map_err(|e| format!("cannot use {} as the project root: {e}", display.display()))?;
    if !canonical.is_dir() {
        return Err(format!(
            "the project root {} is not a directory",
            display.display()
        ));
    }
    Ok(Some(Root {
        display,
        canonical,
        explicit: explicit.is_some(),
    }))
}

/// Load, resolve and check the program whose entry is `entry`, with project
/// root `root` (see [`project_root`]).
pub fn check_program_from(entry: Entry, root: Option<Root>) -> Result<Program, Failure> {
    let mut sources = Sources::default();
    let entry_canonical = entry
        .path
        .as_ref()
        .and_then(|p| std::fs::canonicalize(p).ok());
    let entry_module = match (&root, &entry_canonical) {
        (Some(r), Some(c)) => module_name(r, c).or_else(|| {
            // An entry reached through a symbolic link out of an implicit
            // root is named by its path as written, in the root.
            let written = entry.path.as_ref()?;
            if r.explicit || written.extension()?.to_str()? != EXTENSION {
                return None;
            }
            Some(written.file_stem()?.to_str()?.to_string())
        }),
        _ => None,
    }
    .unwrap_or_else(|| ANONYMOUS_MODULE.to_string());
    sources.files.push(SourceFile {
        name: entry.name.clone(),
        text: entry.text.clone(),
        module: entry_module.clone(),
    });
    let fail = |diagnostic: Diagnostic, sources: Sources| Failure {
        diagnostic: Box::new(diagnostic),
        sources,
    };
    // Only a root given with --root can exclude the entry (MOD-ROOT-1).
    if let (Some(r), Some(c)) = (&root, &entry_canonical)
        && r.explicit
        && !c.starts_with(&r.canonical)
    {
        return Err(fail(
            module_error(
                ROOT_CODE,
                format!(
                    "The entry file is outside the project root {}.",
                    r.display.display()
                ),
                Span::at(0),
            ),
            sources,
        ));
    }
    let first = match parse_module(&entry.text, FileId::ENTRY) {
        Ok(ast) => ast,
        Err(d) => return Err(fail(d, sources)),
    };
    let mut names = vec![entry_module];
    let mut modules = vec![Loaded {
        targets: Vec::with_capacity(first.imports.len()),
        ast: first,
    }];
    let mut by_file: HashMap<PathBuf, usize> = HashMap::new();
    if let Some(c) = entry_canonical {
        by_file.insert(c, 0);
    }
    let mut listings = Listings::default();
    // The walk: a stack of (module, next import); `on_stack[m]` while m is open.
    let mut stack: Vec<(usize, usize)> = vec![(0, 0)];
    let mut on_stack = vec![true];
    let mut order = Vec::new();
    while let Some(&(m, next)) = stack.last() {
        let Some(import) = modules.get(m).and_then(|l| l.ast.imports.get(next)) else {
            order.push(m);
            if let Some(flag) = on_stack.get_mut(m) {
                *flag = false;
            }
            stack.pop();
            continue;
        };
        let span = import.path_span;
        let dotted = import.dotted();
        let segments: Vec<&str> = import.path.iter().map(|n| n.text.as_str()).collect();
        let Some(r) = &root else {
            return Err(fail(no_root(span), sources));
        };
        let canonical = match resolve(r, &segments, &mut listings) {
            Ok(c) => c,
            Err(Unresolved::Missing(rel)) => {
                return Err(fail(
                    module_error(
                        NOT_FOUND_CODE,
                        format!(
                            "No module '{dotted}': there is no file {rel} under the project root {}.",
                            r.display.display()
                        ),
                        span,
                    ),
                    sources,
                ));
            }
            Err(Unresolved::Case { written, on_disk }) => {
                return Err(fail(
                    module_error(
                        CASE_CODE,
                        format!(
                            "Module path '{dotted}' names {written}, but the file on disk is {on_disk}: module paths match file names exactly, in case too."
                        ),
                        span,
                    ),
                    sources,
                ));
            }
            Err(Unresolved::Escapes(rel)) => {
                return Err(fail(
                    module_error(
                        ESCAPE_CODE,
                        format!(
                            "Module '{dotted}' resolves through {} to a file outside the project root {}.",
                            rel.display(),
                            r.display.display()
                        ),
                        span,
                    ),
                    sources,
                ));
            }
        };
        let mut fresh = false;
        let target = match by_file.get(&canonical) {
            Some(&t) if on_stack.get(t).copied() == Some(true) => {
                // The cycle: the imports followed from t's frame to this one.
                let from = stack.iter().position(|(x, _)| *x == t).unwrap_or(0);
                let mut d = module_error(
                    CYCLE_CODE,
                    format!(
                        "Importing '{dotted}' here closes an import cycle; imports must not form a cycle."
                    ),
                    span,
                );
                let frames = stack.get(from..).unwrap_or(&[]);
                for (k, &(x, next)) in frames.iter().enumerate() {
                    // A lower frame has moved past the import it followed;
                    // the top frame is at the import that closes the cycle.
                    let i = if k + 1 == frames.len() {
                        next
                    } else {
                        next.saturating_sub(1)
                    };
                    if let Some(imp) = modules.get(x).and_then(|l| l.ast.imports.get(i)) {
                        let importer = names.get(x).map_or("?", String::as_str);
                        d = d.with_related(
                            "import",
                            format!("'{importer}' imports '{}'", imp.dotted()),
                            imp.path_span,
                        );
                    }
                }
                return Err(fail(d, sources));
            }
            Some(&t) => t,
            None => {
                let index = modules.len();
                let file = FileId(u32::try_from(index).unwrap_or(u32::MAX));
                let name = module_name(r, &canonical).unwrap_or_else(|| dotted.clone());
                let display = canonical
                    .strip_prefix(&r.canonical)
                    .map_or_else(|_| canonical.clone(), |rel| r.display.join(rel));
                let bytes = match std::fs::read(&canonical) {
                    Ok(b) => b,
                    Err(e) => {
                        return Err(fail(
                            module_error(
                                NOT_FOUND_CODE,
                                format!("Cannot read module '{dotted}': {e}."),
                                span,
                            ),
                            sources,
                        ));
                    }
                };
                let text = match String::from_utf8(bytes) {
                    Ok(t) => t,
                    Err(e) => {
                        let at = e.utf8_error().valid_up_to();
                        let lossy = String::from_utf8_lossy(e.as_bytes()).into_owned();
                        sources.files.push(SourceFile {
                            name: display.display().to_string(),
                            text: lossy,
                            module: name,
                        });
                        return Err(fail(
                            Diagnostic::new(
                                PURE_SYNTAX_CODE,
                                "lexical",
                                "The source is not valid UTF-8.",
                                Span::new(at, at + 1).in_file(file),
                            ),
                            sources,
                        ));
                    }
                };
                sources.files.push(SourceFile {
                    name: display.display().to_string(),
                    text: text.clone(),
                    module: name.clone(),
                });
                let ast = match parse_module(&text, file) {
                    Ok(ast) => ast,
                    Err(d) => return Err(fail(d, sources)),
                };
                by_file.insert(canonical, index);
                names.push(name);
                modules.push(Loaded {
                    targets: Vec::with_capacity(ast.imports.len()),
                    ast,
                });
                on_stack.push(true);
                fresh = true;
                index
            }
        };
        if let Some(l) = modules.get_mut(m) {
            l.targets.push(target);
        }
        if let Some(top) = stack.last_mut() {
            top.1 += 1;
        }
        if fresh {
            stack.push((target, 0));
        }
    }
    let mut builder = Builder::default();
    for m in order {
        let (Some(loaded), Some(name)) = (modules.get(m), names.get(m)) else {
            continue;
        };
        if let Err(d) = builder.check_module(m, name, &loaded.ast, &loaded.targets) {
            return Err(fail(d, sources));
        }
    }
    Ok(builder.finish(sources, names))
}
