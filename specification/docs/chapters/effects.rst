Foreign effects, evidence, and recovery
=============================================

.. index:: foreign effect, Unknown, idempotency, cancellation, evidence

Dispatch and outcome ownership
------------------------------------

A foreign operation requires an explicit resource permit. In the supplied
protocol, Payments.charge consumes Escrow, whose issuer also creates a recovery
registration. Dispatch transfers ownership into a runtime pending place.
An application cannot obtain an unrestricted charge operation from the declared
API environment.

Each permitted outcome consumes pending state and produces exactly one declared
resource. The returned enum carries that resource and the same identity.
The application must either handle the outcome or transfer the obligation.

.. list-table::
   :header-rows: 1

   * - Outcome
     - Payload in Inventory
     - Meaning and permitted continuation
   * - Ok
     - Paid
     - Authoritative paid evidence; sell or use the declared paid cancellation
   * - Err
     - Unpaid
     - Authoritative final rejection; release through the matching API
   * - Unknown
     - Uncertain
     - Unresolved external effect; preserve obligation and hand off to recovery

A timeout, missing reply, or lookup returning NotFound is not final rejection.
Releasing stock on that basis can conflict with a payment that later succeeds.
Unknown therefore has its own nominal state and recovery path.

Registration and cancellation
-----------------------------------

Arming escrow and its recovery registration in one transition avoids a modeled
state in which an armed permit exists without registration. Subsequent protocol
states preserve that relationship through the declared invariants.

Normal return never invokes cancellation automatically. Abnormal cancellation
is a separate runtime operation. Structural cancellation rules ensure the route
does not wait on a guard or read arc and transfers outputs to non-activation
owners. They do not define a universal cancellation stack or crash scheduler.

For an in-flight payment, cancellation preserves an unresolved recovery
obligation. For already paid evidence, the declared Inventory route commits the
sale. Recovery is state-sensitive; a single generic "undo" action is insufficient.

Keys and correlation
--------------------------

The foreign declaration identifies scalar key fields and an allowed correlation
contract. The type checker verifies that those fields equal the permit's index
tuple. It does not implement key serialization, retention, authentication, or
remote idempotency.

R0 uses a stable operation-kind prefix and tenant/order values to form its local
key. A repeated key with a conflicting request digest is rejected. Duplicate
attempts use the same provider record. These are concrete model behaviours;
the language does not prescribe a universal JSON wire format.

A production adapter would need an authenticated client-key echo or lookup,
plus recorded provider-reference aliases when available. An Unknown response
cannot require a provider reference that was never observed. Provider
truthfulness, retention horizons, account scope, and anti-replay controls remain
external contracts. General webhook authentication is not implemented.

Capabilities and the trust boundary
-----------------------------------------

Sealed resource constructors and private transitions restrict checked client
programs. They do not sandbox arbitrary Python or prevent an unrestricted
external network client from bypassing a protocol. A production capability
claim requires provider credentials and authority to be available only through
the enforcing adapter.

The selected net and its declarations are trusted inputs. Changing a guard's
classification, an API contract, or a safety property changes the specification
being checked. A proof about a maliciously weakened net is not a proof about the
original business requirement.

Effect composition
------------------------

Helpers propagate the permit and outcome contracts through their explicit types.
There is no general effect row, resumable algebraic handler, implicit error
union, automatic retry, or map_error operation in F0. Proposed abstract effect
providers are recorded in :doc:`proposals` and must not be presented as accepted
source.

