# Burned ContextBench pilot protocol

**Protocol version:** `burned-pilot-v2`
**Status:** amended before governor and worker calls; no treatment runs yet
**Frozen audit universe:** all 11 target IDs and pools in the smoke release
**Primary treatment set:** the ten targets listed in `docs/PILOT_PRETREATMENT_AMENDMENT.md`

This protocol uses the already constructed smoke release as the burned pilot. It does not rebuild, replace, or expand its targets or candidate histories. The frozen plan records each target and pool hash in `artifacts/burned-pilot/plan.json`. Matplotlib remains in the audit universe but is excluded from primary treatment analyses because its corrected semantic no-op control resolved. The full pre-treatment amendment and evidence are recorded in `docs/PILOT_PRETREATMENT_AMENDMENT.md` and `artifacts/burned-pilot/control_gate.json`. No further exclusion or outcome-based replacement is allowed.

## Source-time candidate extraction and write governance

The extraction rule is `provided-experience-metadata-v1`, already applied uniformly to the ContextBench experience tasks. It emits one source-only episodic candidate for each source task, using its issue description and paths touched by its source reference change. It does not inspect any target or relation label, and it does not filter candidates for generality, reusability, similarity, or future usefulness. Candidate quality is left to the write governor. These cards are ContextBench-provided experience records; they are not fresh coding-worker trajectories and do not assert a source-agent outcome.

The candidate unit is the stable `memory_id`. The union of the frozen 11 target pools is deduplicated by that ID and contains 211 source cards. The Jev/System-One write governor receives each unique source card **exactly once**, in stable source-time order, without a target ID, target issue, relation label, target patch, or target outcome. This source-time universe remains fixed even though Matplotlib is not a primary target. Its only permitted write actions are:

- `SHARE`
- `DO_NOT_SHARE`

The complete decision table, input hashes, confidence, rationale, latency, token use, and available cost are written before the first target worker run and then treated as immutable for every target. The deliberative LLM makes a second, independently frozen source-only decision for each of the same 211 cards. Ollama usage reports supply local prompt/completion token counts; local monetary cost is zero. Missing, duplicate, or target-contaminated decisions stop the pilot. Never retry a candidate whose model call may have reached the service.

The size-matched random baseline is drawn once from the same unique source-memory universe. Its admission count is exactly the number of `SHARE` decisions in the frozen Jev table. Admission is without replacement, using ascending `SHA256("fleet-mem-contextbench-burned-v2:random:42:" + memory_id)`; ties use `memory_id`. Its decision table is also frozen before target runs. A share rate of 0% or 100% under Jev is a degeneracy stop and does not authorize substituting another governor.

## Target-time retrieval and read governance

Target-time governance has only two actions: `EXPOSE` and `WITHHOLD`. It receives the target task and the memories permitted by the arm, but never hidden relation labels or target gold patches.

All non-oracle write-policy comparisons use the same fixed target-time retrieval: take the three most recent candidates in the target's frozen history, ordered by source timestamp descending, then `source_task_id` and `memory_id` ascending. Retrieval is independent of target text and governor output. Filter those three slots by the arm's already-frozen shared set. Expose no more than three memories. Thus Share-All, Random, Jev Write, and LLM Write have identical retrieval and exposure rules; only source-time admission can change which retrieved memories survive. The worker context window is fixed at 16,384 tokens. Record actual model-reported context tokens per call and per run, plus each exposed card's serialized bytes and character-based token estimate. There is no separate memory-token truncation cap.

Jev Write+Read applies the same frozen Jev write set and retrieval, then asks the Jev read governor for `EXPOSE`/`WITHHOLD` on each retrieved, admitted memory. The read governor runs at target time and may see the target issue. It cannot add memories outside the deterministic retrieved set or exceed the shared three-memory budget.

The oracle ceiling uses hidden published relationship annotations only inside the oracle adapter. It selects known-related candidates from the full frozen target history, orders them by the same source-time tie-break rule, and exposes up to three memories. Oracle results are diagnostic and excluded from causal governor comparisons.

## Preregistered kill-gate sequence

