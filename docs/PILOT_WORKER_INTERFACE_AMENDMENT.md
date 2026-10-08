# Pre-treatment worker-interface amendment

**Status:** frozen before the corrected qualification attempt; no governor or
treatment runs have occurred.

## Evidence prompting this amendment

Qualification job `289199` used the frozen targets
`sympy__sympy-21309`, `django__django-34176`, and
`sympy__sympy-16953`. All three workers reached the local Ollama endpoint, but
each submitted an empty patch after one assistant action. In the first
trajectory, the model's initial response was a prose implementation plan with
fabricated test output. The command parser rejected it with `FormatError`. The
format-retry message then asked for a command block, and the model issued only
`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`. The Apptainer environment treats
that command's successful output as terminal submission, so the task ended
without repository inspection or edits. The other two trajectories show the
same final action. This run did not measure coding ability.

The prior `qualification-attempt-289199.json` and raw trajectory/log files are
retained. The target IDs, target ordering, candidate histories, source-memory
union, evaluator, model, temperature, seed, context window, step limit, tool
image, and qualification thresholds are unchanged.

## Frozen correction

The worker interface now states the command-block format in the initial system
message, requires a repository-inspection command first, and describes the
completion sentinel as terminal. The format-retry message now tells the worker
to choose a command that advances inspection, implementation, or testing, and
not to use the sentinel to repair a formatting error. The instance prompt
states that an empty patch is a failure unless inspection establishes that no
change is required.

The proxy recorder now counts native Ollama `/api/chat` calls and reads
`prompt_eval_count` and `eval_count` from JSON responses, while retaining its
OpenAI-compatible usage parsing. The initial run's response bodies were not
preserved, so its exact token counts remain unavailable. Ollama documents those
native counters in its [API usage reference](https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx).

No code is tuned from any memory-treatment outcome: there are no such outcomes.
This is a single, pre-treatment correction of the demonstrated command-format
failure. The exact same three qualification tasks are run once with this fixed
interface. The corrected attempt must satisfy the original pass rule (three
nonempty patches and at least two canonical resolutions); otherwise stop with
no treatments and no further worker tuning.
