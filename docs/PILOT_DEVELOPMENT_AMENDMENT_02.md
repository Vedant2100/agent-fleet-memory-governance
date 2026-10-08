# Pre-treatment worker and memory-signal development amendment

**Status:** frozen before the two-run Sol diagnostic and before any Oracle
signal treatment. This amendment does not change the burned benchmark or its
evaluator.

## Historical record remains fixed

**Original 2/3 worker qualification gate: FAILED.** GPT-6 Luna at `xhigh`
received two canonical grades, resolved 0/2, and the third attempt was canceled
before grading when the original threshold became unreachable. No memory
treatments were run, so no memory-effect conclusion can be drawn from that
gate. This amendment is a transparent pre-treatment development amendment;
there is not yet a clean confirmatory treatment outcome. The original result
and its raw artifacts remain unchanged.

## Why worker selection gets a second, distinct test

The original gate tested whether a worker resolved at least two of three
standalone coding tasks. It remains a valid historical result for that
question; it is not the sole test of suitability for the memory-signal
question. A worker that solves every task can create a ceiling, while a worker
that makes valid, plausible partial fixes can leave room for prior experience
to alter what it does. Three binary task grades also have high sampling
variance. The paper's immediate prerequisite is a mechanically valid worker
whose behavior can be changed by transferable prior experience, not a
particular high standalone solve rate.

This distinction does not turn Luna's failed gate into a pass. Luna's submitted
patches and canonical grades show repository interaction and nontrivial
partial task behavior. The separate No-Memory versus Oracle test will decide
whether this worker/benchmark pair exposes useful memory signal.

## Existing SymPy control timing diagnosis

The existing controls were inspected before authorizing any new model run. The
source records and timing details are in
[`sympy_timing_diagnosis.json`](../artifacts/development/sympy_timing_diagnosis.json).

| Variant | Whole canonical grade | `test_wester.py` before patch | `test_wester.py` after patch | Outcome |
| --- | ---: | ---: | ---: | --- |
| Semantic no-op/base | 399.45 s | 181.57 s | 178.47 s | both completed |
| ContextBench reference/gold patch | 541.31 s | 179.88 s | 323.17 s | both completed |
| GPT-6 Luna patch | 2,083.85 s | 208.20 s | >1,800 s | patched run timed out at about 46% |

The gold patch has a slower second `test_wester.py` run than its first, but it
completed in 323.17 seconds. The no-op runs were about 178–182 seconds. Neither
control exhibits Luna's greater-than-1,800-second timeout. The timing pattern
is therefore classified **A. likely Luna-patch regression**. It is not
profiler-confirmed, and the moderate gold-patch slowdown shows that some
runtime variation exists. This is not classified as a general evaluator
pathology.

## Frozen two-run Sol diagnostic

Run GPT-5.6 Sol on exactly `sympy__sympy-21309` and
`django__django-34176`, once each, through the same SWE-Edit Baseline commit,
adapter, bootstrap, task prompts, clean target SIFs, submission path, canonical
grader, and 1,800-second task timeout used for Luna. The only worker setting
changed is the requested model. Set `requested_model` to `gpt-5.6-sol` and
`reasoning.effort` to `xhigh`, matching Luna's effort exactly; OpenAI Docs list
`none`, `low`, `medium`, `high`, `xhigh`, and `max` for GPT-5.6 Sol, so `xhigh`
is available while preserving the controlled effort comparison ([official
GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)).
The config is `configs/sweedit_worker_sol.json`; it differs from the Luna worker
config only in `model.requested_model`. Do not run a third Sol task. Store the
two diagnostic grades outside the frozen benchmark artifacts and do not
overwrite the Luna qualification record.

Prespecified interpretation of Sol versus Luna on these same two tasks:

- Sol resolves 2/2: strong evidence Luna is the limiting worker; recommend Sol
  for the Oracle signal pilot.
- Sol resolves 1/2: the original three-task binary gate appears high-variance
  for worker selection; Luna remains a viable candidate.
- Sol resolves 0/2: these tasks and the binary criterion do not justify
  rejecting Luna.
- If Sol does not resolve a task but has clearly stronger canonical partial
  outcomes, report task difficulty and prefer the memory-signal criterion over
  binary qualification.

Do not choose from prose quality. Compare resolution, FAIL_TO_PASS,
PASS_TO_PASS, patch applicability and size, runtime, worker tokens/context,
and qualitative failure mode. Prefer Luna if its canonical behavior is
reasonably close to Sol; select Sol only for a material capability advantage
likely to improve interpretability enough to justify its cost.

## Replacement development gate, frozen before Oracle

The original 2/3 gate remains historically failed and unchanged. A worker is
**mechanically viable** when it reliably interacts with the repository,
produces an applicable patch, reaches canonical evaluation, and shows
nontrivial task behavior rather than systematic empty/no-op failure. The
existing Luna records satisfy the mechanics evidence; the original resolution
gate does not.

Worker suitability for the memory experiment is determined only by the
development-only No-Memory versus Oracle Known-Related Memory signal test on
the ten already frozen primary targets. It uses one selected model and the
existing frozen source cards and known-relation metadata. Every A/B pair keeps
the repository state, worker, effort, scaffold, prompt except for memory
insertion, tool/step/time budget, and canonical evaluator identical. Log
per-target resolution, FAIL_TO_PASS, PASS_TO_PASS, patch applicability and
size, worker token/context use, latency, and exposed memory/context size.

This Oracle pilot is development-only. None of its target outcomes enter
confirmatory effect estimates. Do not regenerate cards or alter histories,
relations, target selection, evaluator, leakage rules, or any worker setting
after looking at treatment outcomes.

### Frozen Oracle go/no-go rule

Proceed to governance development only if at least **2 of 10** complete target
pairs show executable discordance: resolution changes, or canonical
FAIL_TO_PASS/PASS_TO_PASS changes meaningfully. At least one resolution
rescue/harm is preferable but not required. The difference must not be
credibly attributable to evaluator failure, truncation, unequal budget,
repository state, or treatment plumbing. If fewer than two targets differ,
stop before every governor treatment and diagnose the lack of signal. Do not
weaken this threshold after seeing results. Oracle success alone does not
establish that any governor works.
