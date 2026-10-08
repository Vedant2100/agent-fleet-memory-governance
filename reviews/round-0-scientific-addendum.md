# Round 0 scientific addendum — research decisions, not handoff mechanics

**Status:** Substantive supplement to `reviews/round-0.md`, not a second Round 0 review. **Verdict remains MAJOR REVISION.** Prepared after inspecting the unchanged Round 0 manuscript and the newer frozen v5 archive. Scientific soundness and useful revision decisions take priority over checksums, commit metadata, or paper formatting.

## 1. The most revealing missing analysis: where the annotated related record goes

Using the frozen target pools, the published source–target relationship annotations, and the saved Jev write/read decision tables, the following **target-level** counts are directly reproducible:

- In **8 of 10** primary target histories, the annotated related source is among the three most recent records selected by the fixed retrieval rule. In two targets (django-34176 and sympy-19235) it is not, so no write/read controller can expose it under this retrieval rule.
- The source-time Jev write policy admits that annotated record for only **2 of those 8** target histories: django-35356 and scikit-learn-13771. It rejects the annotated record for the other **6 of 8**.
- The target-time Jev read policy exposes the annotated record for only **1 of 8** target histories: django-35356. It withholds the admitted record for scikit-learn-13771.
- **Crucial dependence caveat:** the six target-level write rejections are *not six independent source decisions*. Three SymPy targets (16342, 16946, 16953) all refer to rejected source sympy-16988; three others (21203, 21309, 9384) all refer to rejected source sympy-21055. One decision is reused across multiple targets, as intended by the design. The result describes coverage across targets, not a six-trial accuracy estimate.

This directly exposes the proposed global-admission versus later-task-relevance tension. It is more scientifically informative than reporting 123/211 globally admitted cards. **Do not call the six rejections mistakes or failures without an independent usefulness test.** The benchmark relation label identifies a related source; it does not prove that its issue-text card helps the worker or that admitting it would improve the final patch. The next paper should explain *why* these decisions occurred, whether a related source would be useful under the actual representation, and whether an alternative admission policy would preserve it.

A concrete illustration: sympy-16946 has annotated related source sympy-16988 in its three most recent records. Jev Write rejects it, admits two other cards, and Jev Read withholds those two. This is an observed selection pathway, not an observed causal improvement from the rejected source.

## 2. The design lacks a clean test of the two decisions separately

The actual treatment arms are No Memory, Share-All with fixed retrieval, Random global admission with fixed retrieval, Jev Write with fixed retrieval, and Jev Write+Read. **Share-All+Jev Read is missing.** The original smoke `experiment_arms.json` contained a Share-All/Governed-Read arm, but the later pilot protocol/treatment set does not evaluate that cell. Therefore the current study cannot estimate the independent read-filter effect under Share-All or the interaction between source-time and target-time decisions. Avoid claiming a complete factorial decomposition.

A useful compact design table would cross source admission (Share-All versus Jev Write) with read selection (fixed versus Jev Read), alongside No Memory and random admission. If further evaluations are infeasible, explicitly state that the experiment measures only three observed policy bundles rather than the independent effects of two stages. Add simple retrieval/count-matched controls only when the worker and evaluator are stable; do not silently reinterpret the existing global 123-card random match as per-target budget matching.

## 3. Ten task IDs are not ten independent repairs

The relationship annotations map the ten primary target IDs to **eight distinct target pull requests**: sympy-16342 and sympy-16953 both map to SymPy PR 17526; sympy-21309 and sympy-9384 both map to PR 21309. Shared underlying repairs reduce effective diversity and can create correlated outcomes. Show the target-PR grouping and do not present ten observations as ten independent software-change problems. With only seven fully paired targets, uncertainty is already large.

## 4. The key scientific validity question is whether the memory representation can help at all

Each 'experience' card combines historical issue text and source reference-change paths. It is not an agent-generated successful repair trace or a distilled lesson from an agent's actions; source worker outcomes are unknown. A relation label or historical issue description does not by itself establish usable knowledge transfer. The no-memory versus known-related diagnostic changes executable outcomes on 3/10 tasks, but the related-memory condition resolves 1/10 versus 2/10 for No Memory. **Behavioral sensitivity is not a positive memory signal.**

