"""Small adapter for the pinned SWE-ContextBench Lite parquet release."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Task:
    task_id: str
    repo: str
    created_at: str | None
    base_commit: str | None
    environment_setup_commit: str | None
    problem_statement: str
    hints_text: str
    patch: str
    test_patch: str
    fail_to_pass: tuple[str, ...]
    pass_to_pass: tuple[str, ...]
    raw: dict[str, Any]

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Task":
        task_id, repo = row.get("instance_id"), row.get("repo")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task row requires a non-empty instance_id")
        if not isinstance(repo, str) or not repo:
            raise ValueError(f"{task_id}: task row requires a non-empty repo")
        return cls(
            task_id=task_id, repo=repo, created_at=_optional_string(row.get("created_at")),
            base_commit=_optional_string(row.get("base_commit")),
            environment_setup_commit=_optional_string(row.get("environment_setup_commit")),
            problem_statement=str(row.get("problem_statement") or ""),
            hints_text=str(row.get("hints_text") or ""), patch=str(row.get("patch") or ""),
            test_patch=str(row.get("test_patch") or ""),
            fail_to_pass=_to_tuple(row.get("FAIL_TO_PASS")),
            pass_to_pass=_to_tuple(row.get("PASS_TO_PASS")), raw=dict(row),
        )

    def public_target(self) -> dict[str, Any]:
        """Fields available to a target worker and read governor."""
        return {
            "target_id": self.task_id, "repository": self.repo,
            "target_created_at": self.created_at, "base_commit": self.base_commit,
            "environment_setup_commit": self.environment_setup_commit,
            "problem_statement": self.problem_statement,
        }


def load_parquet_rows(path: str | Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to read SWE-ContextBench parquet files") from exc
    return parquet.read_table(path).to_pylist()


def load_parquet_tasks(path: str | Path) -> list[Task]:
    return [Task.from_row(row) for row in load_parquet_rows(path)]


def deduplicate_tasks(tasks: Iterable[Task], label: str) -> dict[str, Task]:
    result: dict[str, Task] = {}
    for task in tasks:
        previous = result.get(task.task_id)
        if previous is not None and previous.raw != task.raw:
            raise ValueError(f"conflicting duplicate {label} task ID: {task.task_id}")
        result[task.task_id] = task
    return result


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _to_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        return tuple(value.splitlines())
    return ()
