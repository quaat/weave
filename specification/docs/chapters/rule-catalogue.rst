Normative rule catalogue
==========================

Rule IDs are explicit source labels and do not depend on chapter numbering.
The grammar's production names identify syntax rules; this catalogue indexes
prose and inference-rule obligations. Explanatory text does not add hidden
conformance requirements. Editorial portability restrictions are identified
separately from implementation-enforced rules.

The machine-readable index is ``rules.json``. To regenerate this appendix and
the conformance table, run ``python scripts/refresh_reference_pages.py``.
``--check`` fails if generated pages or rule links drift.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Rule
     - Chapter
   * - :ref:`CONF-CASE-1 <CONF-CASE-1>`
     - :doc:`conformance`
   * - :ref:`CONF-REQ-1 <CONF-REQ-1>`
     - :doc:`status`
   * - :ref:`CONF-REQ-2 <CONF-REQ-2>`
     - :doc:`status`
   * - :ref:`CONF-REQ-3 <CONF-REQ-3>`
     - :doc:`status`
   * - :ref:`D0-ADMIT-1 <D0-ADMIT-1>`
     - :doc:`execution-contract`
   * - :ref:`D0-AWAIT-1 <D0-AWAIT-1>`
     - :doc:`execution-contract`
   * - :ref:`D0-AWAIT-2 <D0-AWAIT-2>`
     - :doc:`execution-contract`
   * - :ref:`D0-CANCEL-1 <D0-CANCEL-1>`
     - :doc:`execution-contract`
   * - :ref:`D0-COLOR-1 <D0-COLOR-1>`
     - :doc:`execution-contract`
   * - :ref:`D0-COLOR-2 <D0-COLOR-2>`
     - :doc:`execution-contract`
   * - :ref:`D0-DEADLOCK-1 <D0-DEADLOCK-1>`
     - :doc:`execution-contract`
   * - :ref:`D0-SCHEDULE-1 <D0-SCHEDULE-1>`
     - :doc:`execution-contract`
   * - :ref:`F0-BIND-1 <F0-BIND-1>`
     - :doc:`static-semantics`
   * - :ref:`F0-CALL-1 <F0-CALL-1>`
     - :doc:`static-semantics`
   * - :ref:`F0-CALL-2 <F0-CALL-2>`
     - :doc:`static-semantics`
   * - :ref:`F0-CALL-3 <F0-CALL-3>`
     - :doc:`static-semantics`
   * - :ref:`F0-MATCH-1 <F0-MATCH-1>`
     - :doc:`static-semantics`
   * - :ref:`F0-RETURN-1 <F0-RETURN-1>`
     - :doc:`static-semantics`
   * - :ref:`F0-SIGNATURE-1 <F0-SIGNATURE-1>`
     - :doc:`static-semantics`
   * - :ref:`F0-TAGRETURN-1 <F0-TAGRETURN-1>`
     - :doc:`static-semantics`
   * - :ref:`F0-TRY-1 <F0-TRY-1>`
     - :doc:`static-semantics`
   * - :ref:`F0-TRY-2 <F0-TRY-2>`
     - :doc:`static-semantics`
   * - :ref:`F0-TRY-3 <F0-TRY-3>`
     - :doc:`static-semantics`
   * - :ref:`F0-UNITCALL-1 <F0-UNITCALL-1>`
     - :doc:`static-semantics`
   * - :ref:`LEX-REQ-1 <LEX-REQ-1>`
     - :doc:`lexical`
   * - :ref:`LEX-REQ-2 <LEX-REQ-2>`
     - :doc:`lexical`
   * - :ref:`N0-DECL-1 <N0-DECL-1>`
     - :doc:`declarations`
   * - :ref:`N0-DECL-2 <N0-DECL-2>`
     - :doc:`declarations`
   * - :ref:`N0-DECL-3 <N0-DECL-3>`
     - :doc:`declarations`
   * - :ref:`N0-DECL-4 <N0-DECL-4>`
     - :doc:`declarations`
   * - :ref:`N0-DECL-5 <N0-DECL-5>`
     - :doc:`declarations`
   * - :ref:`N0-ORDER-1 <N0-ORDER-1>`
     - :doc:`verification`
   * - :ref:`N0-SEAL-1 <N0-SEAL-1>`
     - :doc:`declarations`
   * - :ref:`N1-COLOUR-1 <N1-COLOUR-1>`
     - :doc:`net-semantics`
   * - :ref:`N1-FAMILY-1 <N1-FAMILY-1>`
     - :doc:`verification`
   * - :ref:`N1-FAMILY-2 <N1-FAMILY-2>`
     - :doc:`verification`
   * - :ref:`N1-FIRE-1 <N1-FIRE-1>`
     - :doc:`net-semantics`
   * - :ref:`N1-ORDER-1 <N1-ORDER-1>`
     - :doc:`verification`
   * - :ref:`N2-CORRELATION-1 <N2-CORRELATION-1>`
     - :doc:`evidence-design`
   * - :ref:`N2-EVIDENCE-1 <N2-EVIDENCE-1>`
     - :doc:`evidence-design`
   * - :ref:`N2-EVIDENCE-2 <N2-EVIDENCE-2>`
     - :doc:`evidence-design`
   * - :ref:`N2-MIGRATE-1 <N2-MIGRATE-1>`
     - :doc:`evidence-design`
   * - :ref:`NET-FIRE-1 <NET-FIRE-1>`
     - :doc:`net-semantics`
   * - :ref:`NET-REQ-1 <NET-REQ-1>`
     - :doc:`net-semantics`
   * - :ref:`P0-ARITH-1 <P0-ARITH-1>`
     - :doc:`pure`
   * - :ref:`P0-ARITH-2 <P0-ARITH-2>`
     - :doc:`pure`
   * - :ref:`P0-BUDGET-1 <P0-BUDGET-1>`
     - :doc:`pure`
   * - :ref:`P0-BUDGET-2 <P0-BUDGET-2>`
     - :doc:`pure`
   * - :ref:`P0-BUDGET-3 <P0-BUDGET-3>`
     - :doc:`pure`
   * - :ref:`P0-BUDGET-4 <P0-BUDGET-4>`
     - :doc:`pure`
   * - :ref:`P0-CALL-1 <P0-CALL-1>`
     - :doc:`pure`
   * - :ref:`P0-DECL-1 <P0-DECL-1>`
     - :doc:`pure`
   * - :ref:`P0-DECL-2 <P0-DECL-2>`
     - :doc:`pure`
   * - :ref:`P0-DECL-3 <P0-DECL-3>`
     - :doc:`pure`
   * - :ref:`P0-DECL-4 <P0-DECL-4>`
     - :doc:`pure`
   * - :ref:`P0-EFFECT-1 <P0-EFFECT-1>`
     - :doc:`pure`
   * - :ref:`P0-EFFECT-2 <P0-EFFECT-2>`
     - :doc:`pure`
   * - :ref:`P0-EVAL-1 <P0-EVAL-1>`
     - :doc:`pure`
   * - :ref:`P0-EVAL-2 <P0-EVAL-2>`
     - :doc:`pure`
   * - :ref:`P0-EVAL-3 <P0-EVAL-3>`
     - :doc:`pure`
   * - :ref:`P0-FAULT-1 <P0-FAULT-1>`
     - :doc:`pure`
   * - :ref:`P0-FILE-1 <P0-FILE-1>`
     - :doc:`pure`
   * - :ref:`P0-FORK-1 <P0-FORK-1>`
     - :doc:`pure`
   * - :ref:`P0-LIST-1 <P0-LIST-1>`
     - :doc:`pure`
   * - :ref:`P0-NAME-1 <P0-NAME-1>`
     - :doc:`pure`
   * - :ref:`P0-NAME-2 <P0-NAME-2>`
     - :doc:`pure`
   * - :ref:`P0-PATH-1 <P0-PATH-1>`
     - :doc:`pure`
   * - :ref:`P0-REC-1 <P0-REC-1>`
     - :doc:`pure`
   * - :ref:`P0-RECORD-1 <P0-RECORD-1>`
     - :doc:`pure`
   * - :ref:`P0-RECORD-2 <P0-RECORD-2>`
     - :doc:`pure`
   * - :ref:`P0-RUN-1 <P0-RUN-1>`
     - :doc:`pure`
   * - :ref:`P0-RUN-2 <P0-RUN-2>`
     - :doc:`pure`
   * - :ref:`P0-TYPE-1 <P0-TYPE-1>`
     - :doc:`pure`
   * - :ref:`P0-TYPE-2 <P0-TYPE-2>`
     - :doc:`pure`
   * - :ref:`P0-TYPE-3 <P0-TYPE-3>`
     - :doc:`pure`
   * - :ref:`P0-VALUE-1 <P0-VALUE-1>`
     - :doc:`pure`
   * - :ref:`PROTO-IDENTITY-1 <PROTO-IDENTITY-1>`
     - :doc:`protocol-diff`
   * - :ref:`SEC-CAP-1 <SEC-CAP-1>`
     - :doc:`security`
   * - :ref:`SEC-EVIDENCE-1 <SEC-EVIDENCE-1>`
     - :doc:`security`
   * - :ref:`SEC-FENCE-1 <SEC-FENCE-1>`
     - :doc:`security`
   * - :ref:`SEC-MODEL-1 <SEC-MODEL-1>`
     - :doc:`security`
   * - :ref:`SEC-REPLAY-1 <SEC-REPLAY-1>`
     - :doc:`security`
   * - :ref:`SYN-01 <SYN-01>`
     - :doc:`grammar`
   * - :ref:`SYN-02 <SYN-02>`
     - :doc:`grammar`
   * - :ref:`SYN-03 <SYN-03>`
     - :doc:`grammar`
   * - :ref:`SYN-04 <SYN-04>`
     - :doc:`grammar`
   * - :ref:`SYN-05 <SYN-05>`
     - :doc:`grammar`
   * - :ref:`SYN-06 <SYN-06>`
     - :doc:`grammar`
   * - :ref:`SYN-07 <SYN-07>`
     - :doc:`grammar`
   * - :ref:`SYN-08 <SYN-08>`
     - :doc:`grammar`
   * - :ref:`SYN-09 <SYN-09>`
     - :doc:`grammar`
   * - :ref:`SYN-10 <SYN-10>`
     - :doc:`grammar`
   * - :ref:`SYN-11 <SYN-11>`
     - :doc:`grammar`
   * - :ref:`SYN-12 <SYN-12>`
     - :doc:`grammar`
   * - :ref:`SYN-13 <SYN-13>`
     - :doc:`grammar`
   * - :ref:`SYN-14 <SYN-14>`
     - :doc:`grammar`
   * - :ref:`TYPE-REQ-1 <TYPE-REQ-1>`
     - :doc:`types`
