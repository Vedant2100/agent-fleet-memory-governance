# SWE-Edit worker qualification stop report

**Status: stopped before memory treatments.** Qualification job `289222` used
the frozen target set, SWE-Edit adapter, `gpt-6-luna` at `xhigh`, and the
unchanged SWE-ContextBench evaluator. The benchmark plan, target histories,
candidate cards, leakage rules, and evaluator were not changed.

## What was verified

- The model-free mini-SWE-agent 2.4.6 submission fixture passed: the exact
  `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt` output was
  parsed as the expected patch.
- The qualification job passed model access, canonical-control, and target-SIF
  preflights. The worker responses identify `gpt-6-luna`; the configured
  reasoning effort was `xhigh`.
- All three workers reached SWE-Edit's finish tool and produced nonempty
  patches. The first two patches were accepted and applied by the canonical
  evaluator.
- The plan hash remained
  `b6535c56e8db63dd72f4e7901960d995db533214df22e139034f99cd29f6a7f5`.

## Qualification outcomes

| Target | Rounds | Patch bytes | Peak context tokens | Canonical grade | FAIL_TO_PASS | PASS_TO_PASS | Resolved |
|---|---:|---:|---:|---|---:|---:|---|
| `sympy__sympy-21309` | 44 | 6,324 | 37,901 | complete; patch applied | 1/2 | 200/320 | no |
| `django__django-34176` | 42 | 2,788 | 43,136 | complete; patch applied | 1/6 | 166/166 | no |
| `sympy__sympy-16953` | 45 | 1,417 | cancelled before grade | not graded | not graded | not graded | not graded |

The qualification rule frozen before this run required three valid submissions,
three canonical grades, and at least two resolutions among the three targets.
After the first two canonical grades, the resolution count was 0/2. Even a
resolved third target could yield at most 1/3, so the required 2/3 pass threshold
was unreachable. Job `289222` was cancelled under the preregistered stop rule.
The third worker's patch is retained, but its task is **not** counted as a
solver failure because it received no canonical grade.

The first SymPy grade took 2,083.9 seconds. The Slurm job's recorded peak memory
was 46,210,800 KiB; the job ran for 55:21 before cancellation. The unusually
long SymPy evaluation came from the unchanged evaluator's extended, per-file
test timeout. The Django grade completed in 46.4 seconds.

## Patch-level diagnosis from the archived evaluator traces

The archive contains the worker patches, before/after test commands, canonical
reports, and container stdout. This resolves the earlier uncertainty about
whether the SymPy patch was imported: the evaluator ran tests from the patched
overlay, and `test_is_ge_le` passed after the patch.

### SymPy

- The patch passed `sympy/core/tests/test_relational.py::test_is_ge_le`, but
  left `sympy/assumptions/tests/test_satask.py::test_extract_predargs` failing.
  Its assertion expected `{x, y, z}` and received `{Eq(x, y), y > z}`. The same
  assertion fails in the archived before-patch run, so the trace does not show
  that the worker introduced this failure; it does show the required test was
  not resolved.
- All 120 nonpassing PASS_TO_PASS entries are in
  `sympy/utilities/tests/test_wester.py`. The before-patch run completed that
  file in 208.20 seconds (243 passed, 4 skipped, 150 xfailed). The patched run
  hit the unchanged 1,800-second file timeout at 46% progress. These are
  timeout-derived nonpasses, not 120 observed assertion failures.
- The patch routes each inequality comparison through `AssumptionsWrapper`
  for both operands. That broad change is a plausible cause of the severe
  slowdown in a comparison-heavy test file, but no profiler or isolated
  follow-up run was performed, so this mechanism is a diagnosis hypothesis,
  not a proven root cause.

### Django

- The patch fixes the reported ordinary duplicate-column case and preserves all
  166 PASS_TO_PASS tests. The other five FAIL_TO_PASS tests remain unresolved:
  `test_aggregation_subquery_annotation_related_field`,
  `test_aggregation_subquery_annotation_values_collision`,
  `test_aggregate_and_annotate_duplicate_columns_proxy`,
  `test_aggregate_and_annotate_duplicate_columns_unmanaged`, and
  `test_annotation_with_value`.
- The proxy case still reports `OperationalError: ambiguous column name: name`,
  showing that the alias handling fix does not cover that query shape.
- At least two remaining failures have evaluator/task compatibility ambiguity.
  `test_aggregation_subquery_annotation_related_field` reports that
  `DatabaseFeatures` lacks `allows_group_by_select_index` in both the archived
  before-patch and after-patch runs. The Django runner also reports that it
  cannot pickle a traceback while propagating test errors. Those traces do not
  support attributing this specific failure to the model patch. The canonical
  report still records the target unresolved; these details limit the claim
  that every Django nonpass is a worker defect.

Taken together, this was a real worker qualification stop: the fixed gate had
0/2 resolved grades and could not reach 2/3. The archived evidence identifies
one clear patch-level performance regression, one partial fix with uncovered
query shapes, and some Django failures whose underlying cause is obscured by
the task/evaluator environment. It does not establish that no stronger worker
could qualify. No memory comparison was run, so there is no transfer conclusion.

## Conclusion

The execution path is mechanically wired: the requested model ran, the
submission fixture passed, the frozen SIFs were used, and canonical grading
applied the patches. The worker did not pass its capability gate. Consequently
the No-Memory versus Oracle signal test and every governance treatment were not
run. These results provide no evidence for or against memory transfer; they
show that this worker configuration did not solve enough qualification tasks
to make that comparison interpretable.

This is a worker qualification failure, not a failure of the structural
candidate-history gate. No task, pool, or leakage change was made in response
to the outcomes.

Machine-readable outcomes are in
[`worker_qualification_stop.json`](../artifacts/burned-pilot/worker_qualification_stop.json).
The 44-file run archive and SHA-256 manifest are in
[`worker_qualification_289222/`](../artifacts/burned-pilot/worker_qualification_289222/).
