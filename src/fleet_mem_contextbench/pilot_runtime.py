"""Strict plan and artifact readers shared by burned-pilot entry points."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .treatments import unique_source_memories


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def analysis_target_ids(plan: dict[str, Any]) -> list[str]:
    """Return the frozen primary target subset, defaulting to the full pilot."""
    target_ids = plan.get("target_ids")
    selected = plan.get("analysis_target_ids", target_ids)
    if (
        not isinstance(target_ids, list) or not target_ids
        or not isinstance(selected, list) or not selected
        or len(selected) != len(set(selected))
        or not set(selected).issubset(target_ids)
    ):
        raise RuntimeError("primary analysis targets must be a nonempty unique subset of the frozen target universe")
    return list(selected)


def load_frozen_pilot(plan_path: str | Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    plan_file = Path(plan_path).resolve(strict=True)
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    _validate_frozen_plan_files(plan)
    protocol = PROJECT_ROOT / "docs/EXPERIMENT_PROTOCOL.md"
    if sha256_file(protocol) != plan.get("protocol_sha256"):
        raise RuntimeError("frozen protocol hash mismatch")
    manifest_path = PROJECT_ROOT / "artifacts/smoke/manifests/benchmark_manifest.jsonl"
    if sha256_file(manifest_path) != plan.get("benchmark_manifest_sha256"):
        raise RuntimeError("frozen benchmark manifest hash mismatch")
    relationship_path = PROJECT_ROOT / "artifacts/smoke/hidden/relationship_annotations.jsonl"
    if sha256_file(relationship_path) != plan.get("hidden_relation_annotations_sha256"):
        raise RuntimeError("frozen hidden relationship annotation hash mismatch")
    target_ids, pools = _load_frozen_pools(plan, manifest_path)
    memories = unique_source_memories(pools)
    _validate_frozen_memory_union(plan, memories)
    return plan, pools, memories


def _validate_frozen_plan_files(plan: dict[str, Any]) -> None:
    if plan.get("plan_version") != "burned-pilot-v2" or plan.get("protocol_status") != "FROZEN_BEFORE_TREATMENTS":
        raise RuntimeError("pilot protocol plan is not frozen burned-pilot-v2")
    expected_files = plan.get("experiment_file_sha256")
    if not isinstance(expected_files, dict) or not expected_files:
        raise RuntimeError("frozen plan has no experiment-code hash manifest")
    for relative_path, expected_hash in expected_files.items():
        path = PROJECT_ROOT / relative_path
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise RuntimeError(f"frozen experiment code/config changed: {relative_path}")
    amendment_path = plan.get("analysis_amendment_path")
    amendment_hash = plan.get("analysis_amendment_sha256")
    if amendment_path:
        path = PROJECT_ROOT / amendment_path
        if not path.is_file() or sha256_file(path) != amendment_hash:
            raise RuntimeError("frozen pre-treatment analysis amendment is missing or changed")
        analysis_target_ids(plan)


def _load_frozen_pools(
    plan: dict[str, Any], manifest_path: Path,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    target_ids = [row["target_id"] for row in read_jsonl(manifest_path)]
    if target_ids != plan.get("target_ids") or len(target_ids) != 11:
        raise RuntimeError("pilot target order/set differs from frozen plan")
    pools: dict[str, dict[str, Any]] = {}
    for target_id in target_ids:
        freeze = plan["target_pool_freeze"][target_id]
        path = PROJECT_ROOT / freeze["path"]
        if sha256_file(path) != freeze.get("file_sha256"):
            raise RuntimeError(f"frozen candidate history hash mismatch for {target_id}")
        pool = json.loads(path.read_text(encoding="utf-8"))
        if pool.get("pool_hash") != freeze.get("pool_hash") or pool.get("target", {}).get("target_id") != target_id:
            raise RuntimeError(f"candidate history metadata mismatch for {target_id}")
        pools[target_id] = pool
    return target_ids, pools


def _validate_frozen_memory_union(plan: dict[str, Any], memories: dict[str, dict[str, Any]]) -> None:
    canonical = json.dumps(memories, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    union_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if len(memories) != plan.get("unique_source_memory_count") or union_hash != plan.get("unique_source_memory_union_sha256"):
        raise RuntimeError("frozen union of source-only memories changed")


def clean_related_sources_by_target() -> dict[str, set[str]]:
    """Return only hidden known-related sources in the primary clean stratum."""
    audit_path = PROJECT_ROOT / "artifacts/smoke/hidden/leakage_audit.jsonl"
    clean_pairs = {
        (row.get("target_id"), row.get("source_id"))
        for row in read_jsonl(audit_path)
        if row.get("primary_stratum") == "CLEAN_TEMPORAL"
    }
    related: dict[str, set[str]] = {}
    relation_path = PROJECT_ROOT / "artifacts/smoke/hidden/relationship_annotations.jsonl"
    for row in read_jsonl(relation_path):
        pair = (row.get("target_id"), row.get("source_id"))
        if row.get("in_candidate_pool") is True and pair in clean_pairs:
            related.setdefault(str(pair[0]), set()).add(str(pair[1]))
    return related


def load_decisions(path: str | Path, memories: dict[str, dict[str, Any]], plan_path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    decision_rows = read_jsonl(path)
    expected_hash = sha256_file(plan_path)
    summary_path = Path(path).with_name(Path(path).name.replace("_decisions.jsonl", "_summary.json"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("plan_sha256") != expected_hash:
        raise RuntimeError(f"source decision table {path} belongs to a different plan")
    if summary.get("status") != "COMPLETE":
        raise RuntimeError(f"source decision table {path} is incomplete")
    from .treatments import validate_source_decisions

    validate_source_decisions(memories, decision_rows)
    if summary.get("decisions_sha256") != sha256_file(path):
        raise RuntimeError(f"source decision table hash mismatch: {path}")
    return decision_rows, summary
