"""Hidden-label oracle ceiling; isolate this from ordinary governor adapters."""

from __future__ import annotations

from typing import Any, Sequence

from .base import Decision


class OracleReadBaseline:
    name = "oracle_known_related_ceiling"

    def __init__(self, related_source_ids_by_target: dict[str, set[str]]):
        self._related = related_source_ids_by_target

    def decide_read(self, target: dict[str, Any], pool: Sequence[dict[str, Any]]) -> list[Decision]:
        target_id = target["target_id"]
        related = self._related.get(target_id, set())
        return [
            Decision(
                "EXPOSE" if entry.get("memory", entry).get("source_task_id") in related else "WITHHOLD",
                confidence=1.0,
                rationale="hidden published-relation ceiling",
            )
            for entry in pool
        ]
