# Burned pilot control and qualification report

> **Superseded before treatments on 2026-10-06.** Per the current worker-route
> amendment, qualification attempts `289199` and `289200` are classified as
> infrastructure-invalid and are not solver outcomes. No treatment has run.
> The current protocol is [PILOT_WORKER_ROUTE_AMENDMENT.md](PILOT_WORKER_ROUTE_AMENDMENT.md);
> this document remains the historical record of those attempts and the model-free
> evaluator controls.

> The initial canonical-control failure, ten-target pre-treatment amendment,
> and worker qualification attempts are all retained below. All eleven target
> histories remain frozen for audit; Matplotlib alone is excluded from primary
> analysis because its semantic no-op resolved. See
> [`PILOT_PRETREATMENT_AMENDMENT.md`](PILOT_PRETREATMENT_AMENDMENT.md) and
> [`PILOT_WORKER_INTERFACE_AMENDMENT.md`](PILOT_WORKER_INTERFACE_AMENDMENT.md).
> The ten-target evaluator controls passed. The one corrected worker
> qualification also failed; no governors or treatments ran.

**Stop before governors and treatments.** The first qualification exposed a
command-format failure. The one documented pre-treatment correction was applied
to the same three tasks; its qualification also failed. No further worker
adjustment or treatment run is allowed under the frozen protocol.

## Frozen pilot and execution

The frozen set is still the same 11 targets and 211 unique source cards. The
benchmark manifest, pools, hidden relationship annotations, ContextBench
checkout, and SIFs were not changed. The worker command interface was corrected
and its prompt/telemetry amendment is frozen in the current plan.
The current plan SHA-256 is recorded in
[`control_gate.json`](../artifacts/burned-pilot/control_gate.json); its manifest
and hidden-annotation hashes are identical to the original freeze. The only
benchmark/runtime changes are the corrected Apptainer adapter parser and the
pre-treatment Matplotlib primary-analysis exclusion documented in the amended
protocol. Neither changed target metadata, histories, evaluator code, or the
hidden relation files.

Control job `289176` completed the first five target pairs successfully, then
could not collect the Matplotlib tests: its post-test-patch package reinstall
was rejected because the adapter skipped a leading `--name` argument. Both
Matplotlib arms collected 0 of 195 requested tests. Those two outputs are
preserved under `results/burned-pilot/controls-first-attempt/`.

Adapter commit `c1cf15b` corrected the Docker argument parser and added a
regression test. All 32 local unit tests passed. The corrected control job
`289186` used the same frozen target order, SIF, test patches, and canonical
ContextBench commit. It completed 12 controls across six targets. The first
five target pairs passed their no-op/reference checks.

## Stop condition

For `matplotlib__matplotlib-22482`, the corrected adapter successfully
reinstalled the package after both patches (return code 0, no adapter errors),
and the canonical evaluator collected all 195 requested test results. The
semantic no-op arm nevertheless resolved:

- FAIL_TO_PASS: 1/1 passed
- PASS_TO_PASS: 194/194 passed
- `lib/matplotlib/tests/test_pickle.py::test_axeswidget_interactive` was
  reported passed in both the before-patch and after-patch outputs.
- The reference-patch arm also returned a valid grade with all 195 tests
  passing.

The frozen protocol requires the semantic no-op to be unresolved. The runner
therefore stopped at this target with
`RuntimeError: semantic no-op control failed for matplotlib__matplotlib-22482`.
The remaining five targets were not run in the corrected control job. The
machine-readable per-target status, result hashes, event-log hashes, and
failure details are in [`control_gate.json`](../artifacts/burned-pilot/control_gate.json).

This fails the original 11-target control gate. The evidence establishes that this
target/test/environment combination does not behave as a valid FAIL_TO_PASS
control under the pinned evaluator; it does not identify whether the underlying
cause is the target metadata, base image, or test behavior. No evaluator source,
target list, test patch, or benchmark item was changed to force a pass.

## Amended primary controls

After recording the failure, the pre-treatment amendment retained the original
11-target universe and candidate pools, marked Matplotlib nonprimary, and froze
the other ten targets as the primary analysis set. Control job `289194` then
completed both canonical controls for the five not covered by job `289186`.
All ten primary targets now have a valid unresolved semantic no-op and a valid
resolving reference patch: 20/20 primary control grades pass. Per-target F2P,
P2P, latency, canonical-result paths, and SHA-256 values are in
[`controls_summary.json`](../artifacts/burned-pilot/controls_summary.json).

An initial subset submission, job `289193`, exposed that Slurm treats commas in
`--export` as variable separators. It was stopped after only the first
no-op-control directory was created; it produced no canonical grade and is not
included in the 20-control table. The runner now parses colon-separated target
IDs, and corrected job `289194` used that syntax. Its output and the cancelled
attempt are retained under `results/burned-pilot/`.

## Worker qualification infrastructure attempt