Before investing in a sophisticated governor, establish a credible *positive control* using a handful of actual source-agent trajectories or clearly validated lessons and repeated, paired worker runs. Distinguish a negative result about this particular card representation from a general negative result about memory governance.

## 5. Repeatability remains the most serious causal blocker

For sympy-21203 and sympy-21309, the saved Jev Write+Read worker task prompt is identical to the earlier No-Memory prompt, yet executable grades differ. No conclusion about memory causing improvement or regression follows from this pair without repeated controls and harmonized patch/evaluator handling. Inspect the authoritative submitted patch rather than inferring its content from `git status`. If repeats cannot be run, report this as an exploratory *reliability limitation* and narrow causal language.

## 6. Correct the prior review's priority and protocol characterization

- Treat outdated results coverage, SHA values, manifests, Overleaf and bibliography cleanup as **editorial/reproducibility maintenance**, not top scientific criticisms.
- The original written protocol states that fewer than three No-Memory successes stops **a larger study**, while also specifying that the ten-target pilot arms are run. A prior qualification gate was amended before the later signal experiment. It is reasonable to require transparent amendments and exploratory labeling; it is **not yet justified** to call continuation of the ten-target pilot a breach of a preregistered stop rule. Correct the original review's insinuation.
- The frozen v5 handoff reports **31/40** completed B–E grades (B 8, C 8, D 7, E 8); the added sympy-16953 E run is unresolved (F2P 0/11, P2P 443/443). Only seven targets have all B–E grades. This new partial result does not justify changing the Round 0 scientific verdict or comparing unmatched denominators.

## 7. Academic prose and terminology — concrete revision guidance

The manuscript is generally restrained, not full of promotional AI clichés, but its title and abstractions overstate the demonstrated setting.

| Round 0 wording | Problem | Better direction |
| --- | --- | --- |
| 'From Local Experience to Shared Knowledge in Coding-Agent Fleets' (title) | Suggests learned experience and operating fleets; neither is evaluated. | 'Selecting Earlier Task Records for Coding Agents' (subject to conference title-change rules). |
| 'source-time admission decision' (Introduction) | Technical-sounding label before readers understand the action. | 'whether to store a record from an earlier task'; introduce 'admission' only if needed later. |
| 'provided-experience card' (Study Design) | Nonstandard term obscures that the record is assembled from issue text and touched paths. | 'historical task record' or 'task-derived context card', defined once. |
| 'the intervention is mechanically meaningful' (Discussion) | Evaluative filler rather than a scientific observation. | 'The two filters changed which records the worker received.' |
| 'the study’s potential contribution is a controlled question' (Discussion) | A research question alone is not a contribution. | State a demonstrated finding with scope, or explicitly call this a pilot whose research contribution remains unresolved. |
| 'Oracle Ceiling' (condition F in earlier protocol) | A label-derived record is not a performance upper bound; it performs worse than No Memory. | 'known-related-memory diagnostic'. |

A first-time AAMAS reviewer needs an intuitive diagram with a **real annotated source and later target**, showing candidate pool → fixed retrieval → global write decision → read decision → worker context → executable grade. The present example names source issues but does not explain *why the annotated related source could matter*, or what useful information it actually contains. Do not fabricate a beneficial transfer story.

## Required writer response, ordered by scientific value

1. Add a target-by-target decision-flow analysis of annotated related records, with dependence and usefulness caveats; use the verified 8→2→1 counts.
2. Explain the missing Share-All+Jev Read cell and avoid independent-effect claims without it.
3. Group targets by underlying pull request and adjust interpretation.
4. Establish whether the chosen historical-task representation has a credible positive transfer signal; if not, frame the negative result specifically to that representation.
5. Repeat/standardize no-memory worker runs, or explicitly limit causal inference.
6. Only then revise title, abstract, conventional terminology, references, evidence status and AAMAS formatting.

**No new Round 1 manuscript was present at this check.** Preserve the existing Round 0 critique; do not trigger a duplicate `PAPER_WRITER round=1`. This addendum is scientific feedback for the writer already handed off to Round 1.
