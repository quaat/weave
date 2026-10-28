Net declarations and contracts
====================================

.. index:: place, transition, ownership, sealed resource, foreign declaration

Places and ownership
--------------------------

A place declares its initial count and owner. In N0 it is unindexed. In N1 it is
either shared or indexed by two distinct variables.

.. weave-check::
   :expect: ACCEPT
   :profile: N1
   :context: net-fragment

   place available = stock owner domain
   place held[t, o] = 0 owner activation
   place inflight[t, o] = 0 owner runtime

These are N1 net-body fragments. Initial values are nonnegative literals or the
net parameter. For an indexed place, a constant applies to each colour; a shared
place has one count. All activation places begin at zero, since handles must be
issued by a transition.

.. list-table::
   :header-rows: 1

   * - Owner
     - Contract
   * - domain
     - Shared or durable protocol state; no activation handle required
   * - activation
     - Exactly one sealed resource type; issuer and consumers are validated
   * - runtime
     - Explicit closed consumer declaration required
   * - adapter
     - Adapter-owned bookkeeping; no automatic provider implementation

Owner labels establish validator rules. They do not by themselves implement
persistence, physical isolation, or distributed authority.

Resources and cancellation
--------------------------------

.. weave-check::
   :expect: ACCEPT
   :profile: N1
   :context: net-fragment

   linear Escrow[t, o] at escrow issuer arm cancel cancel_escrow registered registrations

.. _N0-DECL-1:

**N0-DECL-1.** The resource's issuer MUST be its only producing transition and produce exactly
one token per firing. Its registration, when present, MUST be runtime-owned and
be produced exactly once by that issuer in the same firing.

.. _N0-DECL-2:

**N0-DECL-2.** The cancellation transition MUST take one token from the associated place.
It MUST have no guards or read arcs, and MUST produce no activation-owned tokens.
Any additional consumed place must be an armed registration place. This removes
dependency on a second application handle; it is not a proof that every required
registration exists in all reachable states. Invariants and protocol structure
supply that evidence.

.. _N0-SEAL-1:

**N0-SEAL-1.** A resource may be consumed only by its cancellation route or by an exported
operation whose signature accounts for it. Read arcs over activation places are
rejected: the current language has no borrowing mechanism.

Runtime-owned state
-------------------------

.. weave-check::
   :expect: ACCEPT
   :profile: N1
   :context: net-fragment

   runtime_state inflight consumers charge_ok, charge_err, charge_unknown, cancel_inflight
   runtime_state results terminal
   runtime_cancel inflight via cancel_inflight

.. _N0-DECL-3:

**N0-DECL-3.** Every runtime place MUST have exactly one consumer declaration. Each listed
transition takes exactly one token from that place. Other consumers are rejected.
A terminal place has no consumers, but may still be read. A runtime cancellation
declaration uses the same structural cancellation restrictions as a resource.

Transitions
-----------------

Transitions contain positive-count take, read, and put arcs and named guards.
A duplicate arc of the same kind and place is invalid, even when it would
otherwise be meaningful to add its count. Different arc kinds may refer to the
same place. N1 arcs must supply exactly the arity declared by their place.

Every N1 transition has two distinct firing variables in tenant/order position.
Variables appearing in inscriptions retain their positional sort throughout the
transition. An extra order variable can describe a cross-order arc; the parser
does not automatically equate it with the firing order. Family proofs and the
token-correlation check detect relevant violations.

A transition must have a nonempty body. Arbitrary assignments, expressions,
inhibitor arcs, priorities, capacities in transition syntax, and timed arcs are
not supported.

Local APIs
----------------

.. weave-check::
   :expect: ACCEPT
   :profile: N1
   :context: net-fragment

   api arm(h: Hold[t, o]) -> Escrow[t, o] via arm

.. _N0-DECL-4:

**N0-DECL-4.** The signature's resource inputs, counted by backing place, MUST exactly account
for all activation-owned take arcs. Its resource output, if any, MUST account
for all activation-owned put arcs. An operation may also change domain, runtime,
or adapter state without returning handles to those places.

API parameters may be opaque scalars or resources; enum parameters are not
supported in net APIs. Result indices must be bound by parameters. The validator
checks activation counts and signatures; in N1 this shared check uses an erased
net projection. It must be read together with colour analysis, not mistaken for
a complete arbitrary-order API refinement theorem.

Foreign APIs
------------------

.. weave-check:: ../../examples/nets/Inventory.coloured.weave
   :expect: ACCEPT
   :profile: N1
   :start-at:     foreign Payments.charge
   :end-at:         outcome Unknown via charge_unknown

.. _N0-DECL-5:

**N0-DECL-5.** A foreign declaration MUST specify dispatch transition, runtime-owned pending
place, explicit key fields, the supported correlation clause, and all outcome
transitions. Dispatch requires exactly one linear permit with an armed recovery
registration. It consumes the permit, requires the registration through a read
or take arc, produces one pending token, and produces no activation handle.

The key fields equal the permit's declared index tuple and name explicit scalar
parameters. The result enum has exactly Ok, Err, and Unknown. Every outcome
takes one pending token and produces the resource prescribed by its case,
with the consumed permit's identity. Pending state requires a cancellation route.

The grammar fixes one correlation declaration; it does not define a network
protocol. See :doc:`effects` for evidence and runtime assumptions.

Invariants and check blocks
---------------------------------

An aggregate invariant contains one affine equality. A family invariant adds a
two-variable binder and refers to indexed places at that binder. Check blocks
declare a finite model, named guard classifications, and safety properties.
Their semantics are specified separately in :doc:`verification`.

