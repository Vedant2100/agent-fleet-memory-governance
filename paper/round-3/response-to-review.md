# Final writer response to Round 2 independent scientific review

**Status:** Final author-side manuscript pass, not a scientific acceptance or submission authorization. The independent review verdict remains **Major Revision** for any claim that memory governance improves coding-agent outcomes. The user requested an end to repeated writer–critic loops, so this revision addresses the actionable issues and stops; it does not initiate another critic round.

## Main issues addressed in the manuscript

1. **Outcome-changing baseline regrade — addressed in prose.** The worker/grading section now identifies the original No-Memory `sympy-21203` patch as failing to apply, and the test-path-filtered sanitized regrade as resolving it (3/3 F2P, 124/124 P2P). The abstract now explicitly identifies the regrade dependence. This does not make grading comparable across arms; that remains an experimental limitation.
2. **Memory actually exposed — addressed in results.** A new ten-target B/C/D/E exposure table makes unequal memory budgets visible. The paper explicitly says E's only resolved target (`sympy-19235`) received **no memory**, while E's only exposed record was on unresolved `django-35356`.
3. **Repeated PR dependence — addressed in methods.** A new target-to-PR table shows ten target IDs correspond to eight resolving PRs, including two repeated SymPy PRs.
4. **Missing factorial condition — addressed in design.** A 2×2 admission/exposure table explicitly marks Share-All+Read as **Not run**. The manuscript does not estimate a separate read-filter effect.
5. **Actual card content and selection flow — addressed in figure.** Django and SymPy cases now show verified excerpts of the stored, truncated source records, their reference paths, and source → top-three retrieval → admission → exposure → target stages. The paper does not invent decision rationales.
6. **Contribution, novelty and language — narrowed.** The introduction and related work foreground the reuse of source-only admission decisions across later tasks. The manuscript distinguishes custom Jev System-One API prompts from Jev-Mem, avoids fleet/organizational-learning effectiveness claims, and states that observed exclusions concern annotated related records rather than proven useful lessons.

## Main scientific issues that cannot be fixed by writing

- **Positive transfer:** no validated source-agent lesson or repeated evidence that a stored card helps the later worker.
- **Causal identification:** independent worker runs differ even with identical prompts, and the A/F regrading path differs from B–E.
- **Fair comparison:** unequal exposure budgets and no per-target exposure-matched random/relevance baseline.
- **Factorial completeness:** Share-All+Read was never run.
- **Generalization:** ten target IDs span only eight resolving PRs and three repositories; source patch paths may be retrospective.

These limitations are retained as limitations, not described as solved. No new evaluations, submissions, or acceptance claims were made.
