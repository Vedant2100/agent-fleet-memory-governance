# Dataset card

## Source

- Dataset: [jiayuanz3/SWEContextBench](https://huggingface.co/datasets/jiayuanz3/SWEContextBench), immutable revision `12c65bd15e2559bc808065565e941ee7bbbd008f`.
- Evaluator and source-task repository: [jiayuanz3/SWEContextBench](https://github.com/jiayuanz3/SWEContextBench), commit `12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b`.
- Subset: SWE-ContextBench Lite only. The release has 300 experience tasks, 99 related target tasks, and 362 total published relationship rows; 104 raw rows point to Lite targets.
- License reported by the dataset repository: MIT.

SWE-ContextBench describes its related tasks as real issue/PR dependency and reference relationships; the paper describes the Lite split as 300 experience tasks and 99 targets. This project changes how prior experience is presented: it uses every earlier same-repository task as a candidate pool, not the relation table as retrieval.

## Included task fields

The parquet inputs provide task ID, repository, task creation time, base commit, environment setup commit, issue text, reference patch, test patch, FAIL_TO_PASS, and PASS_TO_PASS. Gold patches and tests are evaluator-side data. They are never included in a governor-facing target record.

The relationship parquet provides related/experience task IDs and issue/PR URLs. A task pair can have multiple published PR mappings; the audit preserves each raw mapping row and aggregates the pair conservatively (same PR if any mapping is same PR). It does not provide a normalized relationship subtype, resolved commit timestamp, or source-agent evaluation result. Those facts remain unknown unless another released field supports them.

## Known limits

- A task creation timestamp is a historical ordering proxy, not an observed source-worker completion timestamp.
- Source outcomes in the released trajectories are not canonical SWE-ContextBench grades.
- The smoke build checks executable metadata completeness. It does not run gold/no-patch controls or certify environment availability.
- Published relation labels are not governance labels and do not define positive transfer.
- Natural same-repository history varies substantially by target; zero-history targets remain in the full audit and are excluded from the nontrivial-pool pilot sample.

## Intended use

A controlled, paired experiment of write admission and read reliance across coding workers. The data supports a construction smoke test and a small controlled pilot. It does not justify a general memory-system claim or a broad performance claim without complete paired executable outcomes.
