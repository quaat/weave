Static semantics: inference rules
=======================================

This chapter is normative for F0 static checking. Rule IDs are stable across
chapter renumbering. The judgments describe the existing fragment; they do not
claim a mechanized soundness proof.

Notation and auxiliary judgments
--------------------------------------

:math:`\Sigma` maps operation names to parameter/result signatures and declared
enum cases. :math:`\Gamma` maps reusable bindings to types and symbolic identities.
:math:`\Delta` maps live linear bindings to types. :math:`K` contains **all**
names introduced in the current scope, including moved names. Therefore removing
a binding from :math:`\Delta` does not allow shadowing it.

:math:`\Sigma;\Gamma;\Delta;K\vdash B\Downarrow R` means that block B has a
valid explicit terminal path returning R on every branch.
:math:`\Sigma;\Gamma;\Delta\vdash f(\bar a):T\triangleright\Delta'` is the
call judgment; it consumes arguments without yet binding the result.

Let :math:`\operatorname{lin}(T)` hold exactly for declared resources and enums.
The value-use judgment :math:`\Gamma;\Delta\vdash v:T\triangleright\Delta'`
has these cases: a live linear variable is removed from Delta; a variable in
Gamma leaves Delta unchanged; the empty payload, written :math:`\epsilon` in
the metalanguage, has Unit and leaves Delta unchanged. It is not a source literal.

.. _F0-SIGNATURE-1:

F0-SIGNATURE-1 — Formation and complete checking
------------------------------------------------------

Every resource/enum occurrence MUST have its declared arity. Result indices
MUST be bound by scalar parameter names or linear-parameter indices. A linear
parameter name cannot itself stand for an index. Scalar parameters are unindexed
and non-Unit. Results are Unit, a resource, or an enum. All helper signatures are
registered before bodies; all bodies are checked, including unused bodies.
The helper call graph MUST be acyclic.

.. _F0-CALL-1:

F0-CALL-1 — Resolution
----------------------------

A call MUST resolve to exactly one declared API or same-file helper. Sealed
resource constructors are forbidden. Every argument is an existing binding,
and its number and nominal type name match the corresponding parameter.
No implicit conversion, widening, overload, or private-transition call exists.

.. _F0-CALL-2:

F0-CALL-2 — Identity substitution and moves
-------------------------------------------------

Let :math:`\Sigma(f)=(p_i:T_i)_{i=1}^n\to R` and actual argument types be U_i.
First bind each scalar formal name to its actual symbolic identity, then unify
formal identity indices with actual indices. The resulting substitution
:math:`\theta` MUST be consistent at every occurrence and resolve all result
indices. Every linear actual MUST be live and appear only once in the argument
list. Nominal names and ordered index arities must match exactly.

.. _F0-CALL-3:

F0-CALL-3 — Call judgment
-------------------------------

With the premises of F0-CALL-1/2, and L the set of linear argument bindings:

.. math::

   \frac{\Sigma(f)=(p_i:T_i)_{i=1}^{n}\to R
         \quad \theta(T_i)=U_i\;(\forall i)
         \quad L\subseteq\operatorname{dom}\Delta
         \quad \operatorname{distinct}(L\text{ occurrences})}
        {\Sigma;\Gamma;\Delta\vdash f(\bar a):
         \theta(R)\triangleright(\Delta\setminus L)}
   \;\text{F0-CALL-3}

The equality for scalar types compares their nominal type; scalar formal names,
rather than scalar type names, seed theta. The judgment is static ownership
transfer, not a claim that the requested net transition can fire.

.. _F0-BIND-1:

F0-BIND-1 — Bound call and sequencing
-------------------------------------------

Define extend(x,T) to add x to Delta when T is linear, or to Gamma when T is
Unit. The new name MUST be absent from K.

.. math::

   \frac{\Sigma;\Gamma;\Delta\vdash f(\bar a):T\triangleright\Delta_1
         \quad x\notin K
         \quad(\Gamma_2,\Delta_2)=\operatorname{extend}(\Gamma,\Delta_1,x,T)
         \quad\Sigma;\Gamma_2;\Delta_2;K\cup\{x\}\vdash B\Downarrow R}
        {\Sigma;\Gamma;\Delta;K\vdash
         \texttt{let }x\texttt{ = await }f(\bar a);B\Downarrow R}

Source calls require await. Parsing an unawaited call for a useful E212/E205
diagnostic does not make that call a valid F0 statement.

.. _F0-UNITCALL-1:

F0-UNITCALL-1 — Unbound call
----------------------------------

