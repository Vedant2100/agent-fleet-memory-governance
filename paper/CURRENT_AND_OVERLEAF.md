# AAMAS paper publication workflow

- `paper/round-N/`: immutable snapshots for writer–critic rounds (do not overwrite earlier rounds).
- `paper/current/`: the selected version mirrored to Overleaf. Currently a **provisional round-0 draft**, not an accepted or submission-ready paper.
- Update `paper/current/` **only when a complete revision is ready for viewing**. Copy that round's `main.tex`, `references.bib`, and any referenced figures or local LaTeX inputs into `paper/current/`, then commit on `handoff/aamas-2027-evidence`.
- GitHub Actions publishes just LaTeX source assets from `paper/current/` to the **root** of the Overleaf project's `master` branch. The rest of the coding/evidence repo is never exported.
- GitHub `main` is not used or modified.
- Treat GitHub as the source of truth for manuscript edits; Overleaf edits may conflict with later GitHub publication.
- This sync does not change the paper's scientific status, run any critic, or submit a paper.

## One-time account configuration

An Overleaf project with Git integration access is required (a paid/premium feature or eligible institutional access).

In GitHub: repo **Settings → Secrets and variables → Actions → New repository secret**, add:
- `OVERLEAF_PROJECT_ID`: ID from your Overleaf project URL, not the whole URL.
- `OVERLEAF_GIT_TOKEN`: Git authentication token generated in Overleaf Account Settings. Never put this token in repo files or chat.

The workflow is in `.github/workflows/sync-paper-overleaf.yml`. It runs on changes to `paper/current/` on the handoff branch. Without secrets it fails clearly and does not connect or push.

For correct compilation, add the official AAMAS 2027 class/template files (`aamas.cls` and any required dependencies) to the Overleaf project or include licensed, official source files in the published `paper/current/` tree. In Overleaf select root `main.tex` as the main document.

The workflow does not erase unrelated Overleaf files. It intentionally does not attempt bidirectional sync or automatically select an unfinished `round-N`.
