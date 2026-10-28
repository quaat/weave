Petri-net operational semantics
=====================================

.. index:: marking, enabledness, firing, read arc, colour, atomicity

Uncoloured markings
-------------------------

.. _NET-FIRE-1:

**NET-FIRE-1 — Atomic marking relation.** The following definitions specify
the normative token-enabledness and firing relation.

Let :math:`P` be the finite set of places and :math:`T` the transitions.
A marking :math:`M:P\to\mathbb{N}` assigns a nonnegative token count to each
place. Initial marking :math:`M_0` is obtained by substituting a nonnegative
stock parameter into each place's initial expression.

For transition :math:`t`, write :math:`I_t` for take counts, :math:`O_t` for put
counts, and :math:`R_t` for read requirements. Missing arcs have count zero.
Token enabledness is:

.. math::

   \operatorname{enabled}(M,t)
   \iff \forall p\in P,\;
   M(p)\ge I_t(p)\ \land\ M(p)\ge R_t(p).

The take and read requirements are tested independently on the pre-state.
If a place has both kinds of arc, the requirement is their maximum, not their
sum. A put arc cannot satisfy a read or take requirement in the same firing.

An enabled firing produces:

.. math::

   M'(p)=M(p)-I_t(p)+O_t(p).

Read arcs do not change counts. No partial firing is a language-level state.
All arc effects of one firing occur atomically in the net model. Runtime
atomicity must be implemented; it is not guaranteed by merely parsing the net.

Guards
------------

A named guard is an abstract predicate supplied by a model or execution
environment. No guard body or arbitrary expression is defined by the source
language. Full operational enabledness also requires all transition guards.

Accounting proofs relax guards completely. The bounded safety explorers
consider guard-enabled firings and omit false-guard stuttering steps.
Evidence-class guards update model flags when their transition fires. This is
an abstraction, not executable provider authentication.

The low-level ``Unfolding.enabled`` and ``Unfolding.fire`` functions check token
availability, not evidence truth. Their execution caller must enforce guard
conditions; R0 does so for its supported evidence and budget guards.

Coloured markings
-----------------------

N1 has two positional colour sorts: tenant and order. A colour is an ordered pair.
There is no user-declared arbitrary algebra of colours.

A shared place has one cell. An indexed place has one cell per colour in the
chosen domain. Write :math:`M(p,c)` for an indexed cell. An indexed initial literal
is a count per colour, not a total distributed among colours.

A transition declares a primary firing binder, for example ``[t, o]``.
An inscription such as ``registrations[t, other]`` selects a cell under a
binding :math:`\beta`. Variables may only appear in their positional sort.
A firing mode consists of a transition plus assignments to all its inscription
variables. Take, read, and put arcs are substituted before testing enabledness.

The equations above apply to each selected cell. Shared cells have no colour.
In the finite unfolding, the selected primary colour and every indexed arc cell
must belong to the declared colour set; impossible bindings are omitted.

Correlation is an additional safety property
--------------------------------------------------

Parsing a well-sorted inscription does not prove it uses the firing identity.
The property ``tokens match firing`` checks that every indexed take, read, and
put cell of every enabled mode has the primary firing colour.

This matters for read arcs: changing a registration read to another order may
leave the incidence matrix unchanged. Accounting alone cannot detect that
identity violation. The supplied coloured explorer checks correlation before
accepting a mode's successor.

Concurrent behaviour
--------------------------

The transition relation permits every enabled firing. The reference explores
interleavings of atomic single firings; it does not specify simultaneous-step
semantics, priorities, fairness, wall-clock timing, or a distributed scheduler.

Two transitions can contend for the same token. Static ownership of a handle
does not prove all additional domain/runtime inputs are available. A dead
marking, deadlock, or nonterminating protocol is not excluded by a conservation
invariant.

Bounds and resource exhaustion
------------------------------------

.. _NET-REQ-1:

**NET-REQ-1.** Place bounds are analysis limits, not source-level capacity guards that disable
a transition. An enabled successor exceeding the limit makes the analysis
inconclusive with a failure diagnostic. It MUST NOT be silently discarded.
Likewise, a state-budget limit MUST NOT be converted into a successful safety
result. See :doc:`verification` for profile-specific bounds.

