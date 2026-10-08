# Experimental design

## Question

When should one coding worker's experience be promoted from local to shared memory, and when should a later worker rely on it? The endpoint is executable target-task performance, including regressions, rather than a governor preference score.

## Data flow

```text
source task + source-only trajectory
              |
       memory extractor
              |
       REJECT / LOCAL / SHARED
              |
   repository's shared pool at cutoff
              |
 target task + visible candidate pool
              |
      IGNORE / ADVISORY / RELY
              |
 canonical SWE-ContextBench test evaluation
```

The published relationship table is read only by selection/audit code and the oracle ceiling. It never decides which memories enter an ordinary candidate pool or which candidates Share-All receives.

## Source and target construction

- The source universe is the 300 SWE-ContextBench Lite experience tasks.
- The target universe is the 99 SWE-ContextBench Lite related tasks.
- For each target, candidates are all experience tasks from the same repository with `source.created_at < target.created_at`. Equality and missing timestamps fail the strict chronology check.
- Candidate pools include distractors by construction. Each candidate records `same_repository_history` and any additional source/target issue-text similarity or recency reason. Similarity uses only the target's public issue text and source-side task/patch metadata; it never uses target gold patches, test patches, later commits, or relationship labels.
- The structural screen does not call every historical candidate “plausible.” It separately counts non-linked candidates with shared issue terms, symbols, or paths; chronology alone is not a hard-negative signal. This is a reproducible lexical plausibility proxy, not a human semantic judgment.
- Pool construction deduplicates source IDs and sorts by source timestamp then ID. Duplicate IDs with conflicting content are fatal.
- The hidden relation file annotates known links for evaluation and the oracle arm. Ordinary write and read governor payloads have no relationship field.

The timestamp is the released task `created_at` field. It supports a reproducible historical cutoff, but it does not prove the source agent's actual trajectory was completed at that wall-clock time. The release lacks an official source completion timestamp. The experiment must describe this as a simulated historical ordering and keep the uncertainty visible.

## Memory sources

Two explicitly distinct modes are supported:

1. **Provided experience smoke mode:** a deterministic card from the source task statement, reference-change paths, and source metadata. It has no claimed source-agent success and is useful for pool/interface checks only.
2. **Fresh worker trajectory mode:** a candidate proposed from an actual worker trajectory. The builder accepts a separate JSONL file with exactly one record per experience task; missing, duplicate, or unknown IDs fail closed. The adapter requires a source ID, repository, source-only trajectory text, claim, scope, preconditions, and exact evidence excerpts. Candidate creation and write governance receive no target object. Source outcome is `unknown` unless an unchanged canonical source evaluation is attached.

The smoke release uses mode 1. It is not reported as equivalent to fresh worker experience. Exposed-memory token counts are marked as a character-based estimate unless the paired runner receives a solver-specific token-count callback.

## Tracks

- **NATURAL_TRANSFER:** naturally released tasks and histories only. No generated hard negatives or invented lessons.
- **GOVERNANCE_STRESS:** natural redundancy, overly broad scope, stale/superseded guidance, conflicts, verified failed-source lessons, or adjacent-but-wrong guidance. A case enters only with evidence and an audit reason. The smoke release does not fabricate cases to fill this track; it reports when source outcomes or version evidence are insufficient.

## Factorial arms

Each target is run from the same clean base and with the same frozen solver, harness, and evaluator configuration:

| Arm | Write policy | Read policy |
| --- | --- | --- |
| A | no shared writes | no memory |
| B | Share-All | fixed deterministic read |
| C | governed write | same fixed deterministic read |
| D | Share-All | governed read |
| E | governed write | governed read |
| F | oracle concise known-related memory | known-related memory ceiling |

A–E use the same source candidates and source outcomes. F is an upper-bound diagnostic, never an ordinary governor input. The run manifest records both decisions and the memory actually exposed to the target.

## Governors

A small JSON interface supports deterministic baselines, a Jev/System-One adapter, a deliberative LLM adapter, and an oracle adapter. The benchmark owns no model stack. Governor outputs include action, optional confidence/probabilities, rationale, and latency/cost fields where available.

## Paired execution

For each selected target, each arm starts from the same SWE-ContextBench target base commit and canonical test setup. Source candidates are generated once, then frozen. The official evaluator is called unchanged. One source or target agent configuration is frozen before the pair; no tuning is allowed between arms.

If Share-All and Governed produce the same admitted pool and target exposure on nearly every pilot case, the experiment stops before scaling. If exposures differ, compare paired target outcomes and costs.

## Outcomes

At minimum, record task resolved/Pass@1, FAIL_TO_PASS, PASS_TO_PASS, positive transfer, negative transfer, preserved success, persistent failure, patch application, tokens, steps/tool calls, agent latency, memory tokens exposed, write admission rate, read abstention rate, governor latency/cost, pool size, and environment/control status.

Positive/negative transfer is defined by paired target outcomes relative to A: a new resolution or improved FAIL_TO_PASS without new PASS_TO_PASS regression is positive; loss of a baseline resolution or added regression is negative. Both can be reported for one condition across different targets. The relationship mapping is descriptive metadata, not the transfer outcome label.
