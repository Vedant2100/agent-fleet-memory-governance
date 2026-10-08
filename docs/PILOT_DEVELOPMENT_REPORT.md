# Worker and memory-signal development report

**Status:** Phases 1–2 complete; the Sol diagnostic and Oracle signal pilot have
not started. This is a development report, not a confirmatory result.

## 1. Original Luna gate remains failed

**Original 2/3 worker qualification gate: FAILED.** GPT-6 Luna at `xhigh`
received two canonical grades and resolved 0/2. The third output was not
graded. No memory treatments were run, and no memory-effect conclusion can be
drawn from that failed gate. The prior qualification record and raw files are
preserved in
[`PILOT_WORKER_QUALIFICATION_REPORT.md`](PILOT_WORKER_QUALIFICATION_REPORT.md)
and [`worker_qualification_289222`](../artifacts/burned-pilot/worker_qualification_289222/).

The work described here is a transparent pre-treatment development amendment.
No clean confirmatory treatment outcome exists yet.

## 2. SymPy patch timing diagnosis

The canonical evaluator controls already contain the relevant measurements, so
no expensive evaluator was rerun.

| Variant | Canonical grade runtime | Base `test_wester.py` | Patched `test_wester.py` | Patched result |
| --- | ---: | ---: | ---: | --- |
| No-op/base | 399.45 s | 181.57 s | 178.47 s | completed |
| ContextBench reference/gold patch | 541.31 s | 179.88 s | 323.17 s | completed |
| Luna patch | 2,083.85 s | 208.20 s | >1,800 s | timed out at about 46% |

**Classification: A, likely Luna-patch regression.** Neither base run nor the
gold-patched run reproduced Luna's timeout. The gold-patched run was slower
than its baseline but completed in 323.17 seconds. The Luna patch broadly
wraps operands in `AssumptionsWrapper`, a plausible source of the slowdown, but
there was no profiler run; this does not establish a proven mechanism. Full
control paths, container event indices, commands, outputs, and hashes are in
[`sympy_timing_diagnosis.json`](../artifacts/development/sympy_timing_diagnosis.json).

## 3. Frozen Sol comparison setup

The development amendment and timing evidence were committed before any Sol
run (`cd16b80`). The diagnostic route was committed separately
(`d1d9e8f`). It pins `gpt-5.6-sol` at `xhigh`, runs exactly
`sympy__sympy-21309` followed by `django__django-34176`, and writes to a new
development run root and summary. The Sol config differs from the Luna config
only by `model.requested_model`; effort, tool budget, SWE-Edit commit, prompts,
runner, SIFs, submission path, and evaluator remain fixed. OpenAI Docs confirm
that GPT-5.6 Sol supports `xhigh` reasoning effort ([official model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)).

The route passed the 40-test repository suite, plus Python compilation, shell
syntax, and JSON validation. **No Sol task has run.** The launch environment has
neither `FMC_OPENAI_ENV_FILE` nor `OPENAI_API_KEY`, and no protected mode-600
OpenAI environment-file path was found in the current development environment.
The unrelated `.env` in the older ChainSWE repository was left untouched and
was not read or used. The two-task comparison therefore awaits the existing
protected OpenAI environment-file path; the API key itself is not needed in
the repository or in chat.

Until both canonical Sol grades exist, there is no Sol-versus-Luna table,
worker selection, or Oracle run. The prespecified comparison rule is in
[`PILOT_DEVELOPMENT_AMENDMENT_02.md`](PILOT_DEVELOPMENT_AMENDMENT_02.md).

## 4. Frozen development gate and Oracle rule

The original binary gate remains historically failed and unchanged. Mechanical
viability is established by repository interaction, valid applicable patches,
canonical grading, and nontrivial behavior rather than systematic empty/no-op
failure. Memory-experiment suitability is decided by the burned No-Memory vs
Oracle Known-Related Memory test, not by reinterpreting the original gate.

After the two-run comparison, select one worker under the frozen rule: prefer
Luna if its canonical behavior is reasonably close to Sol; select Sol only if
the two-task comparison shows a material capability advantage likely to
improve interpretability. Then run only No Memory and Oracle on the ten frozen
primary targets. The Oracle pilot is development-only; its outcomes cannot
enter confirmatory effect estimates.

Proceed to governance development only if at least 2/10 complete pairs have
executable discordance in resolution or canonical FAIL_TO_PASS/PASS_TO_PASS,
without credible evaluator, truncation, budget, repository-state, or plumbing
confounds. If fewer than two differ, stop before governor treatments. This
threshold is frozen in the amendment before either diagnostic or treatment
outcomes.

## 5. What has not been shown

- GPT-5.6 Sol is materially better than GPT-6 Luna on these tasks.
- The selected worker/benchmark pair produces Oracle memory signal on at least
  two of ten targets.
- Any write or read governor improves downstream executable outcomes.
- Any confirmatory memory-transfer effect.

No memory-governance arm has run. The 11 histories, 211 source cards, frozen
target set, relation labels, evaluator, leakage rules, and frozen plan were not
changed.