.. math::

   \frac{\Sigma;\Gamma;\Delta\vdash f(\bar a):\mathrm{Unit}\triangleright\Delta_1
         \quad\Sigma;\Gamma;\Delta_1;K\vdash B\Downarrow R}
        {\Sigma;\Gamma;\Delta;K\vdash
         \texttt{await }f(\bar a);B\Downarrow R}

A resource or enum result MUST NOT be discarded, including an enum whose actual
payload happens to be Unit.

.. _F0-RETURN-1:

F0-RETURN-1 — Ordinary return
-----------------------------------

.. math::

   \frac{\Gamma;\Delta\vdash v:R\triangleright\varnothing}
        {\Sigma;\Gamma;\Delta;K\vdash\texttt{return }v\Downarrow R}

For a bare return, use :math:`v=\epsilon`, so R is Unit.
The returned binding MUST have exactly R and there MUST be no other live linear
obligation. Return ends the block; following statements are invalid.

.. _F0-TAGRETURN-1:

F0-TAGRETURN-1 — Tagged return
------------------------------------

Let :math:`R=E[\bar k]`, case payload :math:`E[\bar\alpha].c=P`,
and :math:`\eta=[\bar\alpha\mapsto\bar k]`.

.. math::

   \frac{c\in\operatorname{cases}(E)
         \quad\Gamma;\Delta\vdash v:\eta(P)\triangleright\varnothing}
        {\Sigma;\Gamma;\Delta;K\vdash
         \texttt{return }c(v)\Downarrow E[\bar k]}

The constructor is selected from the declared return enum, not inferred as an
open union. Empty parentheses use epsilon and require a Unit payload.
Wrapping a payload moves it; it does not mint another resource.

.. _F0-MATCH-1:

F0-MATCH-1 — Exhaustive terminal match
--------------------------------------------

For a live scrutinee :math:`x:E[\bar k]\in\Delta`, remove x. For each declared
case c, instantiate its payload with eta. Extend that branch with its payload
binding if one is supplied; omission is allowed only for Unit. A supplied binding
MUST be fresh in K. Let these environments be :math:`\Gamma_c,\Delta_c,K_c`.

.. math::

   \frac{x:E[\bar k]\in\Delta
         \quad\operatorname{tags}(B_c)=\operatorname{cases}(E)
         \quad\operatorname{unique}(\operatorname{tags}(B_c))
         \quad\forall c,\ \Sigma;\Gamma_c;\Delta_c;K_c\vdash B_c\Downarrow R}
        {\Sigma;\Gamma;\Delta;K\vdash
         \texttt{match }x\texttt{: }\{c(v_c):B_c\}_c\Downarrow R}

Each branch begins with the same residual Delta, never a union of branch-owned
values. There is no post-match continuation and no branch environment join.

.. _F0-TRY-1:

F0-TRY-1 — Bound propagation rewrite
------------------------------------------

Write :math:`\mathcal L` for lowering, B for the entire remaining continuation,
and Names for all source identifiers. With e and u distinct and fresh outside
Names(source):

.. math::

   \mathcal L(\texttt{let }x\texttt{ = }r\texttt{?};B)
   =
   \texttt{match }r\texttt{: }
   \begin{cases}
   \texttt{Ok}(x):\mathcal L(B)\\
   \texttt{Err}(e):\texttt{return Err}(e)\\
   \texttt{Unknown}(u):\texttt{return Unknown}(u)
   \end{cases}

Fresh names MUST also avoid names allocated by earlier lowering steps.
The source line of the propagation is attached to generated nodes.

.. _F0-TRY-2:

F0-TRY-2 — Awaited propagation rewrite
--------------------------------------------

With z fresh under the same condition:

.. math::

   \mathcal L(\texttt{let }x\texttt{ = (await }f(\bar a)\texttt{)?};B)
   =
   \texttt{let }z\texttt{ = await }f(\bar a);
   \mathcal L(\texttt{let }x\texttt{ = }z\texttt{?};B)

These rewrites are syntax transformations. The entire result is checked by the
ordinary rules, not by a separate weakened propagation checker.

.. _F0-TRY-3:

F0-TRY-3 — Propagation obligations
----------------------------------------

The operand enum MUST have exactly Ok, Err, Unknown. The enclosing result enum
MUST accept the same Err and Unknown payload types and indices; its Ok payload
may differ. F0-TAGRETURN-1 requires every other obligation to be discharged on
both early-return paths. No cleanup, cancellation, conversion, or extra firing
is inserted.

Guarantee and implementation boundary
-------------------------------------------

The rules establish symbolic transfer discipline for the fragment. They do not
prove enabledness, identity freshness, deadlock freedom, fairness, provider truth,
or general runtime refinement. :doc:`execution-contract` specifies the new
normative dynamic target, whose scheduler is not implemented by the simulator.

