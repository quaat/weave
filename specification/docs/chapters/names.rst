Names, scope, and program structure
=========================================

.. index:: scope, name resolution, module, forward reference

Compilation units
-----------------------

An N0/N1 file contains exactly one net. An F0 file contains one or more flows,
checked against one explicitly selected net API environment: the ``--net``
argument of the checking tool, or the file's ``use net`` header (`Net selection
(use net)`_). Net declarations and flow declarations do not coexist in a source
file. Flow and net files have no import, package, export modifier, include
directive, or automatic module discovery.

The bundled teaching runner checks multiple flow files independently. Helpers
are not linked across files; related helpers must be in the same file.

P0 code may span several files: the modules-1 extension (`P0 modules
(modules-1)`_) gives P0 module files with selective imports and exports,
resolved from one project root.
The net name qualifies local APIs: ``api arm(...) ...`` in ``Inventory`` creates
the operation name ``Inventory.arm``. A foreign declaration supplies its own
qualified name, such as ``Payments.charge``.

Declaration namespaces
----------------------------

Places, transitions, resources, enums, invariants, APIs, and flows have distinct
roles. Duplicate names within a declaration map are rejected. Enum names cannot
collide with resource names or ``Unit``; flow names cannot collide with declared
resource/enum names or ``Unit``. Enum case names are local to their enum and may
recur across enums. Return constructors are resolved from the declared result
enum; match tags are resolved from the scrutinee's enum.

**Editorial portability rule:** reserve ``Unit`` and ``Nat`` against resource
or enum redefinition, and do not give a helper the same operation name as an API
or foreign declaration. The reference does not enforce every cross-category
collision. Its API/helper dictionary merge is an implementation detail, not an
overload resolution rule. Reusing an unqualified spelling for an API and its
transition, as in ``api arm(...) ... via arm``, is valid: the API is resolved as
``Inventory.arm`` and the transition belongs to a separate namespace.

Names do not overload by arity or type. A net transition is private unless an API
or foreign declaration exposes it. Calling a transition name directly is not a
general escape hatch.

Local scope
-----------------

Parameters enter a flow's scope before its body is checked. A binding introduced
by ``let`` is visible in subsequent statements. Names cannot be shadowed, including
names of already moved bindings. Every branch receives the environment at the
match, with the scrutinee moved; the payload is bound only in that branch.

Branch scopes do not join because matches are terminal. There are no closures,
captures, global values, mutable locals, tuple destructuring, or local function
declarations.

Identity variables
------------------------

Indices in a signature are symbolic names, not runtime expressions. A resource
parameter can bind identity variables even when no corresponding scalar
parameter appears. In ``arm(h: Hold[t, o]) -> Escrow[t, o]``, ``t`` and ``o`` are
inferred from the actual handle.

A scalar parameter may supply an identity name: ``tenant: TenantId`` binds the
symbol ``tenant``. A result may mention only identity variables bound by parameters.
Identity variables do not create ordinary value bindings that can be passed as
arguments.

Declaration order
-----------------------

The checker registers flow signatures before checking bodies. Forward helper
references work, and unused helpers are checked. It then rejects every cycle in
the helper call graph, including self-recursion and mutual recursion.

Net structural validation resolves references after collecting declarations.
Declarations should be ordered for readers: places, ownership, enums, invariants,
checks, transitions, and API contracts. This is a style recommendation, not a
requirement to declare a transition before its API.

P0 modules (modules-1)
----------------------------

.. index:: modules-1, module, import, export, project root, symbol identity

**modules-1** is a versioned extension of P0 (:doc:`pure`) adopted by the
maintainer's decision on quaat/weave#12. It lets a P0 program consist of several
files: a module selectively imports the exported functions and records of other
modules of the same project. It adds the rule IDs ``MOD-*`` below and the
diagnostic codes E600 to E619 (E600 to E610 are used). It changes no P0 rule,
code or meaning: a P0 file without imports or ``export`` is checked and run
exactly as before, and a P0 error inside an imported module keeps its E5xx code
and its ``P0-*`` rule. Its conformance corpus is ``examples/modules/manifest.json``
(format ``weave-modules-conformance-v1``, :doc:`conformance`); the corpora of F0,
N0, N1 and P0 are unchanged (:doc:`stability`).

The implementation is the Rust ``weave`` command (``crates/weave-cli``, with
``crates/weave-check``): ``weave check FILE [--root DIR]`` and ``weave run FILE
--entry NAME [--root DIR]``. The Python P0 reference evaluator implements P0 only;
modules-1 is not part of the P0 differential.

modules-1 has no cross-project imports, package manifest, lockfile or search path
(quaat/weave#13), no protocol packages (quaat/weave#19), no composition of nets
(quaat/weave#91), no qualified calls, no wildcard imports, no re-exports and no
opaque types (:doc:`limitations`).

Module files
~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../grammar/weave.ebnf
   :language: text
   :start-at: (* modules-1 module files
   :caption: modules-1 productions of the portable grammar
   :name: listing-modules-grammar

.. _MOD-FILE-1:

**MOD-FILE-1 — Module-file syntax.** A modules-1 file MUST be derived from the
start symbol ``module-file`` (:ref:`SYN-01 <SYN-01>`): zero or more import
declarations ``from a.b import x, y as z``, each on one line, before the first
declaration, then one or more P0 declarations, each optionally marked
``export``. ``from``, ``import``, ``as``, ``export`` and ``use`` are contextual
words (:ref:`LEX-REQ-2 <LEX-REQ-2>`) and remain valid names. A file in which no
top-level line (a line without indentation) begins with the word ``from`` or
``export`` is read with the start symbol ``pure-file``, exactly as by a P0
checker. A lexical or syntax fault located on a top-level line that begins with
``from`` (a malformed import, a wildcard, a ``..`` or ``/`` in a path, or an
import after the first declaration) is E600; every other fault is reported as
in a pure file (E500, :ref:`P0-FILE-1 <P0-FILE-1>`, or E001). A module path is
dotted identifiers, so ``..``, absolute paths and other file-system syntax cannot
be written.

Project root and module paths
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. _MOD-ROOT-1:

**MOD-ROOT-1 — One project root.** A program has one project root: the directory
given with ``--root``, or else the directory of the entry path as written,
canonicalised. For an entry that is a symbolic link, that is the directory of the
link, not of its target. Every import, in every module at any depth, resolves from
that root; the working directory of the process never takes part. Only a root
given with ``--root`` can exclude the entry: an entry file whose canonical path is
outside it is E605. The entry is never outside the implicit root, so an entry
without imports is checked and run exactly as by P0, wherever its target lies. An
import in a file that has no root (standard input without ``--root``) is also
E605. A ``--root`` that is not an existing directory is a usage error of the
command, not a diagnostic.

.. _MOD-RESOLVE-1:

**MOD-RESOLVE-1 — Module files.** The module path ``a.b.c`` names the file
``<root>/a/b/c.weave``: each segment but the last a directory, the last with
``.weave`` a regular file. A path that names no such file (a missing file, or a
directory where a file is required) is E601 at the path.

.. _MOD-RESOLVE-2:

**MOD-RESOLVE-2 — Exact case.** Each segment MUST equal the name of its
directory or file on disk exactly, compared by the names the directory lists. A
segment that matches only when case is ignored is E602, on every file system,
case-insensitive ones included, so a program resolves alike everywhere.

.. _MOD-RESOLVE-3:

**MOD-RESOLVE-3 — Inside the root.** Every directory on the path and the file
itself, once symbolic links are resolved, MUST lie inside the canonical project
root; otherwise E603. A symbolic link that stays inside the root is allowed.

.. _MOD-RESOLVE-4:

**MOD-RESOLVE-4 — One file, one module.** A module is identified by the
canonical path of its file (symbolic links resolved). Two routes to the same
canonical path (for example through a symbolic link inside the root, or a module
imported by several modules) load one module, checked once. Identity is the path,
not the file's contents or its inode: two hard links to one file have different
canonical paths and load as two modules, whose records are different types. A
module's path is its canonical path relative to the canonical root, with ``/``
written as ``.`` and without ``.weave``. The entry file's module path is formed
the same way; an entry that is a symbolic link out of an implicit root is named
by its path as written, the link's name without ``.weave``; an entry without a
module path (standard input, or a file not named ``.weave``) is ``<entry>``.

Imports and exports
~~~~~~~~~~~~~~~~~~~~~~~~~

.. _MOD-IMPORT-1:

**MOD-IMPORT-1 — Selective imports.** Each name in ``from m import ...`` MUST be
a function or record declared in module ``m`` itself (E606). There are no
wildcard imports and no re-exports: a name that ``m`` imports is not declared by
``m`` and cannot be imported from it.

.. _MOD-IMPORT-2:

**MOD-IMPORT-2 — Exports.** Only a declaration marked ``export`` can be imported
(E607). ``export`` changes nothing else: an exported declaration is checked and,
for a function, evaluated exactly like an unexported one. ``export`` is allowed
on any declaration, the run entry included.

.. _MOD-EXPORT-1:

**MOD-EXPORT-1 — No exposed private records.** A record named in the parameter
or result types of an exported function, or in the field types of an exported
record, also through ``List``, MUST itself be exported (E609, at the type). An
imported record is exported by the module that declares it, so it may appear in
any exported signature. A record that is not exported may still appear in
unexported declarations and in bodies. Opaque types are a separate design.

Name resolution
~~~~~~~~~~~~~~~~~~~~~

.. _MOD-NAME-1:

**MOD-NAME-1 — One namespace per module.** The top-level names of a module are
its own declarations and the names its imports introduce: the alias after ``as``,
or else the imported name. P0 has one namespace (:ref:`P0-DECL-1 <P0-DECL-1>`),
so these names are resolved exactly as P0 resolves the declarations of a file,
with no precedence between them: an import name that equals a built-in name,
another import name of the module, or a declaration of the module is E608, at the
import name. Importing one declaration twice
under different aliases is allowed. Because imported names are top-level names,
a parameter or ``let`` binding with the same name would shadow one and is E506
(:ref:`P0-NAME-2 <P0-NAME-2>`). Imported names are used unqualified, as in
``area(r)`` and ``Rect(width: 1, height: 2)``; ``geo.area(r)`` is still a
qualified call and E512 (:ref:`P0-EFFECT-1 <P0-EFFECT-1>`). Field access on an
imported record is unchanged.

.. _MOD-IDENT-1:

**MOD-IDENT-1 — Declaration identity.** Every function and record resolves to a
symbol: its package, its module path and its declared name. In modules-1 the
package is always the local project; quaat/weave#13 adds packages to the symbol
without changing the rest. Two records are the same nominal type exactly when
their symbols are equal: ``a.Point`` and ``b.Point`` are different types even
when their fields are equal, and one record imported under two aliases is one
type. A name inside a function's body is resolved in the module that declares
the function, so an imported function calls its own module's private helpers,
whatever names the importing module declares. Diagnostics spell a record by its
declared name, qualified with its module path when another record of the program
has the same name.

Cycles and checking
~~~~~~~~~~~~~~~~~~~~~~~~~

.. _MOD-CYCLE-1:

**MOD-CYCLE-1 — Acyclic imports.** The import graph MUST be acyclic. An import
that closes a cycle, a module importing itself included, is E604 at that import,
with one related span (role ``import``) for every import of the cycle, in order
from the first module of the cycle, so every location is shown. Since a call or a
field type can only name what is imported, a call cycle or a record cycle through
two or more modules always needs an import cycle and is rejected by this rule;
within one module, :ref:`P0-REC-1 <P0-REC-1>` (direct recursion only) and
:ref:`P0-DECL-3 <P0-DECL-3>` (no recursive records) apply as in a pure file.

.. _MOD-CHECK-1:

**MOD-CHECK-1 — Loading and checking order.** Loading starts at the entry
module and walks the imports depth first, in source order, reading, parsing and
lowering each module when it is first reached; resolution faults (E601 to E605),
syntax faults and cycles are reported at the first import, in this order, that
meets them. The loaded modules are then checked in the walk's post-order, each
module after the modules it imports. Within a module the order is: its
declaration names (:ref:`P0-DECL-1 <P0-DECL-1>`); its imports, name by name in
source order (E606, E607, E608); P0's records, record depth and signatures
(:doc:`pure`, "Checking order"); the export rule (E609) in file order; the bodies;
and mutual recursion among its functions. Every declaration of every loaded module
is checked, exported or not, used or not (:ref:`P0-DECL-4 <P0-DECL-4>`). The first
violation is reported. The nesting limits of :doc:`pure` apply to each file;
the type-depth limit applies to every record, whichever module declares it.
Loading and checking walk the import graph with explicit stacks, never by
recursion, so the number and depth of imports is bounded by memory, not by the
stack: a chain of 10,000 modules is checked (``crates/weave-check/tests/modules.rs``).

.. _MOD-RUN-1:

**MOD-RUN-1 — Running a program.** A run calls a function declared in the entry
file, exported or not; a name that is only imported there is an unknown entry
(E540, :ref:`P0-RUN-1 <P0-RUN-1>`). Evaluation is P0 evaluation (:doc:`pure`):
each call runs the body of the called symbol, in its own module, under the run's
one set of budgets. A fault or an exhausted budget is reported at the expression
that caused it, in the file that contains it.

Diagnostics in several files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every span of a module, from parsing through checking to evaluation, carries the
identity of its file, so each ``weave-diagnostic-v1`` document's ``span.file`` and
``related[].span.file`` name the file the location is in: the entry file as given
on the command line, an imported module as the root as given joined with the
module's path. ``weave check`` states one ``CHECKED pure`` claim per loaded file,
the entry first.

The corpus project ``examples/modules/shapes/`` is a small example: ``main.weave``
imports ``area`` and the record ``Rect`` (as ``R``) from ``geo/shapes.weave`` and
``scale`` from ``geo/units.weave``; ``geo.shapes`` exports ``Rect`` and ``area``,
keeps its helper ``product`` private, and imports ``geo.units`` too, which is
loaded once (cases M101 and M201 in :doc:`conformance`). The documentation build
displays only examples it can check itself, and it has no modules-1 checker, so
these files are not reproduced here; ``scripts/modules_conformance.py`` checks
them through the ``weave`` command.

Net selection (use net)
-----------------------------

.. index:: use net, net selection

.. _MOD-NET-1:

**MOD-NET-1 — Net selection.** A flow file MAY begin with the header ``use net
a.b`` (``use-net`` in :doc:`grammar`), before its first flow; blank and comment
lines may precede it. The header selects ``<root>/a/b.weave`` as the flow's net,
exactly as the ``--net`` argument does, with the root and the path rules of
modules-1 (:ref:`MOD-ROOT-1 <MOD-ROOT-1>` to :ref:`MOD-RESOLVE-3
<MOD-RESOLVE-3>`, E601 to E603, at the path); the root is ``--root``, or else the
flow file's directory. A first line that begins with ``use`` but is not such a
header is E600. A ``--net`` argument that names another net than the header is
E610; one that names the same file is accepted. The header selects one existing
net and nothing else: it is not checking of flows by the Rust tools, not
composition of nets or protocols (quaat/weave#91), not a protocol package
(quaat/weave#19), and it does not let flows call P0 functions.

A flow with a header is checked by the agent kit's runner,
``python3 scripts/weave.py check|lower|simulate FILE [--root DIR] [--net NET]``
(``agent-kit/.agents/skills/weave/scripts/weave.py``), whose backend is the
pinned Python prototype checker (F0). The runner resolves the header, then hands
the prototype the flow with the header line replaced by a blank line, so every
other line and column, and therefore every F0 diagnostic location, is that of the
file as written. The files of one command must select one net. ``lower`` copies
the header into its output only when the header, resolved from the output's root
(``--root``, or else the output file's directory), selects the same canonical net
file the flow was checked against; otherwise the output has a blank line in its
place, so the lowered lines are the same either way and the output never selects
another net, or none, by accident. In both cases the result names the selected
net (text and JSON), so the output can be checked with ``--net``. The prototype itself, without the runner, rejects the
header as E200, as it rejects any line it does not know (grammar probe SD-13 in
:doc:`grammar`). The Rust ``weave`` command checks P0 only and does not read flow
files.

