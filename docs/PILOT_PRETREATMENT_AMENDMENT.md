# Pre-treatment amendment: Matplotlib target validity

**Recorded before any source-governor calls, worker qualification, or treatment runs.**

## Observed control result

The corrected canonical evaluator run completed both controls for
`matplotlib__matplotlib-22482`. The semantic no-op resolved the task: its
designated FAIL_TO_PASS test passed, as did all 194 PASS_TO_PASS tests. The
reference patch also resolved. This means the target does not satisfy the
predeclared no-op failure control and cannot support interpretable treatment
comparisons. The canonical evaluator and target are left unchanged.

## Frozen data and primary analysis

The original 11 target IDs, their candidate histories, the hidden relation
annotations, and the 211-memory source candidate union remain frozen exactly as
recorded in `plan.json`. Matplotlib remains in those artifacts for audit and
sensitivity reporting. It is excluded from the primary target analysis solely
because its canonical no-op control resolved. No target or source history is
added, replaced, or rebuilt.

The primary analysis contains these ten already-frozen targets:

1. `sympy__sympy-19235`
2. `sympy__sympy-21203`
3. `django__django-35356`
4. `sympy__sympy-16342`
5. `sympy__sympy-16946`
6. `sympy__sympy-21309`
7. `django__django-34176`
8. `sympy__sympy-16953`
9. `scikit-learn__scikit-learn-13771`
10. `sympy__sympy-9384`

Source-time write decisions still cover each of the 211 frozen memory cards
once, without target input, and remain frozen across targets. The matched random
admission baseline uses the same frozen candidate universe and exactly matches
the governed admission count. Target exposures and executable treatments use
only the ten primary targets.

## Remaining gates

Run the two canonical controls on each of the five remaining primary targets.
All ten primary targets must have a canonical non-resolving no-op and resolving
reference patch. Any further failure stops the pilot; this amendment does not
authorize another exclusion or target replacement.

If those controls pass, qualify the already-frozen worker with No Memory on
`sympy__sympy-21309`, `django__django-34176`, and
`sympy__sympy-16953`. The qualification rule remains three nonempty patches and
at least two canonical resolutions. Exposure-difference and Jev-read
eligibility gates remain six of the ten primary targets. Passing these gates
would permit only the 70-run, ten-target burned pilot; it does not authorize a
main study.

This amendment is based only on a model-free pre-treatment control. It does not
change the candidate-pool construction, memory extraction, source decisions,
governor prompts, worker, evaluator, treatment definitions, or outcome-based
selection rules.
