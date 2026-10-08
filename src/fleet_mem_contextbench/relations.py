"""Read published links for hidden evaluation/audit use only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .data import load_parquet_rows


@dataclass(frozen=True)
class Relation:
    target_id: str
    source_id: str
    mapping_rows: tuple[dict[str, str | None], ...]

    @property
    def same_pr(self) -> bool | None:
        comparisons = [
            _canonical_url(row["target_pr_url"]) == _canonical_url(row["source_pr_url"])
            for row in self.mapping_rows
            if row["target_pr_url"] and row["source_pr_url"]
        ]
        if any(comparisons):
            return True
        if comparisons and len(comparisons) == len(self.mapping_rows):
            return False
        return None

    @property
    def source_issue_urls(self) -> tuple[str, ...]:
        return _unique(row["source_issue_url"] for row in self.mapping_rows)

    @property
    def source_pr_urls(self) -> tuple[str, ...]:
        return _unique(row["source_pr_url"] for row in self.mapping_rows)

    def hidden_record(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "source_id": self.source_id,
            "relationship_type": "PUBLISHED_RELATIONSHIP_TYPE_NOT_PROVIDED",
            "same_pr": self.same_pr,
            "target_pr_urls": list(_unique(row["target_pr_url"] for row in self.mapping_rows)),
            "target_issue_urls": list(_unique(row["target_issue_url"] for row in self.mapping_rows)),
            "source_pr_urls": list(self.source_pr_urls),
            "source_issue_urls": list(self.source_issue_urls),
            "mapping_row_count": len(self.mapping_rows),
            "distinct_mapping_count": len(set(_row_key(row) for row in self.mapping_rows)),
            "mapping_rows": [dict(row) for row in self.mapping_rows],
        }


def load_relations(path: str | Path) -> dict[tuple[str, str], Relation]:
    return relations_from_rows(load_parquet_rows(path))


def relations_from_rows(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], Relation]:
    grouped: dict[tuple[str, str], list[dict[str, str | None]]] = {}
    for row in rows:
        target_id, source_id = str(row["related_instance_id"]), str(row["experience_instance_id"])
        mapping = {
            "target_pr_url": _optional(row.get("related_pr_url")),
            "target_issue_url": _optional(row.get("related_issue_url")),
            "source_pr_url": _optional(row.get("experience_pr_url")),
            "source_issue_url": _optional(row.get("experience_issue_url")),
        }
        grouped.setdefault((target_id, source_id), []).append(mapping)
    return {
        key: Relation(key[0], key[1], tuple(values))
        for key, values in grouped.items()
    }


def _optional(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _unique(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _row_key(row: dict[str, str | None]) -> tuple[str | None, ...]:
    return tuple(row[key] for key in (
        "target_pr_url", "target_issue_url", "source_pr_url", "source_issue_url",
    ))


def _canonical_url(value: str) -> str:
    return value.rstrip("/").lower()
