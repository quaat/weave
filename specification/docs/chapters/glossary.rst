Glossary
==============

.. glossary::
   :sorted:

   Activation
      An invocation or executing owner of application-level linear handles.

   Affine invariant expression
      An integer linear combination of names plus a constant. Products of two
      variable-bearing expressions are outside the supported fragment.

   Colour
      A tenant/order pair distinguishing indexed token cells in N1.

   Closed enum
      A nominal type with an explicitly declared, exhaustive set of tags.

   Dispatch
      The transition transferring a foreign permit into pending runtime state.

   Evidence
      An abstract witness or recorded external fact used to justify a protocol
      transition. Its truthfulness is outside token accounting.

   Firing
      One atomic enabled transition step in the Petri-net model.

   Guard
      A named abstract condition associated with a transition.

   Identity index
      A symbolic argument on a resource or enum type identifying its protocol
      subject. It is not a generic type argument or arbitrary expression.

   Invariant family
      An accounting equality checked separately for every colour through symbolic
      inscription coefficients.

   Linear obligation
      A live handle or enum that must be moved or discharged on every normal exit.

   Marking
      The nonnegative token counts of all places, or all indexed place cells.

   P-invariant
      A place-weight vector whose product with the incidence matrix is zero.

   Permit
      A sealed resource required to request an operation.

   Projection
      The erased uncoloured view used for shared structural validation of an N1
      net. It does not replace identity-aware analysis.

   Recovery registration
      Runtime-owned state recording a recovery obligation associated with an
      armed protocol resource.

   Sealed resource
      A nominal handle with validated issuer and consumer restrictions.

   Terminal match
      An exhaustive match ending its containing block; every branch terminates.

   Unknown
      An explicit unresolved foreign outcome whose payload preserves a protocol
      obligation. It is not evidence of final failure.

   Unfolding
      A finite ordinary-net representation with a row per place/colour cell and
      a transition mode per supported variable binding.


   Admission
      Durable acceptance of a job under a protocol identity. In R0 admission
      records a job before source acknowledgement; reserve happens later.

   Generation
      An ownership epoch used to reject stale workers after cancellation or
      reassignment. It does not imply a real-time lease implementation.

   Lease
      Time-bounded authority to act, distinct from a hard execution deadline.
      General timed execution leases are a design concern, not implemented R0
      scheduling. The small Lease net models a resource slot without time.

   Pending place
      Runtime-owned protocol state holding an in-flight foreign obligation
      after dispatch and before an outcome or cancellation transition.

   Cancellation route
      The declared transition that transfers an abandoned activation or pending
      obligation to its state-appropriate non-activation owner.

   Firing mode
      A transition together with a complete, sort-consistent binding of its
      colour variables to concrete identities.

   Profile
      A named scope of language, analysis, or runtime requirements. F0/N0/N1
      describe implemented scopes; D0/N2 are new unimplemented targets.

   Witness
      Persistent historical evidence recorded by an abstract guard-class
      firing or a concrete operation ledger. Its truth requires an external contract.

   Aggregate invariant
      An equality about total place counts, summing over colours where applicable.
      Unlike an invariant family it need not distinguish individual identities.