Qualification job `289197` launched all three frozen No-Memory tasks but is
invalid as worker-capability evidence. Each mini-SWE-agent request returned
HTTP 404 before inference because the adapter passed `/v1` to the `ollama_chat`
provider, which appended `/api/chat`; the local Ollama server expects native
`/api/chat`. The installed `mini` console script also had a stale shebang into
`shared-mem-gov-pilot/.venv`, violating the standalone repository boundary.
The outputs are preserved under
`results/burned-pilot/qualification-failed-289197/` and the Slurm logs at
`results/burned-pilot/qualification-289197.{out,err}`. No model inference or
canonical grade occurred in this attempt.

The adapter now supplies the native Ollama base URL, and the Slurm job creates
a job-local wrapper around the pinned mini-SWE-agent interpreter. A no-network
preflight checks mini-SWE-agent 2.4.6, LiteLLM 1.102.1, its module location,
and its `mini` entry point before the worker runs. Qualification job `289198`
then stopped at that preflight: `realpath` followed the venv's `python` symlink
to base Conda Python, which does not contain mini-SWE-agent. No task ran. The
wrapper now resolves the executable's directory while preserving the venv
entrypoint symlink. Both failed jobs are retained.

## Qualification attempt `289199`: command-interface failure

Job `289199` passed the interpreter, Ollama, evaluator, and frozen-control
preflights, then ran all three preregistered No-Memory qualification tasks.
The pinned worker returned HTTP 200 for each `/api/chat` request, but every
trajectory submitted an empty patch after one assistant action and one tool
call. That action was the configured `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`
completion marker; the worker did not inspect, edit, or test the target
repository. The trajectories establish a command-format/scaffold failure under
this setup, not a coding-capability measurement.

| Qualification target | Patch bytes | Worker steps / tool calls | Wall seconds | Canonical grade |
| --- | ---: | ---: | ---: | --- |
| `sympy__sympy-21309` | 0 | 1 / 1 | 149.9 | Not run; no patch |
| `django__django-34176` | 0 | 1 / 1 | 43.6 | Not run; no patch |
| `sympy__sympy-16953` | 0 | 1 / 1 | 40.5 | Not run; no patch |

Each target made two `/api/chat` calls and one `/api/show` call, all with
HTTP 200. The qualification gate required three nonempty patches and at least
two canonical resolutions; it observed 0/3 nonempty patches and 0 canonical
grades. The recorded `resolved_count: 0` means no target had a grade marked
resolved; it is not evidence that three graded tasks failed. FAIL_TO_PASS,
PASS_TO_PASS, and transfer outcomes are unavailable because no patch was
graded.

Token telemetry is also unavailable. The worker recorder counts
`/chat/completions` responses with an OpenAI `usage` object, while this frozen
provider used native `/api/chat`; its parser therefore recorded zero model
calls and null prompt/completion token counts despite the successful chat
requests. The response bodies were not retained, so exact tokens cannot be
recovered from this run. The fixed context window was 16,384 tokens; actual
context use is unknown. Raw worker outputs and endpoint logs remain under
`results/burned-pilot/qualification/`; the machine-readable result is
[`qualification-attempt-289199.json`](../artifacts/burned-pilot/qualification-attempt-289199.json).

The documented command-interface correction and one same-task pre-treatment
requalification are recorded in
[`PILOT_WORKER_INTERFACE_AMENDMENT.md`](PILOT_WORKER_INTERFACE_AMENDMENT.md).
The corrected attempt failed the original qualification rule, so no treatments
were run.

## Corrected qualification attempt `289200`: final stop

The corrected command interface let the worker inspect repositories and issue
commands. It still produced no submitted patch on any task:

| Qualification target | Exit status | Steps / tool calls | Patch bytes | Prompt / output tokens | Wall seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| `sympy__sympy-21309` | `LimitsExceeded` | 12 / 12 | 0 | 52,896 / 411 | 94.1 |
| `django__django-34176` | `Submitted` | 8 / 8 | 0 | 24,538 / 268 | 27.5 |
| `sympy__sympy-16953` | `LimitsExceeded` | 12 / 12 | 0 | 61,983 / 342 | 36.8 |

All 32 model `/api/chat` requests and the three `/api/show` requests returned
HTTP 200. The two SymPy runs exhausted the 12-step limit. The Django run added
test text but no implementation, then submitted an empty patch. No synthetic
patch was graded: canonical grade count is 0/3, so the `resolved_count: 0`
field is not three observed task failures. FAIL_TO_PASS, PASS_TO_PASS, and
transfer are unavailable.

The trajectory also exposes an output-contract defect: the worker prompt says
to run the completion marker as a standalone command, while mini-SWE-agent's
Apptainer environment takes the submitted patch from stdout lines after that
marker. A standalone marker therefore submits an empty string even if the
working tree contains edits. Fixing that contract would require another worker
change, but the one permitted pre-treatment correction has been used and this
run also failed the task/step gate. The pilot stops; no more worker runs are
made.

The native Ollama token counters are now captured correctly. Across these
qualification-only runs, the worker used 139,417 prompt tokens and 1,021
completion tokens. Per-target context lengths and endpoint records are in
[`qualification.json`](../artifacts/burned-pilot/qualification.json); raw
trajectories and logs remain under
`results/burned-pilot/qualification-attempt-2/`.