1. Commit the complete experiment code, protocol, and the pre-treatment amendment, then generate and commit `artifacts/burned-pilot/plan.json`. The plan retains all 11 target pools but separately records the ten primary analysis targets and the Matplotlib exclusion. It binds the protocol, amendment, target/pool/relation hashes, source-memory union, worker settings, random seeds, and experiment-code file hashes.
2. Stage all 11 ContextBench images as SIFs. Run both model-free canonical controls on each of the ten primary targets, for 20 primary control grades. A failed primary control stops the pilot; Matplotlib's completed failing control remains in the audit.
3. Run the three preregistered No-Memory worker qualification tasks. A failed qualification stops the pilot.
4. Run one Jev source-time write decision per unique memory. Before spending calls on the full deliberative LLM arm or Jev reads, run the write-exposure check. Degenerate Jev admission, fewer than six targets with different Share-All/Jev exposures, or fewer than six targets with at least one admitted memory in the fixed three-slot retrieval window stops the pilot.
5. Only after the write-exposure gate passes, run and freeze the 211 source-only deliberative LLM decisions, then make Jev's target-time read decisions and write the complete 70-row exposure manifest.
6. Validate all frozen inputs and run the seven arms once on the ten primary targets. A low No-Memory success count is reported as an interpretability stop; no benchmark changes or main-study runs follow.

Every stage is a Slurm job using `scripts/run_burned_pilot.sbatch`; it uses job-local scratch for Apptainer's writable overlays and the configured local Ollama model store. Stage names and exact commands are below. Create a Python environment with the pinned optional extras, and set these paths before submitting jobs. The Slurm script creates a job-local `mini` wrapper that invokes the pinned interpreter directly, so it does not depend on an installed console-script shebang:

```bash
export FMC_PYTHON=/path/to/python-with-project-extras
export FMC_CONTEXTBENCH_ROOT=/path/to/clean-pinned-SWE-ContextBench
export FMC_TARGETS_PARQUET=/path/to/SWEContextBench_Related_Lite.parquet
export FMC_MINI_PYTHON=/path/to/python-in-the-pinned-mini-swe-agent-2.4.6-environment
export FMC_OLLAMA_BIN=/path/to/ollama-0.34.4
export FMC_OLLAMA_MODELS=/path/to/frozen-ollama-model-store
mkdir -p results/burned-pilot
```

Configure a fresh TypeSafe credential in a private terminal before Jev stages; the script verifies it and stores it outside this repository with mode 600. It never displays or writes the key into project artifacts:

```bash
python scripts/configure_jev_credentials.py
```

The required order is explicit; inspect each completed artifact before submitting the next stage:

```bash
sbatch --export=ALL,FMC_STAGE=stage-images -o results/burned-pilot/stage-images-%j.out -e results/burned-pilot/stage-images-%j.err scripts/run_burned_pilot.sbatch
sbatch --export=ALL,FMC_STAGE=controls -o results/burned-pilot/controls-%j.out -e results/burned-pilot/controls-%j.err scripts/run_burned_pilot.sbatch
sbatch --export=ALL,FMC_STAGE=qualify -o results/burned-pilot/qualification-%j.out -e results/burned-pilot/qualification-%j.err scripts/run_burned_pilot.sbatch
sbatch --export=ALL,FMC_STAGE=source-jev -o results/burned-pilot/jev-write-%j.out -e results/burned-pilot/jev-write-%j.err scripts/run_burned_pilot.sbatch
sbatch --export=ALL,FMC_STAGE=write-gate -o results/burned-pilot/write-gate-%j.out -e results/burned-pilot/write-gate-%j.err scripts/run_burned_pilot.sbatch
sbatch --export=ALL,FMC_STAGE=source-llm -o results/burned-pilot/llm-write-%j.out -e results/burned-pilot/llm-write-%j.err scripts/run_burned_pilot.sbatch
sbatch --export=ALL,FMC_STAGE=exposure-freeze -o results/burned-pilot/exposure-freeze-%j.out -e results/burned-pilot/exposure-freeze-%j.err scripts/run_burned_pilot.sbatch
sbatch --export=ALL,FMC_STAGE=treatments -o results/burned-pilot/treatments-%j.out -e results/burned-pilot/treatments-%j.err scripts/run_burned_pilot.sbatch
```

Do not submit later stages when the prior gate reports `STOP_*` or lacks its required `PASS_*` artifact. Treatment scripts reject missing gates, changed hashes, duplicate assignments, and incomplete runs. A failed or interrupted model call is never silently retried. `results/` and SIF images are runtime artifacts; tracked JSON/JSONL summaries and decision/exposure tables remain in `artifacts/burned-pilot/`.

## Frozen treatment arms

| Arm | Source-time admission | Target-time handling |
| --- | --- | --- |
| `A_NO_MEMORY` | none | expose none |
| `B_SHARE_ALL` | share every unique candidate | fixed deterministic retrieval |
| `C_RANDOM_MATCHED` | seeded random set, exactly Jev's admitted count | same fixed deterministic retrieval |
| `D_JEV_WRITE` | frozen Jev binary decisions | same fixed deterministic retrieval |
| `E_JEV_WRITE_READ` | same frozen Jev binary decisions | Jev `EXPOSE`/`WITHHOLD` on retrieved memories |
| `F_ORACLE_RELATED_CEILING` | hidden relation oracle | expose known-related memories within the common budget |
| `G_LLM_WRITE` | deliberative LLM binary decisions | same fixed deterministic retrieval |

