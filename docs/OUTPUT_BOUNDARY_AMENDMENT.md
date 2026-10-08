# Output Boundary Amendment

## Canceled development attempt

Pilot attempt 289565 is preserved as:

> INVALID_FOR_SIGNAL_ESTIMATION — submission/output collection ambiguity

Its existing trajectories and partial canonical evaluation are retained under
`results/development/oracle-signal-qwen3-coder-30b-289565/`. Four No-Memory
runs ended without a submitted patch, including one after 78 API responses.
The old runner did not canonically grade empty predictions, and its collected
patch was not authoritative for worker runs that stopped without a submission
marker. These runs are not memory failures, memory nulls, or an estimate of
memory signal. The partial Django Oracle patch and its grade remain raw
development artifacts only. The machine-readable arm inventory is in
`artifacts/development/qwen3_coder_30b_oracle_signal_289565_status.json`.

## Frozen collection rule for the rerun

Each worker starts from a clean target repository. Before the worker runs, the
collector records the initial Git commit and tree hash. At every catchable
termination, it independently records the worker-declared Finish submission,
Git status porcelain, tracked source changes, relevant untracked source files,
the authoritative binary diff against the initial commit, and the termination
reason.

The repository diff, rather than worker prose or a Finish marker, supplies the
prediction. A recovered nonempty diff is sent unchanged to the canonical
evaluator. A recovered empty tree is sent through the existing semantic no-op
prediction so the unchanged target receives an ordinary canonical grade. A
worker that makes no edit is a valid no-op outcome. Infrastructure-invalid is
reserved for cases where the repository state cannot be recovered or the
canonical evaluator fails.

The run record keeps `worker_declared_submission` distinct from
`authoritative_prediction_valid`. Signal-pair completeness requires recovered
repository state and a canonical grade; it does not require a Finish call.
Target histories, target selection, source cards, prompts, model configuration,
memory payload rules, and evaluator remain frozen.

## Required model-free validation

Before another model call, run:

```bash
python scripts/validate_output_boundary.py \
  --contextbench-root /home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench \
  --targets-parquet /home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet \
  --sif-dir artifacts/burned-pilot/images \
  --job-tmp /path/to/local/job-scratch \
  --output artifacts/development/output-boundary-validation-<run-id>
```

The known-edit fixture omits a worker submission marker and checks the exact
captured patch hash at the evaluator boundary. The empty-tree fixture checks
that the same target receives a canonical no-op grade. Both passed on
2026-10-07 against `sympy__sympy-19235`:

| Fixture | Authoritative diff | Evaluator patch applied | F2P | P2P | Resolved |
|---|---:|---|---:|---:|---|
| Known source edit, no marker | 414 bytes; SHA-256 `8c07e9e510e35dcf30d0e3cf4ac53bf9a8e3e8f5eab657e693d56de17d9f38f4` | Yes; exact SHA-256 match | 0/1 | 144/144 | No |
| Empty tree, no marker | 0 bytes | Yes; frozen semantic no-op SHA-256 `58f4b22d9ebefb6e3db2fc6ff094b647765941576e382fd37133acd074aad06b` | 0/1 | 144/144 | No |

The final collector revision was rerun after covering staged untracked files.
Full fixture records and evaluator logs are under
`artifacts/development/output-boundary-validation-20261007-final2/`. The
collector and pair-completeness tests pass. The signal gate remains at least
two executable discordances among the ten frozen pairs; worker-only patch
differences do not pass it. Freeze the repaired collector before restarting
the full paired signal run.
