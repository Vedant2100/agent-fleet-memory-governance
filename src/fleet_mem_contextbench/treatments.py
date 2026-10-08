"""Frozen source-time admission and target-time exposure rules for pilot v2."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from .governors.base import Decision, Governor


RANDOM_SEED = 42
MAX_EXPOSED_MEMORIES = 3
WRITE_FORBIDDEN = {
    "target", "target_id", "target_patch", "target_test_patch", "target_created_at",
    "relationship_type", "known_related", "gold_patch", "hidden_tests", "target_outcome",
}


def unique_source_memories(pools_by_target: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Deduplicate frozen pool cards and fail if an ID has conflicting source content."""
    result: dict[str, dict[str, Any]] = {}
    for target_id in sorted(pools_by_target):
        pool = pools_by_target[target_id]
        for entry in pool["candidate_pool"]:
            memory = entry["memory"]
            _assert_source_only(memory)
            memory_id = memory["memory_id"]
            previous = result.get(memory_id)
            if previous is not None and _canonical(previous) != _canonical(memory):
                raise ValueError(f"memory_id {memory_id} has conflicting source-only content")
            result[memory_id] = memory
    return dict(sorted(result.items()))


def freeze_source_decisions(memories: dict[str, dict[str, Any]], governor: Governor) -> list[dict[str, Any]]:
    """Ask the source-time governor once per unique memory, without target data."""
    rows = []
    source_order = sorted(
        memories.items(),
        key=lambda row: (
            _created_timestamp(row[1].get("created_at")),
            row[1]["source_task_id"], row[0],
        ),
    )
    for memory_id, memory in source_order:
        if memory["memory_id"] != memory_id:
            raise ValueError("source memory mapping key does not match memory_id")
        _assert_source_only(memory)
        decision = governor.decide_write(memory)
        decision.validate("write")
        rows.append({
            "memory_id": memory_id,
            "source_task_id": memory["source_task_id"],
            "candidate_sha256": _sha256(_canonical(memory)),
            "action": decision.action,
            "confidence": decision.confidence,
            "probabilities": decision.probabilities,
            "rationale": decision.rationale,
            "latency_ms": decision.latency_ms,
            "cost": decision.cost,
            "input_tokens": decision.input_tokens,
            "output_tokens": decision.output_tokens,
        })
    validate_source_decisions(memories, rows)
    return rows


