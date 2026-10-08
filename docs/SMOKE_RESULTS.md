# ContextBench Lite construction smoke results

This is the pre-experiment construction report. It contains no target solver outcome and is not evidence for the burned pilot's live governance treatments. The current pilot freezes the same 11 clean targets and the candidate histories in `artifacts/smoke/`; its 603 target-pool entries deduplicate to 211 unique source cards.

## Structural gate: pass, narrow sample

The pinned release has 300 experience tasks, 99 related targets, and 104 relationship rows mapping to 102 unique target/source pairs. Relationship coverage is 99/99 targets. The audit preserves repeated task-pair rows that name distinct PRs.

All 99 targets were screened using strict `created_at` chronology and all earlier same-repository experience tasks. Across the full target population, pool sizes have median 17 and mean 27.646; 16 targets have no history, three have one candidate, 80 have at least two, 71 have at least five, and 60 have at least ten. The maximum pool size is 114.

The frozen clean stratum contains 11 targets. The other target-level strata are 16 `EXPLICIT_PRIOR_REFERENCE`, six `HIGH_HINT_LEAKAGE`, 26 `SAME_PR_OR_CORESOLUTION`, and 40 `AMBIGUOUS_CHRONOLOGY`. Environment metadata is present for these cases, but no canonical runtime control has run; `environment_valid` remains unknown.

All 11 selected targets meet the predeclared rule: a clean strict-prior distinct-PR relationship, at least five same-repository candidates, and at least two non-linked overlap candidates. Their pools range from 13 to 114 (median 50, mean 54.818); every pool has at least ten candidates. The automatic issue/path/symbol overlap proxy counts 3 to 113 non-linked candidates (median 18). These are candidate signals, not human relevance labels. The structural casebook records examples; its clearest adjacent-task pools include:

- `sympy__sympy-19235`: inverse-trigonometric printer experience among other printer memories.
- `matplotlib__matplotlib-22482`: slider/widget and figure-unpickling histories around figure serialization.
- `django__django-35356`: prior `QuerySet.only()` / `select_related()` work alongside a reverse `OneToOneField` target.

This is a narrow 11-target opportunity, not a broad ContextBench sample. There are 33 strict-prior published related pairs in the release; 11 targets have a linked source that passes the frozen clean screen.

## Historical exposure wiring check: pass mechanically

The earlier model-free exposure check compared fixed-read and governed-read pairs under `deterministic_conservative_v1`:

| Comparison | Cases with different shared pools | Cases with different exposed memories |
| --- | ---: | ---: |
| Share-All + fixed read vs Governed write + fixed read | 11/11 | 11/11 |
| Share-All + governed read vs Governed write + governed read | 11/11 | 11/11 |

The means per target were three exposed memories in Share-All/fixed-read, one in Share-All/governed-read, and zero in both governed-write arms. All 603 pool entries are provided-experience episodic cards with unknown source outcomes. The deterministic governor kept every candidate `LOCAL`; this only checked that the earlier treatment wiring could change exposure. It does not predict live Jev or deliberative-LLM decisions. Pilot v2 replaces that read/write interface and runs a new Jev exposure gate before the LLM arm.

No source trajectories were generated for the 300 experience tasks. The smoke cards are explicitly `PROVIDED_EXPERIENCE_SMOKE`, not fresh worker lessons.

## Evaluator status at the construction checkpoint

At this checkpoint the official evaluator checkout was clean at commit `12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b`, and its unchanged `evaluation.sh` required Docker. The initial controls attempt stopped before scoring, so that report had no evaluator-control outcomes. The burned-pilot protocol now uses a project-local Apptainer adapter that maps the evaluator's Docker image/container lifecycle to SIFs and job-local writable overlays while calling upstream `evaluate_instance` unchanged. Current environment validity remains unestablished until all 22 frozen pilot controls pass.

No live Jev, deliberative LLM, or coding-agent run occurred during construction. No burned-pilot outcome is included here.

## Reproducibility check

The smoke release was built twice from the pinned parquet inputs and code commit recorded in `manifests/source_provenance.json`. All 24 builder-owned files were byte-identical across builds, including the JSONL/Parquet manifests, pools, leakage/exclusion audits, selection list, and summary. The separate exposure output is deterministic for the included governor; its summary includes the output path.