Arm G is run on all ten primary targets. Its source governor sees the unchanged 211-card candidate universe. The cards are short and the local `qwen2.5:32b` Ollama model asset is available before outcomes; that is the preregistered feasibility basis. Its write decision is made once per source card, then frozen. If the fixed runtime cannot complete all 211 decisions, record the failure and stop the LLM arm; do not substitute a subset.

## Coding worker qualification and fixed run settings

The worker is `mini-swe-agent 2.4.6` with local `qwen2.5-coder:32b` (Ollama 0.34.4), temperature 0, seed 42, 16,384-token context, at most 12 agent steps, at most 1,024 generated tokens per model call, and a 900-second worker limit per task. The same committed system prompt, task template, Apptainer tool environment, model, and limits apply to every arm. Memories are inserted only in the reserved memory section. Each run starts from a clean target checkout and an empty worker state. The pilot plan pins the worker config and adapter hashes.

Before treatments, run No Memory on the three frozen qualification targets listed in the plan and require valid no-op/reference controls on all ten primary targets. Qualification passes only if all controls are valid, the worker submits a nonempty patch on all three qualification tasks, and at least two of three are canonically resolved. If a qualification run fails before repository inspection because the command-only interface is malformed or the terminal sentinel is invoked prematurely, preserve it as an interface failure. A documented pre-treatment interface correction may then be tested once on the same three frozen tasks, model, tool environment, and budgets. If that corrected qualification fails, stop the pilot; do not tune again or run treatments. After a passing qualification, freeze worker settings across all arms. For the pilot to be interpretable, at least three of the ten primary No Memory outcomes must resolve. The treatment arms are run once per primary target, with within-target arm order determined by the frozen random seed. Do not adjust the worker or governor after observing treatment results.

## Canonical executable evaluation

Use the pinned SWE-ContextBench `evaluate_instance` and its test selection, patch application, result parser, and score predicate unchanged. Run it through the Apptainer adapter recorded with the pilot artifacts; the adapter replaces Docker image/container lifecycle operations only. Its function returns early for an empty model patch, so the no-patch control uses a fixed marker-file patch that changes no executable source. Record that control patch hash. Record ContextBench commit, image reference and digest, SIF hash, adapter command log, and evaluator report for every target-arm. No hand-written test substitute may be used for a missing canonical result.

### Model-free control execution erratum

Control job `289176` initially failed at `matplotlib__matplotlib-22482`: the canonical evaluator's post-test-patch reinstall uses `docker run --name ...` without a preceding option, while the Apptainer adapter incorrectly skipped the first run argument. The parser was corrected, with regression coverage for named runs both with and without `-i`, and the frozen plan was regenerated without changing targets or pools. Corrected job `289186` then completed both Matplotlib grades; its designated FAIL_TO_PASS test passed under the semantic no-op, invalidating Matplotlib as a primary target. The ten other original targets remain fixed. Preserve both job logs and this case-study record. No governor or worker was called before the amendment.

## Required records and comparisons

For each target and arm, record shared and exposed memory IDs, every source write decision, every read decision, memory count, exposed-card byte sizes and token estimates, exact worker prompt/context tokens per call and run, worker tokens/steps/tool calls/latency, governor calls/cost/latency, evaluator validity, resolved/Pass@1, FAIL_TO_PASS and PASS_TO_PASS totals and passes, and transfer status against that target's No Memory result. One-time source-governor cost is reported globally and as non-additive per-target attribution over that target's candidate history.

Define positive transfer as a resolved improvement or a higher FAIL_TO_PASS count without a PASS_TO_PASS regression. Define negative transfer as loss of resolution or any decrease in FAIL_TO_PASS or PASS_TO_PASS. Also report preserved success and persistent failure. List each target-arm pair whose exposed memory IDs differ; separately list outcome-discordant pairs (resolution, FAIL_TO_PASS, or PASS_TO_PASS differs).

Stop before any larger study if Jev admits none/all of the unique memories, fewer than six primary targets have actual exposure differences between Share-All and Jev Write, the evaluator controls fail on any primary target, or fewer than three primary No Memory targets resolve. Preserve all run logs and report the failed gate and cause. Do not modify or replace the frozen benchmark after seeing outcomes.

## Scope of this run

This is the ten-target primary burned pilot with an 11-target frozen audit universe. Do not launch the main study or expand the task set from this protocol.
