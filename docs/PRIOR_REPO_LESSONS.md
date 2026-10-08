# Prior repository lessons

The two previous research repositories and the local SWE-ContextBench pilot were inspected read-only before this repository was implemented. This repository is independent and contains no runtime dependency on them.

## chainswe-organizational-knowledge

**What worked**

- Freezing the task set, source/target transitions, solver profile, and scorer before treatments made exclusions auditable.
- Gold-patch and no-patch controls exposed evaluator and image problems before agent outcomes were interpreted.
- The controlled source-slice reports separated resolution, FAIL_TO_PASS, PASS_TO_PASS, patch validity, and observed knowledge reuse. This kept negative transfer visible even when no target resolved.
- The source-only card interface and explicit provenance made unsupported scope and outcome claims detectable.

**What failed**

- A working evaluator did not make the scientific task set useful. The reviewed ChainSWE pool had few control-valid transitions, and the tested source lessons were often not used on targets.
- A fixed solver/tool integration failure overwhelmed memory conditions: the SWE-Edit calibration returned non-tool text for all 100 iterations, so it generated no patch. Solver/tool viability must be established separately from memory comparisons.
- On the controlled source slice, the no-memory arm resolved Jsonpickle while its human-card treatment did not; ten knowledge-treatment runs across five additional transitions produced no resolution. Other malformed patches regressed PASS_TO_PASS tests. Sharing can hurt, and an unresolved target can still show meaningful regression.
- Sequential task ordering alone did not guarantee an eligible, useful source experience.

**Reused**

- Keep evaluator controls independent of treatment runs.
- Freeze and hash task selection, source artifacts, solver/harness versions, and scorer inputs.
- Extract from one source task at a time. Record exact source evidence and leave source outcomes unknown unless an official result supports them.
- Report patch application, FAIL_TO_PASS, PASS_TO_PASS, token use, steps, tool calls, and latency separately.

**Explicitly refused**

- No solver/model tuning during a memory comparison.
- No changing the task set after inspecting treatment outcomes.
- No target issue, hidden tests, target patch, later commit, or target outcome may enter source-time extraction or write governance.
- No reliance on a successful evaluator smoke as evidence that the benchmark has sufficient candidate diversity.
- No singleton-pool “governance” result, and no masking negative transfer by reporting only resolution.

## sharedmemgov

The requested repository was fetched read-only at commit `8a8987f75d730b61d1f6d64c67367c00754810e0`. Its README, `research-notes.md`, and `sources.md` were reviewed.

**Novelty discipline preserved**

- Shared memory, memory write gates, access control, provenance, consistency, forgetting, and institutional memory already have prior work or implementations.
- A generic claim that an agent fleet needs a promotion gate is not a novelty claim.
- The narrower contribution here is an executable coding-task setting that separately measures cross-worker write decisions and later-worker read decisions, with outcomes scored by repository tests.
- The benchmark paper must position itself against the neighboring work listed in `sources.md`; its labels about gaps are synthesis judgments, not proof of priority.

## shared-mem-gov-pilot (SWE-ContextBench only)

**What worked**

- The pilot pinned the SWE-ContextBench Git and Hugging Face revisions and hashed each Lite parquet input.
- Its source reader kept target records out of source extraction and validated exact trajectory evidence.
- Deterministic provenance/scope checks could be separated from semantic governor judgment.
- The unchanged official scorer was retained while evaluator state handling was checked with no-fix and reference-patch controls.

**What failed or remains unproven**

- The released source traces do not contain official per-source evaluator outcomes. Tool output or an agent's final statement cannot be relabeled as canonical success.
- The published relationship links include same-PR/co-solution cases and sources that are not earlier by the task timestamp. Links cannot be used as a substitute for candidate-pool construction or chronology.
- A target/source task pair can have multiple relationship rows with distinct target PR URLs. Treating such rows as conflicting duplicates would discard valid metadata; the new audit retains all rows and aggregates conservatively.
- The first leakage pass treated any shared patch identifier as a solution hint and overflagged ordinary API names. The final screen requires an exact added-line string or substantial target/source patch overlap; symbols remain recorded separately.
- One linked source per target is not a realistic governance pool. This repository enumerates all earlier same-repository source tasks and audits the published edge separately.
- A functioning extractor and scorer do not prove that governed and Share-All arms expose different context. That is a separate pilot gate.

**Reused**

- Source-only extraction, exact evidence references, structured candidate cards, and deterministic validation are retained as small interfaces.
- The pinned evaluator and its tests remain upstream assets invoked without patching their grading rules.

**Explicitly refused**

- No dependency on the pilot directory, its curated target list, local environment, models, or evaluator adapter.
- No synthetic stress cases presented as natural results.
- No claim that the source trace's existence means its lesson helped, that the source succeeded canonically, or that a published relationship is correct governance.