No source-governor decisions, memory exposures, target-governor decisions, or
treatment runs occurred. The frozen 11 histories, 211 source cards, ten
primary targets, and all 20 passing evaluator controls remain unchanged. No
treatment result or task-set change motivated the correction. The qualification
gate failed, so this pilot cannot support a memory-governance effect estimate.

## What has not run

No source-time or target-time governor decisions, memory exposures, treatment
outcomes, or treatment-discordant cases exist. These are **not run**, not
zero-valued observations. The model-free gate passed; worker qualification
attempt `289200` failed after the one documented interface correction.

The earlier SIFs are retained. No main study was started, and this frozen pilot
does not support scaling or a causal claim about memory governance.

## Reproduction

Run the local checks from the repository root:

```bash
python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/validate_benchmark.py
bash -n scripts/run_burned_pilot.sbatch
```

The corrected control stage uses the frozen plan and the exact Slurm command
recorded in `docs/EXPERIMENT_PROTOCOL.md`, with `FMC_STAGE=controls` and the
pinned SWE-ContextBench checkout and parquet paths. Job `289186` stopped at the
predeclared no-op check; its stdout/stderr and per-control canonical logs are
preserved under `results/burned-pilot/`.

The exact submission was run from the repository root:

```bash
sbatch --partition=vcggpu --time=48:00:00 \
  --export=FMC_PROJECT_ROOT=/home/csgrad/vbork001/fleet-mem-contextbench,FMC_PYTHON=/home/csgrad/vbork001/miniconda3/bin/python,FMC_CONTEXTBENCH_ROOT=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench,FMC_TARGETS_PARQUET=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet,FMC_STAGE=controls \
  -o /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/controls-%j.out \
  -e /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/controls-%j.err \
  scripts/run_burned_pilot.sbatch
```

That command uses the default corrected-control output directory; resubmitting
it in this checkout would overwrite the corrected-run control files. The
first-attempt logs remain separately preserved.

The corrected five-target batch and summary assembly used:

```bash
sbatch --partition=vcggpu --time=48:00:00 \
  --export=FMC_PROJECT_ROOT=/home/csgrad/vbork001/fleet-mem-contextbench,FMC_PYTHON=/home/csgrad/vbork001/miniconda3/bin/python,FMC_CONTEXTBENCH_ROOT=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench,FMC_TARGETS_PARQUET=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet,FMC_STAGE=controls,FMC_CONTROL_TARGET_IDS=sympy__sympy-21309:django__django-34176:sympy__sympy-16953:scikit-learn__scikit-learn-13771:sympy__sympy-9384,FMC_CONTROL_OUTPUT=results/burned-pilot/controls-remaining-corrected,FMC_CONTROL_SUMMARY=results/burned-pilot/controls-remaining-corrected.json \
  -o /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/controls-remaining-corrected-%j.out \
  -e /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/controls-remaining-corrected-%j.err \
  scripts/run_burned_pilot.sbatch
python scripts/assemble_burned_controls.py \
  --remaining-summary results/burned-pilot/controls-remaining-corrected.json
```

Qualification job `289199` used the same frozen three-task subset and settings:

```bash
sbatch --partition=vcggpu --time=48:00:00 \
  --export=FMC_PROJECT_ROOT=/home/csgrad/vbork001/fleet-mem-contextbench,FMC_PYTHON=/home/csgrad/vbork001/miniconda3/bin/python,FMC_CONTEXTBENCH_ROOT=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench,FMC_TARGETS_PARQUET=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet,FMC_STAGE=qualify,FMC_MINI_PYTHON=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/worker-venv/bin/python,FMC_OLLAMA_BIN=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/ollama/ollama/bin/ollama,FMC_OLLAMA_MODELS=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/ollama/models \
  -o /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/qualification-%j.out \
  -e /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/qualification-%j.err \
  scripts/run_burned_pilot.sbatch
```

This command reproduces the recorded failed qualification; the frozen stop
gate means it should not be resubmitted unchanged.

The single amended qualification job `289200` used the corrected interface and
a separate output directory:

```bash
sbatch --partition=vcggpu --time=48:00:00 \
  --export=FMC_PROJECT_ROOT=/home/csgrad/vbork001/fleet-mem-contextbench,FMC_PYTHON=/home/csgrad/vbork001/miniconda3/bin/python,FMC_CONTEXTBENCH_ROOT=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench,FMC_TARGETS_PARQUET=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet,FMC_STAGE=qualify,FMC_MINI_PYTHON=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/worker-venv/bin/python,FMC_OLLAMA_BIN=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/ollama/ollama/bin/ollama,FMC_OLLAMA_MODELS=/home/csgrad/vbork001/.cache/fleet-mem-contextbench/ollama/models,FMC_QUALIFICATION_RUN_ROOT=results/burned-pilot/qualification-attempt-2 \
  -o /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/qualification-%j.out \
  -e /home/csgrad/vbork001/fleet-mem-contextbench/results/burned-pilot/qualification-%j.err \
  scripts/run_burned_pilot.sbatch
```

It produced the failed result in `artifacts/burned-pilot/qualification.json`;
the frozen protocol does not permit another worker attempt.
