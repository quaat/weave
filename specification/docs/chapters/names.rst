Names, scope, and program structure
=========================================

.. index:: scope, name resolution, module, forward reference

Compilation units
-----------------------

An N0/N1 file contains exactly one net. An F0 file contains one or more flows,
checked against one explicitly selected net API environment. Net declarations
and flow declarations do not coexist in a source file. There is no import,
package, export modifier, include directive, or automatic module discovery.

The bundled teaching runner checks multiple flow files independently. Helpers
are not linked across files; related helpers must be in the same file.
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

