Types and values
======================

.. index:: type; nominal, type; identity index, Unit, outcome enum

Type universe
-------------------

F0 distinguishes three operational categories:

.. list-table::
   :header-rows: 1

   * - Category
     - Examples
     - Use
   * - Opaque scalar
     - ``TenantId``, ``OrderId``, ``Money``
     - Parameters and call arguments; reusable symbolic values
   * - Linear resource
     - ``Hold[t, o]``, ``Paid[t, o]``
     - Move-only handle to a declared activation-owned state
   * - Linear enum
     - ``ChargeOutcome[t, o]``
     - One declared tag with a resource or Unit payload
   * - Unit
     - ``Unit``
     - Result with no resource obligation

The first three rows are value categories; Unit is the distinguished empty
result type. The spelling of an undeclared, unindexed scalar type is accepted
nominally in parameters. There is no scalar declaration, representation, range,
serialization, or arithmetic defined for it. In particular, ``Money`` is not a
built-in decimal currency type.

``Nat`` is the special net-parameter sort. It denotes a nonnegative integer
initial-count parameter. A scalar parameter named with the type spelling
``Nat`` does not gain arithmetic operations in F0.

Nominality and equality
-----------------------------

Types are equal exactly when their names and ordered identity-index tuples are
equal after signature substitution. For example, ``Paid[t, o]`` is distinct from
``Unpaid[t, o]``; ``Hold[t, o1]`` is distinct from ``Hold[t, o2]`` when those are
different symbols. There is no structural equivalence, inheritance, subtyping,
implicit coercion, union widening, overload, trait, or type alias.

Indices are not generic type arguments. ``Hold[tenant, order]`` denotes one
nominal resource indexed by identities, not a container parameterized by types.
The grammar does not permit nested types such as ``List[Hold[t, o]]``.

Resources
---------------

A resource declaration defines its name, ordered index arity, backing place,
unique issuer transition, and cancellation route. It may associate a runtime
registration place. Every activation-owned place has exactly one resource type.

.. _TYPE-REQ-1:

**TYPE-REQ-1.** Client code MUST NOT construct a resource. It obtains handles from declared API
results, foreign outcomes, parameters, or helper returns. A handle is neither an
integer token count exposed to the program nor a copyable record.

The type checker tracks liveness separately from lexical scope. A resource can
be transferred through many bindings over time, but each live binding may be
consumed only once. All normal exit paths must transfer or discharge it.

Enums
-----------

An enum is nominal, closed, and indexed. Each case carries exactly one declared
resource type or ``Unit``. Nested enums and arbitrary scalar payloads are not
supported. The payload's indices must come from the enum binder and have the
resource's declared arity.

.. weave-check::
   :expect: ACCEPT
   :profile: N1
   :context: net-fragment

   enum ChargeOutcome[t, o]:
       Ok(Paid[t, o])
       Err(Unpaid[t, o])
       Unknown(Uncertain[t, o])

This declaration is a net-body fragment. The entire enum value is linear,
including a value whose selected payload is Unit. Matching or returning an enum
moves it. Closed enums make residual obligations explicit; Unknown cannot
silently disappear under a generic error value.

A local net API returns a resource or Unit. A foreign API returns the required
three-case enum. A flow can return a resource, enum, or Unit, but cannot return
an opaque scalar in this fragment.

Unit values
-----------------

A flow with no return annotation returns Unit. ``return`` produces Unit.
An enum case with a Unit payload is constructed with ``return Ok()`` and matched
using ``Ok():``. The reference also permits binding Unit call results or Unit
payloads, but they do not carry a linear obligation.

Unit is not a permitted parameter type in flow or net API signatures. There is
no standalone Unit literal, null, undefined, optional value, or exception object.

Substitution
------------------

For a call to ``arm(h: Hold[t, o]) -> Escrow[t, o]`` with an argument of type
``Hold[a, b]``, infer the substitution ``t ↦ a, o ↦ b`` and obtain
``Escrow[a, b]``. Every occurrence of an index variable must agree.

Scalar identity arguments are compared by their symbolic binding identity.
Two distinct scalar parameters are not assumed equal even if a real caller
might supply equal runtime values. The checker has no theorem prover for value
equality and does not establish identity freshness or uniqueness merely from
indices. N1 identity tokens and runtime admission records address separate
protocol properties.

