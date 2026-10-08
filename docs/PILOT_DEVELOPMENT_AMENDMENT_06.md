# Development Amendment 06: Qwen3-Coder-Next memory-capacity retry

**Recorded after inspecting job 289376 and before this retry.** No memory
treatment has run. The frozen task order, target states, data, prompts, worker
configuration, SWE-Edit revision, evaluator, reasoning setting, step budget,
submission interface, and PDA-05 mechanics gate remain unchanged.

## Reason for retry

The prior `qwen3-coder-next:q4_K_M` attempt used a 96 GB host-memory allocation.
Its model digest was
`ca06e9e4087c714d44355bf954099187890e63084b4a632b8e9956c4b9492074` and its
reported model size was 51,741,611,823 bytes. The three task workers ended after
1,845 seconds with 12, 2, and 3 API responses, respectively; none produced a
patch or canonical grade. The enclosing Slurm job ended `OUT_OF_MEMORY`.
Those records stay in the evidence ledger as infrastructure-limited; they are
not erased or counted as canonical coding outcomes.

The GPU nodes advertise 749,000 MB of host memory. This amendment repeats the
same three frozen tasks with a 192 GB host-memory allocation. The only planned
change is the Slurm host-memory request, from 96 GB to 192 GB. One GPU, eight
CPUs, Ollama 0.34.4, cloud-disabled local inference, xhigh reasoning, upstream
100-iteration worker budget, prompts, code, and evaluator stay fixed.

## Decision rule

Apply the already frozen PDA-05 rule without modification: at least two of the
three runs must each produce a nonempty upstream `finish` submission, an
applicable patch, and an available canonical grade. The original Luna 2/3
resolution gate and all previous candidate records stay historically
unchanged.

If Qwen3-Coder-Next meets PDA-05, the existing runner may start only the
development-only ten-target No-Memory versus Oracle Known-Related Memory signal
test, with the previously frozen 2/10 executable-discordance threshold. No
governor or confirmatory treatment will run as part of this amendment. If the
memory retry still fails, retain the new task-level results and continue
candidate selection using the complete evidence ledger.

The launch script is
[`qwen3_coder_next_memory_retry.sbatch`](../artifacts/development/qwen3_coder_next_memory_retry.sbatch).

## Execution record

Job `289555` ran for 20 seconds and exited before model inference. Although the
script requested `--mem=192G`, Slurm recorded `TRES mem=96000M` and
`MinMemoryNode=96000M`; the larger request was not reflected in the allocation.
The pinned Ollama service started, but `ollama pull qwen3-coder-next:q4_K_M`
failed because DNS could not resolve `registry.ollama.ai`. No model responses,
worker trajectories, patches, or task grades were produced. This is an
infrastructure-incomplete retry and does not change any prior model result or
the PDA-05 decision. The exact job stdout/stderr and model-service log are
retained as `artifacts/development/qwen3_coder_next_retry_289555.{log,err}`
and `artifacts/development/model_service_qcn_retry_289555.log`.
