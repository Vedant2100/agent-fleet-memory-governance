# Independent AAMAS scientific critique — Round 2

**Verdict: MAJOR REVISION — not submission-ready.** This is an internal scientific review of the committed `paper/round-2/main.tex`, not a conference decision.

## Demonstrated contribution

The manuscript distinguishes an earlier source-only decision to retain a historical issue record from a later task-aware decision to expose that record to a coding agent. It traces where benchmark-annotated related records are excluded under fixed top-three retrieval, but does not establish that those records were useful or that the selection policy improves repair success. The study is a narrow, potentially informative negative pilot rather than a validated memory-management method.

## Independent evidence check

I examined Round 0's review and scientific addendum, the available Round 1 critique, the Round 2 manuscript and supporting files, and the frozen v15 archive. The archive SHA-256 matches the handoff; all **40/40** B–E canonical-result hashes match their ledger. Across the same ten target IDs, A No Memory resolves **2/10**, while B Share-All, C Random, D custom Jev admission, E admission plus read, and F known-related diagnostic each resolve **1/10**. F2P passed out of 48: A 9, B 7, C 8, D 13, E 7, F 8. P2P preserved out of 2145: A 2145, all B–F 2025. These target IDs represent only **eight distinct resolving PRs**.

The v15 pools, relationship annotations and decisions independently confirm the related-record trace: **8/10** reach top-three retrieval, **2/8** survive source-only admission, and **1/8** is exposed. The six target-level write exclusions represent only two distinct SymPy source decisions (`sympy-16988` and `sympy-21055`). The controller has 123 SHARE and 88 DO_NOT_SHARE decisions, followed by one EXPOSE and 14 WITHHOLD decisions. Every saved rationale is empty. The cards are issue-derived descriptions and reference-change paths, not agent-learned lessons; **197/211** descriptions contain a truncation marker and all source-agent outcomes are unknown.

## Ranked scientific concerns

**1. The experiment has not shown that its records contain useful transferable information (critical).** The known-related diagnostic resolves 1/10 against No Memory's 2/10. Relatedness annotations identify a historical relationship, not a useful repair lesson. The custom admission criteria explicitly favor well-supported, bounded memories; rejecting an unvalidated related card is not necessarily a policy error. **Fix now:** call the 8→2→1 result a trace of *annotated related-record availability*, and show actual stored card text for the Django and SymPy examples. **New experiment:** establish a positive control with validated source-agent trajectories or lessons that reproducibly improve a later worker.

**2. Memory effects cannot be separated from worker and grading variation (critical).** E exposes no memory on **nine of ten** targets, and its saved task prompts are byte-identical to A on those nine. Yet the A/E workers produce different patches and grades on `sympy-21203` and `sympy-21309`; on the latter, E preserves 200/320 P2P tests versus A's 320/320. There is a further outcome-changing grading detail: the **original A patch on `sympy-21203` failed to apply**, while the separately test-path-filtered sanitized regrade applies and resolves the task (3/3 F2P, 124/124 P2P). Thus one of A's two reported successes depends on this regrade. **Fix now:** state this raw/regrade distinction explicitly and do not present 2/10 versus 1/10 as a causal effect. **New experiment:** repeat matched workers, prioritizing these two SymPy tasks and the one E-exposed Django task, with a single authoritative patch-normalization/evaluator protocol.

**3. The write/read design and context quantities are not controlled (major).** The missing Share-All+Read cell prevents a full 2×2 decomposition of admission and exposure. B, C, D and E deliver respectively 30, 20, 15 and **one** record across targets, with unequal estimated context sizes. Globally matching Random's admission count does not match per-target exposure. Fixed top-three recency excludes the related record for `django-34176` and `sympy-19235` before admission. **Fix now:** show the missing factorial cell and per-target exposure counts; describe policy bundles rather than independent stage effects. **New experiment if stage effects are claimed:** Share-All+Read, exposure-matched random/relevance controls, and a retrieval ablation.

**4. Novelty and AAMAS fit are still limited (major).** The actual implementation uses custom binary Jev System-One API prompts, **not** Jev-Mem's published memory architecture; Round 2 correctly fixes this attribution. SWE-ContextBench studies related coding histories, ReasoningBank agent-derived lessons, MemGuard verifier-backed governance, Jev-Mem organized/adaptive memory, and ChainSWE linked repairs. The plausible new observation is that a source-only decision reused across future tasks may remove related context before later selection. This is not a new validated selector, fleet collaboration, or organizational learning. **Fix now:** foreground this narrow question and compare directly with prior work. A negative result can be informative, but needs either deeper analysis or a reliable positive-control setting to support a strong methodological claim.

**5. Sampling and temporal validity limit generalization (major).** Ten target labels map to eight resolving PRs in three repositories; two SymPy pairs share PRs. The records were assembled retrospectively, and source reference-change paths may not have been available when the source issue was opened. **Fix now:** include target-to-PR mapping and distinguish issue timestamps from actual patch availability. **New experiment for prospective-memory claims:** enforce real source-information availability times and use distinct later repairs.

## Editorial audit

The title, *Selecting Earlier Task Records for Coding Agents: An Exploratory Study*, is restrained and suitable. The introduction's real Django example and the task-level F2P table are improvements. Precise remaining edits:

- **Introduction:** replace “a plausible place for an agent to investigate” with “The stored record names `django/db/models/sql/query.py`, but provides no tested repair procedure.”
- **Introduction:** replace “a decision to retain that issue is made before the later task is known” with “We evaluate a source-only admission decision that is not given the later task”; this avoids implying a prospective deployment.
- **Figure 1:** the two text boxes are useful but should explicitly show *source → top-three retrieval → admission → exposure → worker*, with both rejection branches.
- **Results:** after “The data show where exclusion occurred, not why,” add “The saved decisions contain no rationale.”
- **Conclusion:** replace “The experiment locates information loss in the selection process” with “The experiment traces removal of annotated related records but cannot establish whether their exclusion affects repairs.”

Avoid changing the title merely for style; keep conventional AI and software-engineering terminology. Add per-target memory exposure to the outcome table so readers can see that E's only resolved target received no memory.

## Factual corrections and workflow notes

The earlier Round 1 critic's **198/211** truncated count should be **197/211**. The old claim that the pilot necessarily violated a stopping rule was overstated: the sub-three baseline restriction appears to concern launching a larger study. SWE-ContextBench arXiv v3 lists **Jiayuan Zhu**, not “Jared Zhu.” Round 2 accurately distinguishes the custom Jev API policy from Jev-Mem and accurately reports 40/40 amended-core evaluations; proposed G remains unrun.

Round 2 lacks `paper/round-2/.overleaf-ready`, so the repository's highest-marked-round Overleaf sync may still show Round 1. The writer should mark a coherent next-round snapshot for preview, not as scientific approval. Official AAMAS class compilation, page count, anonymization and disclosures remain to be checked, but are not the primary scientific blockers.

**Priority for Writer Round 3:** (1) disclose the outcome-changing A regrade; (2) clarify that E's only resolution occurred without memory exposure; (3) add per-target selection/exposure and PR grouping; (4) sharpen the source-only decision contribution and natural-language figure; (5) keep positive control, matched repeats and missing factorial cell explicitly listed as needed experiments. No submission or PAPER_READY marker is justified.
