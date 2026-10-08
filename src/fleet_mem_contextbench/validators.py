"""Deterministic validation for visible manifests and hidden-label boundaries."""

from __future__ import annotations

from typing import Any

from .chronology import parse_timestamp
from .manifest import ARMS, validate_arms
from .pools import candidate_pool_hash


HIDDEN_KEYS = {
    "known_related", "relationship_type", "relationship_label", "target_patch",
    "target_test_patch", "gold_patch", "hidden_tests", "target_outcome",
}


def validate_candidate_pool(pool: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    target = pool.get("target", {})
    if not isinstance(target, dict):
        return ["target must be an object"]
    if "patch" in target or "test_patch" in target or "hints_text" in target:
        errors.append("governor-facing target contains hidden/evaluator-side task fields")
    entries = pool.get("candidate_pool")
    if not isinstance(entries, list):
        return errors + ["candidate_pool must be an array"]
    ids: set[str] = set()
    source_ids: set[str] = set()
    target_time = parse_timestamp(target.get("target_created_at"))
    if target_time is None:
        errors.append("target requires a parseable creation timestamp")
    for entry in entries:
        memory = entry.get("memory", {})
        memory_id = memory.get("memory_id")
        if not isinstance(memory_id, str) or memory_id in ids:
            errors.append("memory IDs must be non-empty and unique within a pool")
        ids.add(memory_id)
        source_id = memory.get("source_task_id")
        if source_id in source_ids:
            errors.append(f"source task appears more than once: {source_id}")
        source_ids.add(source_id)
        leaked = _find_hidden_keys(entry)
        if leaked:
            errors.append(f"governor-facing candidate contains hidden fields: {sorted(leaked)}")
        if memory.get("repository") != target.get("repository"):
            errors.append(f"candidate {memory_id} crosses repository boundary")
        if not memory.get("source_task_id"):
            errors.append(f"candidate {memory_id} lacks source task ID")
        source_time = parse_timestamp(memory.get("created_at"))
        try:
            strict_prior = source_time is not None and target_time is not None and source_time < target_time
        except TypeError:
            strict_prior = False
        if not strict_prior:
            errors.append(f"candidate {memory_id} is not strictly earlier than target")
    if pool.get("candidate_count") != len(entries):
        errors.append("candidate_count does not match pool size")
    if pool.get("pool_hash") != candidate_pool_hash(entries):
        errors.append("pool_hash does not match canonical candidate serialization")
    return errors


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors = []
    for field in ("target_id", "repository", "target_created_at", "base_commit", "canonical_evaluator", "candidate_pool_size"):
        if manifest.get(field) in (None, ""):
            errors.append(f"manifest missing {field}")
    if manifest.get("fail_to_pass_count", 0) <= 0:
        errors.append("manifest has no FAIL_TO_PASS tests")
    if manifest.get("pass_to_pass_count") is None:
        errors.append("manifest lacks PASS_TO_PASS count")
    if manifest.get("environment_validation_status") not in {"NOT_RUN", "PASS", "FAIL"}:
        errors.append("invalid environment_validation_status")
    return errors


def validate_factorial(arms: list[dict[str, Any]] | None = None) -> list[str]:
    return validate_arms(arms if arms is not None else ARMS)


def _find_hidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in HIDDEN_KEYS:
                found.add(key)
            found.update(_find_hidden_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_hidden_keys(item))
    return found
