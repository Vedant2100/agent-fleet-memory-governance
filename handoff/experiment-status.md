# Fleet-Mem AAMAS 2027 evidence status

**PROVISIONAL snapshot: 2026-10-08 20:54 UTC.** No paper-writing READY signal has been issued.

## Scope and provenance

- Repository: `Vedant2100/agent-fleet-memory-governance`; handoff branch: `handoff/aamas-2027-evidence`.
- Experiment code commit: `1cedbc0035cb867cfebde398019e313c2a5b02cb`.
- The amended core comparison is arms A–F on the ten frozen primary targets. The earlier seven-arm protocol also listed `G_LLM_WRITE`; G has not run and is excluded from this handoff by the user's explicit scope decision. Do not describe the seven-arm protocol as complete.
- These are development pilot outcomes. `docs/PILOT_DEVELOPMENT_AMENDMENT_05.md` says the signal pilot does not enter a confirmatory effect estimate; the frozen plan has `main_study_authorized=false`.

## Experiment matrix at this snapshot

| Arm | Canonical grades / 10 | Applicable patches | Resolved | Status |
| --- | ---: | ---: | ---: | --- |
| A_NO_MEMORY | 10 | 10 | 2 | Frozen baseline |
| B_SHARE_ALL | 6 | 6 | 1 | Running under job 289898 |
| C_RANDOM_MATCHED | 6 | 6 | 1 | Running under job 289898 |
| D_JEV_WRITE | 6 | 6 | 1 | Running under job 289898 |
| E_JEV_WRITE_READ | 5 | 5 | 1 | Running under job 289898 |
| F_ORACLE_RELATED_CEILING | 10 | 10 | 1 | Frozen diagnostic ceiling |
| G_LLM_WRITE | 0 | 0 | 0 | Unrun; disclosed, outside amended A–F core |

The A/F signal gate has 10 complete paired canonical grades and 3/10 executable discordances (`ORACLE_SIGNAL_PRESENT`). The original job `289648` summary recorded an incomplete signal test because model-created test-file hunks conflicted with the evaluator's test patch. Supplemental canonical regrade job `289879` removed those test hunks from already-generated patches without new worker inference and produced the frozen 20-grade A/F table. The original failures and regrade evidence are both retained.

Jev source admission is frozen at 211 decisions: 123 `SHARE`, 88 `DO_NOT_SHARE`. Size-matched random admission has 211 decisions. The write exposure gate passed with distinct Share-All/Jev exposures on 9/10 targets and Jev read eligibility on 9/10 targets. Fifteen Jev target-read decisions are frozen.

Treatment attempt `289894` failed on the first Jev API call after a DNS resolution error; no worker ran. Attempt `289897` completed governor decisions and the write gate, then failed evaluator preflight because the ContextBench checkout was dirty; no treatment worker ran. Job `289898` uses a verified clean checkout and is running. Its per-arm canonical outcomes are appended to `results/development/paper-treatments-luna/attempt-0003/treatment_results.jsonl`; do not infer completion from process exit alone.

## Frozen execution details

- Worker: Microsoft SWE-Edit `SwebenchAgent`, scaffold commit `60ca6730714670a91bd6a48a53356be85e145248`; OpenAI Responses API requested model `gpt-6-luna`, `xhigh` reasoning, provider-default temperature. The provider response logs expose the alias `gpt-6-luna`; an underlying checkpoint version is not supplied.
- Worker budget: up to 100 upstream agent iterations and 1,800 seconds per task. Each arm gets a fresh worker process and target worktree.
- Jev write/read governor: TypeSafe System One model `jev-1.13.0`; each frozen source decision is made once without retry. Random admission uses seed 42 and matches Jev's admitted count. The treatment arm order is a deterministic SHA-256 ordering keyed by target and the string `fleet-mem-contextbench-luna-paper:20261006`.
- Primary target set: `sympy__sympy-19235`, `sympy__sympy-21203`, `django__django-35356`, `sympy__sympy-16342`, `sympy__sympy-16946`, `sympy__sympy-21309`, `django__django-34176`, `sympy__sympy-16953`, `scikit-learn__scikit-learn-13771`, `sympy__sympy-9384`.
- Canonical evaluator: pinned SWE-ContextBench commit `12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b`, Apptainer SIF per target, frozen benchmark revision `12c65bd15e2559bc808065565e941ee7bbbd008f`. Model-created test-file edits are excluded from submitted implementation patches before the evaluator applies its own gold test patch. Report canonical resolution plus FAIL_TO_PASS and PASS_TO_PASS counts, not model self-assessment.

The final status file will be regenerated from the saved grades after job `289898` finishes. READY requires 40/40 treatment grades, a complete six-arm table, a verified archive, and exact Drive links. Failed or incomplete grades remain visible in the evidence and keep the handoff PARTIAL.
