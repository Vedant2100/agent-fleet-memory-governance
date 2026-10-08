# Structural kill gate

This gate is evaluated over all 99 SWE-ContextBench Lite targets before any agent run. A target qualifies only if it has at least one strict-prior, same-repository published relation that is distinct-PR and clean under the frozen automatic reference/patch screen. Candidate-pool construction itself ignores all relation labels.

The pool is every strict-prior experience in the same repository. The diagnostic separately counts non-linked entries with overlap in non-boilerplate issue terms, technical identifiers, or explicit paths. It does not call mere repository membership or recency a plausible match. This is an automatic lexical proxy; it can still overcount noisy term overlap and should not be described as a human semantic relevance label.

The frozen smoke selection takes the first 16 SHA-256-ranked eligible IDs or all eligible IDs if fewer exist. The full per-target screen and a hidden casebook of candidate IDs and overlap reasons are emitted with the release. The casebook supports targeted manual review without putting relation labels into governor input.

Illustrative source-only pool checks from the selected sample:

- `sympy__sympy-19235` asks for inverse-trigonometric style support. Its strict-prior pool includes the linked LaTeX inverse-trigonometric printer task plus other printer work (including `sympy__sympy-11897` and `sympy__sympy-16106`), rather than only that linked source.
- `matplotlib__matplotlib-22482` asks about saving a figure containing an interactive slider. The history includes the linked slider-related task and other slider/widget and figure-unpickling tasks, including `matplotlib__matplotlib-22711`, `matplotlib__matplotlib-25433`, and `matplotlib__matplotlib-23476`.
- `django__django-35356` concerns recursive `OneToOneField` relationships with `select_related()` and `only()`. Its history includes the linked reverse-one-to-one query task and a separate `QuerySet.only()`/`select_related()` proxy-model task, `django__django-15814`.

These examples establish that nontrivial histories are present; they are not a blinded adjudication of every pool item. The benchmark has only 11 clean linked targets in this release, so the gate passes narrowly and limits the breadth of the first executable pilot.
