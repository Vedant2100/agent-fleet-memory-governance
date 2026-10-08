"""Authoritative, model-independent collection of worker repository changes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_SUFFIXES = frozenset({
    ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".jsx", ".kt", ".php", ".py", ".pyi", ".rb",
    ".rs", ".scala", ".scss", ".sh", ".sql", ".swift", ".ts", ".tsx",
    ".vue", ".xml",
})


def snapshot_working_tree(repo: str | Path) -> dict[str, Any]:
    """Capture the frozen starting commit/tree and require a clean checkout."""
    root = Path(repo).resolve(strict=True)
    commit = _git(root, "rev-parse", "HEAD").decode().strip()
    tree = _git(root, "rev-parse", f"{commit}^{{tree}}").decode().strip()
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").decode().splitlines()
    return {
        "repository_path": str(root),
        "initial_repository_commit": commit,
        "initial_repository_tree": tree,
        "initial_status_porcelain": status,
        "initial_tree_clean": not status,
    }


def collect_working_tree(
    repo: str | Path,
    initial: dict[str, Any],
    patch_path: str | Path,
    metadata_path: str | Path,
    *,
    worker_declared_submission: dict[str, Any],
    termination_reason: str,
) -> dict[str, Any]:
    """Save allowed source changes, excluding test paths and Finish output."""
    root = Path(repo).resolve(strict=True)
    initial_commit = str(initial["initial_repository_commit"])
    current_head = _git(root, "rev-parse", "HEAD").decode().strip()
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").decode().splitlines()
    untracked = _git_z(root, "ls-files", "--others", "--exclude-standard", "-z")
    initial_tracked = set(_git_z(root, "ls-tree", "-r", "--name-only", "-z", initial_commit))
    current_tracked = set(_git_z(root, "ls-files", "-z"))
    created_paths = current_tracked - initial_tracked
    all_changed = set(_git_z(root, "diff", "--name-only", "-z", initial_commit, "--"))
    tracked_changed = sorted(all_changed & initial_tracked)
    untracked_created = sorted(set(untracked) | created_paths)
    tracked_test_files = sorted(path for path in tracked_changed if is_test_path(path))
    untracked_test_files = sorted(path for path in untracked_created if is_test_path(path))
    untracked_source = sorted(
        path for path in untracked_created
        if is_source_path(path) and not is_test_path(path)
    )
    tracked_source = sorted(
        path for path in tracked_changed
        if is_source_path(path) and not is_test_path(path)
    )

    if untracked_source:
        literal_untracked = [f":(literal){path}" for path in untracked_source]
        _git(root, "add", "-N", "--", *literal_untracked)
    source_paths = sorted(set(tracked_source) | set(untracked_source))
    patch = (
        _git(
            root, "diff", "--binary", "--no-ext-diff", "--full-index",
            initial_commit, "--", *(f":(literal){path}" for path in source_paths),
        )
        if source_paths else b""
    )
    MAX_PATCH_BYTES = 1_000_000
    collector_error = None
    if len(patch) > MAX_PATCH_BYTES:
        collector_error = f"authoritative diff size ({len(patch)} bytes) exceeds safety threshold ({MAX_PATCH_BYTES} bytes)"
        patch = b""
    patch_target = Path(patch_path)
    patch_target.parent.mkdir(parents=True, exist_ok=True)
    patch_target.write_bytes(patch)

    record = {
        "schema_version": 2,
        **initial,
        "worker_declared_submission": worker_declared_submission,
        "termination_reason": termination_reason,
        "final_repository_commit": current_head,
        "git_status_porcelain": status,
        "tracked_changed_files": tracked_changed,
        "untracked_files_created": untracked_created,
        "tracked_test_files_excluded": tracked_test_files,
        "untracked_test_files_excluded": untracked_test_files,
        "tracked_source_files_changed": bool(tracked_source),
        "tracked_source_files": tracked_source,
        "relevant_untracked_files_created": untracked_source,
        "source_code_changed": bool(tracked_source or untracked_source),
        "authoritative_diff_bytes": len(patch),
        "authoritative_diff_sha256": hashlib.sha256(patch).hexdigest(),
        "repository_state_recovered": True,
        "collector_error": collector_error,
    }
    _write_json(Path(metadata_path), record)
    return record


def is_source_path(path: str) -> bool:
    return Path(path).suffix.lower() in SOURCE_SUFFIXES


def is_test_path(path: str) -> bool:
    """Return whether a repository path is a test file excluded from submissions."""
    parts = PurePosixPath(path).parts
    if any(part in {"test", "tests"} for part in parts[:-1]):
        return True
    return bool(
        parts
        and parts[-1].startswith("test_")
        and Path(parts[-1]).suffix.lower() == ".py"
    )


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
    )
    return result.stdout


def _git_z(repo: Path, *args: str) -> list[str]:
    return [row.decode("utf-8", errors="surrogateescape") for row in _git(repo, *args).split(b"\0") if row]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=True)
        stream.write("\n")
        stream.flush()