def validate_source_decisions(
    memories: dict[str, dict[str, Any]], rows: Sequence[dict[str, Any]],
) -> None:
    """Require one binary, hash-matched write result for every source memory."""
    ids = [row.get("memory_id") for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("write decisions contain duplicate memory IDs")
    if set(ids) != set(memories):
        raise ValueError("write decision memory IDs do not match the frozen candidate universe")
    for row in rows:
        memory_id = row["memory_id"]
        if row.get("action") not in {"SHARE", "DO_NOT_SHARE"}:
            raise ValueError(f"{memory_id}: write action must be SHARE or DO_NOT_SHARE")
        if row.get("candidate_sha256") != _sha256(_canonical(memories[memory_id])):
            raise ValueError(f"{memory_id}: write decision is bound to different candidate content")
        if row.get("source_task_id") != memories[memory_id]["source_task_id"]:
            raise ValueError(f"{memory_id}: write decision source_task_id mismatch")


def freeze_size_matched_random(
    memories: dict[str, dict[str, Any]], governed_rows: Sequence[dict[str, Any]], seed: int = RANDOM_SEED,
) -> list[dict[str, Any]]:
    """Freeze a deterministic random admission set with exactly Jev's share count."""
    validate_source_decisions(memories, governed_rows)
    share_count = sum(row["action"] == "SHARE" for row in governed_rows)
    ranked = sorted(
        memories,
        key=lambda memory_id: (
            _sha256(f"fleet-mem-contextbench-burned-v2:random:{seed}:{memory_id}"), memory_id,
        ),
    )
    admitted = set(ranked[:share_count])
    return [
        {
            "memory_id": memory_id,
            "source_task_id": memories[memory_id]["source_task_id"],
            "candidate_sha256": _sha256(_canonical(memories[memory_id])),
            "action": "SHARE" if memory_id in admitted else "DO_NOT_SHARE",
            "confidence": None,
            "rationale": f"seeded size-matched random admission; seed={seed}",
            "seed": seed,
        }
        for memory_id in sorted(memories)
    ]


def deterministic_retrieval(pool: dict[str, Any], limit: int = MAX_EXPOSED_MEMORIES) -> list[dict[str, Any]]:
    """Return fixed newest-first candidates, independent of target text or admissions."""
    entries = list(pool["candidate_pool"])
    entries.sort(key=lambda row: (
        -_created_timestamp(row["memory"].get("created_at")),
        row["memory"]["source_task_id"], row["memory"]["memory_id"],
    ))
    return entries[:limit]


def treatment_exposure(
    *,
    target: dict[str, Any],
    pool: dict[str, Any],
    arm_id: str,
    admitted_ids: set[str],
    token_counter: Callable[[str], int] | None = None,
    read_governor: Governor | None = None,
    related_source_ids: set[str] | None = None,
    frozen_read_decisions: dict[str, Decision] | None = None,
    max_memories: int = MAX_EXPOSED_MEMORIES,
) -> dict[str, Any]:
    """Materialize one preregistered target memory view."""
    shared_ids, retrieval_window, retrieved = _select_retrieved(
        pool, arm_id, admitted_ids, related_source_ids, max_memories,
    )
    decisions = _decide_exposure(
        target, arm_id, retrieved, read_governor, frozen_read_decisions,
    )
    exposed, token_counts, card_sizes = _materialize_exposure(
        arm_id, retrieved, decisions, token_counter,
    )
    exposed_cards = [render_worker_memory(memory) for memory in exposed]
    exposed_ids = {memory["memory_id"] for memory in exposed}
    read_withholds = sum(row["action"] == "WITHHOLD" for row in decisions.values())
    return {
        "arm_id": arm_id,
        "candidate_pool_size": len(pool["candidate_pool"]),
        "shared_memory_ids": sorted(shared_ids),
        "write_admission_rate": len(shared_ids) / max(1, len(pool["candidate_pool"])),
        "retrieval_window_ids": [entry["memory"]["memory_id"] for entry in retrieval_window],
        "retrieved_memory_ids": [entry["memory"]["memory_id"] for entry in retrieved],
        "read_decisions": decisions,
        "exposed_memory_ids": [memory["memory_id"] for memory in exposed],
        "exposed_memories": exposed,
        "memory_token_counts": token_counts,
        "memory_token_counts_exposed": {memory_id: token_counts[memory_id] for memory_id in sorted(exposed_ids)},
        "memory_tokens_exposed": sum(token_counts[memory["memory_id"]] for memory in exposed),
        "memory_token_count_method": (
            "CUSTOM_TOKEN_COUNTER" if token_counter else "CHARACTER_COUNT_DIVIDED_BY_FOUR_ESTIMATE"
        ),
        "memory_card_sizes": card_sizes,
        "exposed_memory_card_sizes": {memory_id: card_sizes[memory_id] for memory_id in sorted(exposed_ids)},
        "memory_serialized_bytes_exposed": sum(len(text.encode("utf-8")) for text in exposed_cards),
        "memory_count_budget": max_memories,
        "read_abstention_rate": read_withholds / len(decisions) if decisions else None,
    }


def _select_retrieved(
    pool: dict[str, Any], arm_id: str, admitted_ids: set[str],
    related_source_ids: set[str] | None, max_memories: int,
) -> tuple[set[str], list[dict[str, Any]], list[dict[str, Any]]]:
    entries = list(pool["candidate_pool"])
    if arm_id == "A_NO_MEMORY":
        return set(), [], []
    if arm_id == "F_ORACLE_RELATED_CEILING":
        if related_source_ids is None:
            raise ValueError("oracle ceiling requires hidden known-related source IDs")
        related = [entry for entry in entries if entry["memory"]["source_task_id"] in related_source_ids]
        related.sort(key=lambda row: _recency_key(row["memory"]))
        return (
            {entry["memory"]["memory_id"] for entry in related},
            related[:max_memories], related[:max_memories],
        )
    pool_ids = {entry["memory"]["memory_id"] for entry in entries}
    shared_ids = set(admitted_ids) & pool_ids
    retrieval_window = deterministic_retrieval(pool, max_memories)
    retrieved = [entry for entry in retrieval_window if entry["memory"]["memory_id"] in shared_ids]
    return shared_ids, retrieval_window, retrieved


def _decide_exposure(
    target: dict[str, Any], arm_id: str, retrieved: list[dict[str, Any]],
    read_governor: Governor | None, frozen_read_decisions: dict[str, Decision] | None,
) -> dict[str, dict[str, Any]]:
    if arm_id != "E_JEV_WRITE_READ":
        return {
            entry["memory"]["memory_id"]: {
                "action": "EXPOSE", "confidence": 1.0,
                "rationale": "fixed deterministic retrieval/exposure policy",
                "latency_ms": 0.0, "cost": 0.0,
            }
            for entry in retrieved
        }
    memories = [entry["memory"] for entry in retrieved]
    outputs = _call_read_governor(target, memories, read_governor, frozen_read_decisions)
    if len(outputs) != len(memories):
        raise ValueError("read governor must return one decision per retrieved memory")
    for decision in outputs:
        decision.validate("read")
    return {
        entry["memory"]["memory_id"]: _decision_record(decision)
        for entry, decision in zip(retrieved, outputs)
    }


def _call_read_governor(
    target: dict[str, Any], memories: list[dict[str, Any]],
    read_governor: Governor | None, frozen: dict[str, Decision] | None,
) -> list[Decision]:
    if frozen is not None:
        memory_ids = [memory["memory_id"] for memory in memories]
        missing = [memory_id for memory_id in memory_ids if memory_id not in frozen]
        if missing:
            raise ValueError(f"frozen Jev read table is missing retrieved memories: {missing}")
        return [frozen[memory_id] for memory_id in memory_ids]
    if read_governor is None:
        raise ValueError("Jev Write+Read requires a frozen read table or target-time read governor")
    return list(read_governor.decide_read(target, memories))


def _materialize_exposure(
    arm_id: str, retrieved: list[dict[str, Any]],
    decisions: dict[str, dict[str, Any]], token_counter: Callable[[str], int] | None,
) -> tuple[list[dict[str, Any]], dict[str, int], dict[str, dict[str, int]]]:
    exposed: list[dict[str, Any]] = []
    token_counts: dict[str, int] = {}
    card_sizes: dict[str, dict[str, int]] = {}
    for entry in retrieved:
        memory = entry["memory"]
        visible_memory = _concise_oracle_memory(memory) if arm_id == "F_ORACLE_RELATED_CEILING" else memory
        rendered = render_worker_memory(visible_memory)
        token_count = _memory_token_count(rendered, token_counter)
        memory_id = memory["memory_id"]
        token_counts[memory_id] = token_count
        card_sizes[memory_id] = _card_size(rendered)
        if decisions.get(memory_id, {}).get("action") == "EXPOSE":
            exposed.append(visible_memory)
    return exposed, token_counts, card_sizes


def _memory_token_count(rendered: str, token_counter: Callable[[str], int] | None) -> int:
    count = token_counter(rendered) if token_counter else max(1, len(rendered) // 4)
    if not isinstance(count, int) or count < 0:
        raise ValueError("memory token counter must return a nonnegative integer")
    return count


def _card_size(rendered: str) -> dict[str, int]:
    return {
        "serialized_bytes": len(rendered.encode("utf-8")),
        "characters": len(rendered),
        "character_based_token_estimate": max(1, len(rendered) // 4),
    }


def _recency_key(memory: dict[str, Any]) -> tuple[float, str, str]:
    return (
        -_created_timestamp(memory.get("created_at")),
        memory["source_task_id"], memory["memory_id"],
    )


def _decision_record(decision: Decision) -> dict[str, Any]:
    return {
        "action": decision.action, "confidence": decision.confidence,
        "probabilities": decision.probabilities, "rationale": decision.rationale,
        "latency_ms": decision.latency_ms, "cost": decision.cost,
        "input_tokens": decision.input_tokens, "output_tokens": decision.output_tokens,
    }

def _assert_source_only(memory: dict[str, Any]) -> None:
    def visit(value: Any) -> set[str]:
        if isinstance(value, dict):
            found = WRITE_FORBIDDEN.intersection(value)
            for child in value.values():
                found |= visit(child)
            return found
        if isinstance(value, list):
            return set().union(*(visit(item) for item in value)) if value else set()
        return set()

    leaked = visit(memory)
    if leaked:
        raise ValueError(f"source-time candidate contains target/hidden fields: {sorted(leaked)}")


def _created_timestamp(value: str | None) -> float:
    if not value:
        return float("-inf")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    timestamp = datetime.fromisoformat(normalized)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.timestamp()


def render_worker_memory(memory: dict[str, Any]) -> str:
    """Serialize the exact source-derived fields inserted into the worker prompt."""
    fields = (
        "source_task_id", "claim", "memory_type", "scope", "preconditions", "evidence",
        "evidence_locations", "files_or_symbols", "generality", "negative_transfer_risk",
    )
    visible = {field: memory[field] for field in fields if field in memory}
    return json.dumps(visible, ensure_ascii=False, sort_keys=True, indent=2)


def _concise_oracle_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Render a deliberately concise known-related ceiling while preserving provenance."""
    fields = (
        "memory_id", "source_task_id", "claim", "memory_type", "scope",
        "preconditions", "evidence", "evidence_locations", "files_or_symbols",
    )
    concise = {field: memory[field] for field in fields if field in memory}
    for field in ("preconditions", "evidence", "evidence_locations", "files_or_symbols"):
        value = concise.get(field)
        if isinstance(value, list):
            concise[field] = value[:3]
        elif isinstance(value, str) and len(value) > 500:
            concise[field] = value[:497] + "..."
    return concise


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
