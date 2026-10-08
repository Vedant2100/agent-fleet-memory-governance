# Development Amendment 07: run the frozen Oracle signal test now

**Recorded before the signal outcomes.** The original GPT-6 Luna qualification
result remains exactly **FAILED** at its original 2/3 resolution gate. No
qualification history is deleted or relabeled. The frozen 11 histories, 211
source cards, ten primary targets, task states, evaluator, leakage rules, and
treatment payloads remain unchanged.

## Reason for proceeding

The purpose of the next run is to test whether known relevant prior experience
changes executable task behavior. Existing Luna and Qwen3.6 trajectories produced
real, applicable patches that received canonical grades and partially changed
FAIL_TO_PASS behavior. This is enough evidence that the worker interface and
evaluator are mechanically viable for a signal test; another full-resolution
qualification screen would answer a different question. No memory treatment has
run yet.

The protected OpenAI credential is absent from the current environment and the
known mode-600 credential paths, so Luna is not immediately runnable here. The
existing store at `/home/csgrad/vbork001/shared-mem-gov-pilot/models` contains a
manifest for `qwen3-coder:30b`; its model layer digest is
`sha256:1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a`
(18,556,688,736 bytes). Pinned Ollama 0.34.4 lists it locally without a pull.
This is the strongest coding-specific model in that store. The run uses this
existing model only; no model search, download, or qualification loop is
authorized by this amendment.

## Frozen worker and execution

- Model: `qwen3-coder:30b`, from the existing shared model store.
- Reasoning: `xhigh`.
- Worker: SWE-Edit `baseline` / `SwebenchAgent`, commit
  `60ca6730714670a91bd6a48a53356be85e145248`.
- Budget: upstream 100 iterations; 1,800 seconds per worker trajectory.
- Context: Ollama 0.34.4 Responses-compatible endpoint, cloud disabled, 16,384
  context tokens; no registry pull.
- Evaluator, SIF states, task prompt, pair order seed, memory cards, and Oracle
  selection: frozen inputs used by `run_sweedit_burned.py`.
- Arms: No Memory and Known Relevant Memory only, for the ten frozen primary
  targets. This user-authorized development run bypasses the earlier
  full-resolution qualification stop only; it does not alter the worker or
  evaluator.

The worker configuration is
[`sweedit_worker_qwen3_coder_30b.json`](../configs/sweedit_worker_qwen3_coder_30b.json).
The local endpoint adapter and Slurm launcher are
[`run_existing_local_oracle_signal.py`](../artifacts/development/run_existing_local_oracle_signal.py)
and
[`qwen3_coder_30b_oracle_signal.sbatch`](../artifacts/development/qwen3_coder_30b_oracle_signal.sbatch).

## Frozen decision

PASS requires at least two of ten targets with a meaningful executable
difference between complete, canonically graded No-Memory and Known-Relevant
Memory arms. A patch-only difference does not count. Any pair with an
infrastructure failure, unapplied patch, or unavailable canonical grade is
incomplete and is not counted as agreement. Fewer than two executable
discordances across complete pairs is FAIL; incomplete runs are reported as
incomplete and are not used to claim a pass or a null effect. No governor run is
authorized by a failed signal test.

## Reproduction

```sh
sbatch artifacts/development/qwen3_coder_30b_oracle_signal.sbatch
```

## Pre-treatment launch correction

Launch attempt `289563` exited before model inference because the wrapper
queried `ollama list` before starting the Ollama server. No task worker,
memory exposure, or evaluator ran. The wrapper order was corrected to start and
verify the local service before listing the installed model; the frozen worker
configuration and all benchmark inputs are unchanged. This attempt is retained
as an infrastructure startup failure, not a treatment result.
