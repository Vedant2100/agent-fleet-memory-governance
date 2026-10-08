# Development Amendment 05: Worker Mechanics and Memory Signal

**Frozen before any GLM-4.7-Flash task outcome.** The model pull and generic tool-call preflight had started, but no target task had run. No memory treatment has run, and there is no confirmatory treatment result.

## Historical qualification result

**Original 2/3 worker qualification gate: FAILED.** Preserve this result unchanged. It remains a standalone-resolution result for the original Luna qualification. It does not establish whether memory can change later executable behavior.

The former full-resolution gate tested a different prerequisite from this paper's question. Full-resolution requirements can create a ceiling for a very strong worker and reject a mechanically sound worker that makes useful partial fixes. A three-task binary resolution rate is also noisy. This amendment does not call the original gate mistaken; it changes the development question to worker mechanics, then tests memory signal directly.

## Replacement development mechanics gate

Use the same three frozen qualification targets, worker configuration, scaffold, budgets, repository states, and canonical evaluator. A candidate passes mechanics if at least **2 of 3** runs each have:

- a nonempty patch submitted through the upstream finish contract;
- an applicable patch on the frozen target state; and
- an available canonical grade.

There is no minimum full-resolution count for this development gate. Report the former full-resolution decision and all per-task F2P/P2P outcomes beside the amended decision. The target set, histories, source cards, evaluator, and leakage rules remain frozen.

## Memory-signal gate

Only a mechanically viable candidate proceeds to the ten-target development-only No-Memory versus Oracle Known-Related Memory pilot. Preserve the existing go/no-go rule: all pairs must have valid worker submissions and canonical grades, and Oracle must produce executable discordance on at least **2 of 10** targets. Count a resolution rescue/harm or a meaningful canonical F2P/P2P change. A changed patch or LLM preference alone does not pass. Oracle success is evidence of available memory signal, not evidence that a governor works.

The pilot is development-only. Its targets and outcomes do not enter confirmatory effect estimates.

## What counts as evidence in the experiment

The experiment is successful as a measurement if the frozen treatments produce complete paired executable outcomes and the write/read contrasts are actually distinct. A positive treatment effect is not required for the study to be informative; a well-measured null or harmful effect is reportable evidence.

Report paired target-level changes in:

- canonical resolution (rescue, harm, or unchanged);
- FAIL_TO_PASS tests passed and PASS_TO_PASS tests preserved or regressed;
- positive transfer, negative transfer, preserved success, and persistent failure;
- memory exposure, context tokens, worker tokens, steps/tool calls, latency, and governor cost.

Keep write and read effects separable. For the write contrast, compare Share-All and Governed-Write under the same deterministic reader and exposure budget. For the read contrast, hold the shared pool fixed and compare deterministic and governed reading. Do not define governance correctness from relationship labels alone. Treat the ten-target pilot as a small paired estimate with uncertainty, not as a broad population claim. Report Oracle only as a ceiling/reference condition.
