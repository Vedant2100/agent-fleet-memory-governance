# AAMAS paper: automatic Overleaf preview from numbered rounds

The writer–critic workflow preserves manuscripts directly under `paper/round-0/`, `paper/round-1/`, and so on. **There is no `paper/current/` directory.**

Codex writes each new round and adds `paper/round-N/.overleaf-ready` **only after it has produced a coherent, reviewable draft**. GitHub Actions detects the highest numerically numbered marked round and pushes its LaTeX sources and figures to the **root** of the existing Overleaf project's Git `master` branch. Older rounds remain in GitHub; GitHub `main` is never touched. The marker is for **preview**, not a claim of completed scientific review or AAMAS submission readiness.

The automated workflow is at `.github/workflows/sync-paper-overleaf.yml`. It triggers when round files change on `handoff/aamas-2027-evidence` and can also be run manually via GitHub Actions. If an unfinished higher round lacks the marker, the previously marked round remains selected.

One-time connection: in GitHub Settings → Secrets and variables → Actions, set:
- `OVERLEAF_PROJECT_ID`: ID from the Overleaf project URL.
- `OVERLEAF_GIT_TOKEN`: Overleaf Git authentication token. Keep it private.

Overleaf Git integration access is required. After configuring secrets, re-run the workflow from Actions; adding secrets alone does not trigger a new run. Overleaf should select the **root `main.tex`** as main document. The official AAMAS `aamas.cls` and its dependencies must be available in the Overleaf project for the draft to compile.

The sync copies only manuscript assets, not experimental code. It preserves Overleaf template files not managed by this workflow and removes only previously synced manuscript files. Edit paper source in GitHub/Codex; otherwise Overleaf-only edits may conflict with GitHub being the source of truth. The project remains a provisional scientific draft until human review.
