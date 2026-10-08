# Development Amendment 04: Local worker candidate and gated Oracle continuation

**Recorded before any Oracle exposure.** The frozen target set, source cards,
relationships, evaluator, leakage rules, and prior worker records remain
unchanged. No memory treatment has run.

## Historical result and route change

**Original 2/3 worker qualification gate: FAILED.** GPT-6 Luna's historical
result remains failed and is not reclassified by this amendment. No memory
effect can be inferred from that gate.

The earlier development amendment specified a two-task GPT-5.6 Sol comparison.
The user later directed model exploration to use stronger local models without
changing the worker harness. The current local-model qualification is therefore
a separate development candidate run, not a Sol comparison and not a change to
the Luna record. Its outcome cannot be used as a confirmatory estimate.

The current candidate uses the already validated SWE-Edit worker adapter,
scaffold, task budget, tool interface, repository images, submission contract,
and canonical evaluator. It changes only the requested model to the locally
served Muse Glimmer model at `xhigh`; SymPy evaluator calls use the already
recorded prospective 3,600-second development timeout override. The candidate
must meet the existing three-task mechanics/resolution qualification: three
nonempty valid submissions, three applied canonical grades, and at least two
resolutions. Failure stops the signal run. Passing allows this candidate to be
used for the development-only Oracle signal test; it does not pass or replace
the historical Luna gate.

## Frozen Oracle continuation

After the candidate qualification and the already queued saved-patch regrades
finish, run only the paired No-Memory versus Oracle Known-Related Memory test
on the unchanged ten primary targets. The continuation checks the qualification
summary and worker/scaffold hashes before starting the local model service. A
failed qualification records a stop and starts no worker. Pair order, source
cards, known-related annotations, prompts, worker budget, target states, and
canonical evaluator remain frozen.

The Oracle gate is **at least two of ten complete pairs with executable
discordance**: a resolution change or a canonical FAIL_TO_PASS/PASS_TO_PASS
change. Behavioral patch differences alone do not pass this gate. Incomplete
pairs are reported as incomplete, never as agreement. The Oracle run is
development-only; none of its outcomes enter confirmatory effect estimates.
If the gate fails, stop before all governor treatments. Passing establishes
only that this worker/benchmark combination has a measurable Oracle signal; it
does not establish that any governor works.

