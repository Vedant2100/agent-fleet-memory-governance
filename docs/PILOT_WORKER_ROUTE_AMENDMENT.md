# Pre-treatment worker route amendment

**Recorded before any new worker run or treatment exposure.** The existing
11-target history freeze, 10-target primary set, 211 source cards, leakage
labels, SIFs, ContextBench checkout, canonical evaluator, and control results
remain unchanged.

## Reclassification of the earlier qualification attempts

Qualification attempts 1 and 2 (Slurm jobs `289199` and `289200`) are treated
as infrastructure-invalid and are not solver outcomes. No memory treatment has
run. The earlier local Ollama solver path is closed; its predictions are not
used to estimate worker ability or memory effects.

## Model-free submission-contract audit

`scripts/audit_mini_submission_contract.py` creates a known unified diff in
`patch.txt`, inspects it, and executes exactly:

```sh
echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt
```

It passes that command's captured output through
`minisweagent.environments.singularity.SingularityEnvironment._check_finished`
from mini-SWE-agent 2.4.6 and asserts that the resulting
`Submitted.messages[0].extra.submission` equals the fixture byte-for-byte. The
audit makes no model call. The recorded result is
[`mini_submission_contract.json`](../artifacts/burned-pilot/mini_submission_contract.json).

## Frozen worker for qualification and the signal test

The coding worker uses Microsoft's upstream SWE-Edit `baseline` agent at commit
`60ca6730714670a91bd6a48a53356be85e145248`, with its `SwebenchAgent` tools and
100-iteration default. The worker runs inside the target's existing ContextBench
SIF with a writable temporary overlay; only the resulting git diff is submitted
to the unchanged ContextBench evaluator. Each arm starts from a fresh SIF
process and receives a new trajectory directory.

The requested API model is `gpt-6-luna`, reasoning effort `xhigh`, using the
OpenAI Responses API. `xhigh` is the strongest value documented for current
reasoning models; the API reference does not list `max` as an effort value. The model name is checked against the actual model IDs
returned by the API in every worker record. The worker configuration is pinned
in [`sweedit_worker.json`](../configs/sweedit_worker.json). GPT-6 Luna is listed
as an OpenAI API model in the [official pricing/model list](https://platform.openai.com/pricing).

The established task timeout is 1,800 seconds. The previous mini-SWE-agent
12-step cap is not used. The qualification set remains
`sympy__sympy-21309`, `django__django-34176`, and `sympy__sympy-16953`.
Qualification passes only with three nonempty submissions, three valid SWE-Edit
finish-tool submissions, three canonical grades with applied patches, and at
least two canonical resolutions. Failure stops the study before treatments.
After a pass, the worker config, adapter, and bootstrap hashes are checked
before the signal test and remain fixed.

## First signal gate

After qualification only, run paired No-Memory and Oracle known-related-memory
conditions on the same ten primary targets, with a preregistered per-target
pair order derived from seed `20261006`. The oracle receives up to the existing
three-memory exposure budget, selected only from clean known-related memories.
No other governance arm runs before this comparison.

For each pair record patch hash and validity, model IDs, response token counts,
trajectory token/context statistics, tool calls, elapsed time, exposed memory
IDs and estimated context size, canonical resolution, FAIL_TO_PASS, and
PASS_TO_PASS. Report behavioral discordance when the submitted patch differs;
report executable discordance when any canonical outcome field differs. If
either occurs on at least one complete pair, the oracle signal gate passes. If
all twenty runs are valid but neither kind of discordance occurs, stop before
governor treatments. If any run lacks a valid submitted patch or canonical
grade, stop and report an incomplete signal test rather than treating missing
evidence as agreement.

The signal summary is written to
[`signal_test.json`](../artifacts/burned-pilot/signal_test.json). A passing
signal permits the already-authorized frozen governance factorial using the
same worker. No target, memory history, evaluator, or leakage rule can change
after this amendment.

## Reproduction

First run the model-free audit:

```sh
/home/csgrad/vbork001/.cache/fleet-mem-contextbench/worker-venv/bin/python \
  scripts/audit_mini_submission_contract.py
```

Then submit the qualification stage, setting the protected API environment-file
path and the pinned ContextBench paths:

```sh
sbatch --export=ALL,FMC_PROJECT_ROOT="$PWD",FMC_SWEEDIT_STAGE=qualify,\
FMC_OPENAI_ENV_FILE=/path/to/mode-600/openai.env,\
FMC_CONTEXTBENCH_ROOT=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench,\
FMC_TARGETS_PARQUET=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet \
  scripts/run_sweedit_pilot.sbatch
```

Only if `sweedit_qualification.json` reports `PASS`, submit the same command
with `FMC_SWEEDIT_STAGE=signal`. The Slurm wrapper uses the site Apptainer
runtime and node-local scratch; it does not start Ollama or use Docker.
