# Codex instructions for AAMAS manuscript rounds

The paper lives exclusively in `paper/round-N/`, with one numbered directory per writer–critic iteration.

- Create `round-(N+1)/` when beginning a substantive new revision; never overwrite or delete an earlier round.
- Write the manuscript, references and figures inside that round, preserving self-contained relative paths.
- Keep critique, evidence notes and response-to-review alongside the new round as needed.
- Never create `paper/current/`; it is no longer part of this repository workflow.
- **At the end of a coherent, reviewable iteration**, place a file named `.overleaf-ready` into that round and commit it with the finished LaTeX inputs. Before this, do not add that file. The marker means **ready for Overleaf preview only**, not scientifically validated or submission-ready.
- Once marked ready, treat a round as an immutable snapshot and work in the next number.
- The GitHub workflow automatically selects the numerically highest marked round on this branch and publishes its `.tex`, `.bib`, and figure files to the same Overleaf project. It also installs the official AAMAS 2027 `aamas.cls` and `ACM-Reference-Format.bst` into Overleaf on **every sync**, so do not duplicate or modify conference style files in round directories. Do not copy files manually and do not change GitHub `main`.
- No automatic action can submit to AAMAS; final human scientific review is still required.
