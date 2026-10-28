Reference execution and durable model
===========================================

.. index:: runtime, durability, crash recovery, fencing, admission

Two execution paths
-------------------------

The snapshot contains an in-memory F0 simulator and a file-backed
Inventory-specific protocol driver. Neither is a general production runtime.

The synchronous simulator executes checked and lowered F0 against the legacy
net. Its entry parameters are scalar, stock is one, and at most one foreign
operation is allowed per scenario. Ok, Err, or Unknown is supplied by the caller.
It does not drain the adapter request queue, so a request token may remain.

R0 instead invokes operations on the parsed coloured net. It uses
``Unfolding.fire`` for the actual token updates and checks evidence and accounting.
It does not execute an arbitrary F0 continuation or prove compiler correctness
for all checked flows.

Transactions and records
------------------------------

R0 stores domain marking, jobs, operations, results, and event history in one
SQLite database. A separate SQLite database represents the scripted provider.
Connections use WAL and synchronous=FULL. Domain and provider commits are
separate; no distributed transaction is implied.

Admission commits a job record before acknowledging the source. Repeated
admission with the same key/payload resumes the existing job; a conflicting
payload is rejected. The subsequent start transaction fires reserve, arm, and
dispatch as appropriate. Admission-record insertion and reserve are therefore
distinct steps in this implementation.

Starting consumes an identity token and a shared worker-pool credit through the
net's reserve transition. Each completion produces one result token, marks the
job completed, returns its credit, and writes the result record atomically.
A later resolution updates an Unknown result under the same identity without
issuing another completion or credit.

Evidence and duplicate handling
-------------------------------------

The operation ledger correlates receipts to the operation key and colour.
Final Paid/Rejected evidence cannot be contradicted by later final evidence;
weaker Pending/NotFound evidence cannot erase it. Unresolved evidence becomes
Unknown. Wrong-identity receipts are rejected.

The provider model records a keyed request digest and state. Repeated attempts
retain the original operation; conflicting contents under one key are rejected.
This simulates a provider contract and does not establish a real provider's
retention or authentication behaviour.

Cancellation advances worker generation and transfers the live protocol state.
A stale generation loses authority to advance the job. Late evidence may still
resolve the operation ledger; it does not restore a stale worker's authority.

Crash acceptance cases
----------------------------

The reference tests terminate subprocesses using ``os._exit(91)`` after:

#. Admission commit, before source acknowledgement.
#. Result/completion/credit commit, before worker acknowledgement.
#. Provider success commit, before recording its response.
#. Payment-evidence commit, before cancellation completes the sale.
#. Cancellation and Unknown completion, before late evidence.
#. Inconclusive evidence, before retry/escalation.

Each scenario reopens databases, checks persisted state, and preserves another
unresolved order's registration. Additional regressions cover rollback,
dequeue/send gaps, lost replies, duplicate results, wrong-order receipts,
generation fencing, immutable final evidence, and late manual resolution.

The model fires adapter_dequeue and finishes without leftover request tokens
in its acceptance scenarios. This is distinct from the legacy synchronous
simulator's queue behaviour. No universal ordering requirement between provider
outcomes and dequeue is imposed by the source net alone.

Limits
------------

The recovery policy uses a concrete two-attempt budget. The analyser does not
prove a general retry-count or elapsed-time policy. Source changes against a
persisted database are rejected pending migration; automatic upgrades are absent.

These tests exercise process death on one machine. They do not prove behaviour
under physical power loss, storage corruption, all crash schedules, distributed
consensus failures, real networks, hostile webhooks, or every possible Weave flow.
Liveness and general durable scheduling remain unestablished.


.. figure:: ../_static/diagrams/r0-unknown.*
   :name: fig-r0-unknown
   :alt: R0 cancellation produces Unknown; late Paid evidence updates the same result without another credit.
   :width: 100%

   One R0 late-receipt path. The provider is scripted; real authentication is
   outside the reference model.

Acceptance obligations by crash point
-------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 50 25

   * - Injection point / case
     - Persisted state asserted after reopen and recovery
     - Other order throughout
   * - after_admission_commit / admission_before_ack
     - Job exists; source_ack is 0; duplicate admission does not add a job;
       eventual sold=1, registration=0, exactly one provider charge
     - recovery_queue=1; registrations=1
   * - after_result_commit / result_before_ack
     - completed=1; worker_ack=0; pool_free=2; two result rows; replay does not
       duplicate completion or credit
     - recovery_queue=1; registrations=1
   * - after_provider_commit / lost_success_reply
     - inflight=1 and registrations=1 on reopen; keyed reconciliation resolves
       sold=1 without another charge
     - recovery_queue=1; registrations=1
   * - after_receipt_commit / cancel_after_paid
     - paid=1 on reopen; cancellation commits sale, consumes registration, and
       preserves the single paid charge
     - recovery_queue=1; registrations=1
   * - after_cancel_finish / late_receipt_after_cancel
     - Old generation rejected; Unknown completion already recorded; duplicate
       late Paid receipts resolve sold without duplicate results/credits
     - recovery_queue=1; registrations=1
   * - after_receipt_commit / inconclusive_status
     - Two reconciliation attempts lead to manual=1 and registrations=1;
       released=0; result remains unresolved
     - recovery_queue=1; registrations=1

Every case also asserts both request queues empty, pool_free=2, and two result
rows at completion of the scenario. These are explicit source assertions in
``run_crash_cases``. The common end conditions do not imply every crash boundary
had already reached that final marking. All subprocess crashes exit with 91.
