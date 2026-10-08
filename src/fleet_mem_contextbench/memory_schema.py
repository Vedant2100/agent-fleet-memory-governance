"""Stable source-memory records and source-only candidate validation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from .data import Task


EXTRACTOR_VERSION = "provided-experience-metadata-v1"
CANONICAL_SOURCE_EVALUATOR = "SWE-ContextBench evaluation.sh (lite), unchanged"
MEMORY_TYPES = {
    "REPOSITORY_CONVENTION", "PROCEDURE", "ARCHITECTURE", "FAILURE_AVOIDANCE",
    "DEBUGGING_HEURISTIC", "TESTING_WORKFLOW", "ENVIRONMENT_SETUP", "EPISODIC_EXAMPLE",
}


@dataclass(frozen=True)
class MemoryCandidate:
    memory_id: str
    source_task_id: str
    repository: str
    source_worker_id: str | None
    source_outcome: dict[str, Any]
    created_at: str | None
    claim: str
    memory_type: str
    scope: dict[str, Any]
    preconditions: str
    evidence: tuple[str, ...]
    evidence_locations: tuple[str, ...]
    files_or_symbols: tuple[str, ...]
    generality: float | None
    negative_transfer_risk: float | None
    provenance_hash: str
    source_mode: str
    extractor_version: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence"] = list(self.evidence)
        value["evidence_locations"] = list(self.evidence_locations)
        value["files_or_symbols"] = list(self.files_or_symbols)
        return value


def memory_from_provided_experience(source: Task) -> MemoryCandidate:
    """Build a smoke-only card from this source task; no target argument exists."""
    paths = tuple(sorted(patch_paths(source.patch)))
    description = _compact(source.problem_statement, 320)
    path_note = ", ".join(paths[:8]) if paths else "no implementation path recovered"
    claim = f"Earlier task experience concerned: {description}. Its reference change touched: {path_note}."
    provenance = {
        "source_task_id": source.task_id,
        "repository": source.repo,
        "created_at": source.created_at,
        "base_commit": source.base_commit,
        "patch_sha256": _sha256(source.patch),
        "problem_sha256": _sha256(source.problem_statement),
    }
    provenance_hash = _sha256(_canonical(provenance))
    memory_id = _sha256(f"{source.task_id}:{EXTRACTOR_VERSION}:{provenance_hash}")[:24]
    return MemoryCandidate(
        memory_id=memory_id,
        source_task_id=source.task_id,
        repository=source.repo,
        source_worker_id=None,
        source_outcome={
            "status": "unknown",
            "evidence_status": "reference_patch_available_not_agent_outcome",
        },
        created_at=source.created_at,
        claim=claim,
        memory_type="EPISODIC_EXAMPLE",
        scope={"repository": source.repo, "paths": list(paths[:8])},
        preconditions="Inspect the current target code and tests; this is a prior task example, not a prescription.",
        evidence=(description,),
        evidence_locations=paths[:8],
        files_or_symbols=paths[:8],
        generality=None,
        negative_transfer_risk=None,
        provenance_hash=provenance_hash,
        source_mode="PROVIDED_EXPERIENCE_SMOKE",
        extractor_version=EXTRACTOR_VERSION,
    )


def memory_from_trajectory(source: Task, record: dict[str, Any]) -> MemoryCandidate:
    """Validate a worker-proposed lesson against exact source trajectory evidence."""
    forbidden = {"target_id", "target_patch", "target_test_patch", "relationship_type", "known_related"}
    leaked = forbidden.intersection(record)
    if leaked:
        raise ValueError(f"trajectory candidate contains target-side fields: {sorted(leaked)}")
    if record.get("source_task_id") != source.task_id:
        raise ValueError("trajectory candidate source_task_id mismatch")
    if record.get("repository") != source.repo:
        raise ValueError("trajectory candidate repository mismatch")
    trajectory = record.get("trajectory_text")
    if not isinstance(trajectory, str) or not trajectory:
        raise ValueError("trajectory candidate requires source-only trajectory_text")
    claim = record.get("claim")
    evidence = record.get("evidence")
    if not isinstance(claim, str) or not claim.strip() or not isinstance(evidence, list) or not evidence:
        raise ValueError("trajectory candidate requires a claim and evidence array")
    if any(not isinstance(item, str) or not item or item not in trajectory for item in evidence):
        raise ValueError("every evidence item must be an exact substring of the source trajectory")
    memory_type = record.get("memory_type")
    if memory_type not in MEMORY_TYPES - {"EPISODIC_EXAMPLE"}:
        raise ValueError("trajectory candidate has an unsupported memory_type")
    paths = tuple(sorted(set(map(str, record.get("files_or_symbols", [])))))
    trajectory_hash = _sha256(trajectory)
    provenance_hash = _sha256(_canonical({
        "source_task_id": source.task_id,
        "repository": source.repo,
        "source_created_at": source.created_at,
        "trajectory_sha256": trajectory_hash,
        "source_worker_id": record.get("source_worker_id"),
    }))
    return MemoryCandidate(
        memory_id=_sha256(f"{source.task_id}:{trajectory_hash}:{_canonical(record)}")[:24],
        source_task_id=source.task_id,
        repository=source.repo,
        source_worker_id=_optional(record.get("source_worker_id")),
        source_outcome=_source_outcome(record.get("source_outcome"), source.task_id),
        created_at=source.created_at,
        claim=claim.strip(),
        memory_type=memory_type,
        scope=record.get("scope") if isinstance(record.get("scope"), dict) else {"repository": source.repo},
        preconditions=str(record.get("preconditions") or "Revalidate against the current repository state."),
        evidence=tuple(evidence),
        evidence_locations=paths,
        files_or_symbols=paths,
        generality=_optional_float(record.get("generality")),
        negative_transfer_risk=_optional_float(record.get("negative_transfer_risk")),
        provenance_hash=provenance_hash,
        source_mode="FRESH_WORKER_TRAJECTORY",
        extractor_version=str(record.get("extractor_version") or "worker-proposal-v1"),
    )


def validate_memory(memory: MemoryCandidate) -> list[str]:
    errors: list[str] = []
    if memory.memory_type not in MEMORY_TYPES:
        errors.append("unsupported memory_type")
    if not memory.claim.strip():
        errors.append("empty claim")
    if not memory.provenance_hash or len(memory.provenance_hash) != 64:
        errors.append("missing or malformed provenance_hash")
    if memory.source_outcome.get("status") not in {"unknown", "verified_pass", "verified_fail", "mixed"}:
        errors.append("unsupported source_outcome status")
    return errors


def patch_paths(patch: str) -> set[str]:
    return {
        line[6:].strip()
        for line in patch.splitlines()
        if line.startswith("+++ b/") and line[6:].strip() != "/dev/null"
    }


def _compact(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text or "unspecified software task"


def _source_outcome(value: Any, source_task_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "unknown", "evidence_status": "no_official_source_result"}
    status = value.get("status")
    if status not in {"unknown", "verified_pass", "verified_fail", "mixed"}:
        return {"status": "unknown", "evidence_status": "unrecognized_source_result"}
    if status == "unknown":
        return {"status": "unknown", "evidence_status": str(value.get("evidence_status") or "source_result_unknown")}
    evidence_hash = value.get("evidence_sha256")
    if (
        value.get("task_id") != source_task_id
        or value.get("evidence_status") != "official_canonical_source_evaluation"
        or value.get("evaluator") != CANONICAL_SOURCE_EVALUATOR
        or not isinstance(evidence_hash, str)
        or not re.fullmatch(r"[a-f0-9]{64}", evidence_hash)
    ):
        raise ValueError("verified source outcomes require matching task ID, pinned evaluator, and evaluator-record SHA256")
    return {
        "status": status, "evidence_status": value["evidence_status"],
        "evaluator": value["evaluator"], "evidence_sha256": evidence_hash,
    }


def _optional(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
