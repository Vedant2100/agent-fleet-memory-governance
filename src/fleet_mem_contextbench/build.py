"""Deterministic ContextBench Lite pool, audit, and smoke-release builder."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .data import Task, deduplicate_tasks, load_parquet_rows, load_parquet_tasks
from .leakage import audit_pair
from .manifest import ARMS
from .memory_schema import memory_from_provided_experience, memory_from_trajectory
from .pools import build_candidate_pool, plausible_distractor_count
from .relations import Relation, load_relations


HF_REVISION = "12c65bd15e2559bc808065565e941ee7bbbd008f"
CONTEXTBENCH_COMMIT = "12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b"
PROTOCOL_VERSION = "fleet-mem-contextbench-smoke-v1"
CANONICAL_EVALUATOR = "SWE-ContextBench evaluation.sh (lite), unchanged"


def build_release(
    experience_path: str | Path,
    target_path: str | Path,
    relation_path: str | Path,
    output_dir: str | Path,
    seed: int = 42,
    target_count: int = 16,
    hf_revision: str = HF_REVISION,
    contextbench_commit: str = CONTEXTBENCH_COMMIT,
    source_trajectory_jsonl: str | Path | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    for child in ("pools", "manifests", "hidden"):
        (out / child).mkdir(parents=True, exist_ok=True)
    experience_rows = load_parquet_tasks(experience_path)
    target_rows = load_parquet_tasks(target_path)
    experiences = deduplicate_tasks(experience_rows, "experience")
    targets = deduplicate_tasks(target_rows, "target")
    relation_raw = load_parquet_rows(relation_path)
    relation_map = load_relations(relation_path)
    target_ids = set(targets)
    relations = {key: value for key, value in relation_map.items() if key[0] in target_ids}
    source_by_repo: dict[str, list[Task]] = defaultdict(list)
    for task in experiences.values():
        source_by_repo[task.repo].append(task)
    memories = _source_memory_candidates(experiences, source_trajectory_jsonl)
    source_memory_mode = next(iter(memories.values())).source_mode if memories else "PROVIDED_EXPERIENCE_SMOKE"

    pools: dict[str, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    hidden_relations: list[dict[str, Any]] = []
    screens: list[dict[str, Any]] = []
    linked_clean: dict[str, list[str]] = defaultdict(list)

    for target in sorted(targets.values(), key=lambda task: task.task_id):
        repo_sources = source_by_repo.get(target.repo, [])
        pool = build_candidate_pool(target, repo_sources, memories)
        pools[target.task_id] = pool
        source_count = pool["candidate_count"]
        environment_metadata_valid = _environment_metadata_valid(target)
        for source in experiences.values():
            precedes, chronology_reason = _before(source, target)
            included = source.repo == target.repo and precedes is True
            reason = None if included else (
                "DIFFERENT_REPOSITORY" if source.repo != target.repo
                else chronology_reason or "NOT_IN_HISTORICAL_POOL"
            )
            if not included:
                exclusions.append({
                    "target_id": target.task_id, "source_id": source.task_id,
                    "target_repository": target.repo, "source_repository": source.repo,
                    "source_created_at": source.created_at, "target_created_at": target.created_at,
                    "exclusion_reason": reason,
                })
            if source.repo == target.repo:
                relation = relations.get((target.task_id, source.task_id))
                audit = audit_pair(
                    source, target, relation, source_count, included, reason,
                    environment_metadata_valid,
                )
                audits.append(audit)
                if relation and included and relation.same_pr is False and audit["primary_stratum"] == "CLEAN_TEMPORAL":
                    linked_clean[target.task_id].append(source.task_id)
        for (mapped_target, source_id), relation in sorted(relations.items()):
            if mapped_target != target.task_id:
                continue
            source = experiences.get(source_id)
            is_in_pool = bool(source and source.repo == target.repo and _before(source, target)[0] is True)
            reason = None
            if source is None:
                reason = "SOURCE_NOT_IN_LITE_EXPERIENCE_POOL"
            elif source.repo != target.repo:
                reason = "SOURCE_REPOSITORY_MISMATCH"
            elif not is_in_pool:
                reason = _before(source, target)[1] or "SOURCE_NOT_STRICTLY_EARLIER"
            hidden_relations.append({
                **relation.hidden_record(), "repository": target.repo,
                "source_created_at": source.created_at if source else None,
                "target_created_at": target.created_at,
                "source_before_target": _before(source, target)[0] if source else None,
                "in_candidate_pool": is_in_pool,
                "exclusion_reason": reason,
            })
        screen_audit = [row for row in audits if row["target_id"] == target.task_id]
        target_stratum = _target_stratum(screen_audit)
        known_sources = {source_id for (target_id, source_id) in relations if target_id == target.task_id}
        plausible = plausible_distractor_count(pool, known_sources)
        screens.append({
            "target_id": target.task_id, "repository": target.repo,
            "target_created_at": target.created_at,
            "candidate_count": source_count,
            "published_related_source_count": len(known_sources),
            "published_related_sources_in_pool": sum(source_id in {
                entry["memory"]["source_task_id"] for entry in pool["candidate_pool"]
            } for source_id in known_sources),
            "clean_prior_related_source_count": len(linked_clean[target.task_id]),
            "plausible_distractor_count": plausible,
            "target_primary_stratum": target_stratum,
            "environment_metadata_valid": environment_metadata_valid,
            "environment_valid": None,
            "environment_validation_status": "NOT_RUN",
        })

    clean_relation_targets = sorted(target_id for target_id, source_ids in linked_clean.items() if source_ids)
    screen_by_id = {row["target_id"]: row for row in screens}
    eligible_targets = [
        target_id for target_id in clean_relation_targets
        if screen_by_id[target_id]["candidate_count"] >= 5
        and screen_by_id[target_id]["plausible_distractor_count"] >= 2
    ]
    selected_ids = sorted(
        eligible_targets,
        key=lambda task_id: hashlib.sha256(f"{seed}:{PROTOCOL_VERSION}:{task_id}".encode()).hexdigest(),
    )[:max(0, target_count)]
    selected_set = set(selected_ids)
    manifest_rows = []
    for target_id in selected_ids:
        target = targets[target_id]
        pool = pools[target_id]
        pool_relative_path = f"pools/{target_id}.json"
        _write_json(out / pool_relative_path, pool)
        source_count = pool["candidate_count"]
        manifest = {
            **target.public_target(),
            "canonical_evaluator": CANONICAL_EVALUATOR,
            "canonical_evaluator_commit": contextbench_commit,
            "evaluator_task_id": target.task_id,
            "fail_to_pass_count": len(target.fail_to_pass),
            "pass_to_pass_count": len(target.pass_to_pass),
            "candidate_pool_path": pool_relative_path,
            "candidate_pool_hash": pool["pool_hash"],
            "candidate_pool_size": source_count,
            "source_count_for_target": source_count,
            "environment_metadata_valid": _environment_metadata_valid(target),
            "environment_valid": None,
            "environment_validation_status": "NOT_RUN",
            "track": "NATURAL_TRANSFER",
        }
        manifest_rows.append(manifest)
    _write_jsonl(out / "manifests/benchmark_manifest.jsonl", manifest_rows)
    _write_manifest_parquet(out / "manifests/benchmark_manifest.parquet", manifest_rows)
    _write_jsonl(out / "hidden/relationship_annotations.jsonl", hidden_relations)
    _write_jsonl(out / "hidden/leakage_audit.jsonl", audits)
    _write_jsonl(out / "hidden/excluded_sources.jsonl", exclusions)
    _write_jsonl(out / "hidden/full_population_screen.jsonl", screens)
    _write_jsonl(out / "hidden/structural_casebook.jsonl", _structural_casebook(
        selected_ids, pools, relations, linked_clean,
    ))
    selection = {
        "protocol_version": PROTOCOL_VERSION, "seed": seed, "selection_method": "SHA256(seed:protocol_version:target_id)",
        "eligibility": "at least one clean strict-prior different-PR relation, >=5 historical candidates, and >=2 non-linked issue/path/symbol overlap candidates",
        "eligible_target_ids": eligible_targets, "selected_target_ids": selected_ids,
        "requested_target_count": target_count,
    }
    _write_json(out / "hidden/selection.json", selection)
    counts = _candidate_counts(screens, selected_set)
    _write_counts_csv(out / "hidden/per_target_candidate_counts.csv", screens)
    _write_jsonl(out / "hidden/governance_stress.jsonl", [])
    _write_json(out / "manifests/experiment_arms.json", {
        "protocol_version": PROTOCOL_VERSION, "arms": ARMS,
        "stress_track_status": "NOT_POPULATED: smoke release has no adjudicated stale/conflict/failed-source cases; no synthetic cases added",
    })
    input_hashes = {
        "experience_parquet": _sha_file(experience_path),
        "targets_parquet": _sha_file(target_path),
        "relationships_parquet": _sha_file(relation_path),
    }
    if source_trajectory_jsonl is not None:
        input_hashes["source_trajectory_jsonl"] = _sha_file(source_trajectory_jsonl)
    provenance = {
        "dataset": "jiayuanz3/SWEContextBench", "huggingface_revision": hf_revision,
        "contextbench_git_commit": contextbench_commit,
        "benchmark_generation_commit": _generation_commit(out),
        "input_sha256": input_hashes,
        "source_memory_mode": source_memory_mode,
        "random_seed": seed, "filters": [
            "SWE-ContextBench Lite only", "same repository", "source created_at strictly before target created_at",
            "no relation-label pool filtering", "smoke targets require a clean strict-prior different-PR published relation",
        ],
        "source_task_ids": sorted(experiences), "target_task_ids": sorted(targets),
        "selected_target_ids": selected_ids,
    }
    _write_json(out / "manifests/source_provenance.json", provenance)
    summary = _summarize(experiences, targets, relation_raw, relations, screens, audits, selected_ids, counts)
    summary["source_memory_mode"] = source_memory_mode
    summary["provenance"] = provenance
    _write_json(out / "summary.json", summary)
    return summary


def _summarize(
    experiences: dict[str, Task], targets: dict[str, Task], raw_relations: list[dict[str, Any]],
    relations: dict[tuple[str, str], Relation], screens: list[dict[str, Any]], audits: list[dict[str, Any]],
    selected_ids: list[str], counts: dict[str, Any],
) -> dict[str, Any]:
    pool_sizes = [row["candidate_count"] for row in screens]
    selected = [row for row in screens if row["target_id"] in set(selected_ids)]
    linked_rows = [row for row in audits if row["known_related"]]
    distances = [row["temporal_distance_days"] for row in audits if row["in_candidate_pool"] and row["temporal_distance_days"] is not None]
    selected_id_set = set(selected_ids)
    smoke_distances = [
        row["temporal_distance_days"] for row in audits
        if row["target_id"] in selected_id_set and row["in_candidate_pool"]
        and row["temporal_distance_days"] is not None
    ]
    clean_targets = [row for row in screens if row["clean_prior_related_source_count"] > 0]
    by_stratum = Counter(row["primary_stratum"] for row in audits)
    return {
        "source_task_count": len(experiences), "target_task_count": len(targets),
        "target_repository_distribution": dict(sorted(Counter(task.repo for task in targets.values()).items())),
        "experience_repository_distribution": dict(sorted(Counter(task.repo for task in experiences.values()).items())),
        "relationship_raw_rows_for_lite_targets": sum(row["related_instance_id"] in targets for row in raw_relations),
        "relationship_unique_pairs_for_lite_targets": len(relations),
        "targets_with_any_published_relation": len({key[0] for key in relations}),
        "relationship_target_coverage": round(len({key[0] for key in relations}) / max(1, len(targets)), 4),
        "targets_with_any_strict-prior_same-repo_candidate": sum(size > 0 for size in pool_sizes),
        "targets_with_clean_prior_related_source": len(clean_targets),
        "targets_with_structurally_eligible_clean_pool": sum(
            row["clean_prior_related_source_count"] > 0 and row["candidate_count"] >= 5
            and row["plausible_distractor_count"] >= 2 for row in screens
        ),
        "strict_prior_published_related_pairs": sum(row["in_candidate_pool"] for row in linked_rows),
        "unique_published_related_edges_in_candidate_pool": sum(row["source_before_target"] is True and row["same_pr"] is False for row in linked_rows),
        "all_population_candidate_counts": _size_distribution(pool_sizes),
        "smoke_candidate_counts": _size_distribution([row["candidate_count"] for row in selected]),
        "candidate_pool_repositories_smoke": dict(sorted(Counter(row["repository"] for row in selected).items())),
        "plausible_distractor_counts_smoke": _size_distribution([row["plausible_distractor_count"] for row in selected]),
        "source_target_pair_strata": dict(sorted(by_stratum.items())),
        "target_strata_all": dict(sorted(Counter(row["target_primary_stratum"] for row in screens).items())),
        "target_strata_clean_target_count": len(clean_targets),
        "temporal_distance_days_all_candidate_pools": _numeric_distribution(distances),
        "target_primary_environment_validation": "NOT_RUN; metadata completeness only",
        "temporal_distance_days_smoke_candidate_pools": _numeric_distribution(smoke_distances),
        "governance_stress_cases": 0,
        "structural_gate": {
            "clean_targets_with_nontrivial_pools": sum(
                row["candidate_count"] >= 5 and row["plausible_distractor_count"] >= 2
                for row in clean_targets
            ),
            "clean_targets_total": len(clean_targets),
            "gate_passed": sum(
                row["candidate_count"] >= 5 and row["plausible_distractor_count"] >= 2
                for row in clean_targets
            ) >= 10,
            "criterion": "at least 10 clean targets each with >=5 total candidates and >=2 non-linked candidates with issue/path/symbol overlap",
        },
        "candidate_counts_artifact": counts,
    }


def _candidate_counts(screens: list[dict[str, Any]], selected_ids: set[str]) -> dict[str, Any]:
    all_counts = [row["candidate_count"] for row in screens]
    smoke_counts = [row["candidate_count"] for row in screens if row["target_id"] in selected_ids]
    return {
        "all_99_targets": _size_distribution(all_counts),
        "smoke_targets": _size_distribution(smoke_counts),
    }


def _source_memory_candidates(
    experiences: dict[str, Task], source_trajectory_jsonl: str | Path | None,
):
    if source_trajectory_jsonl is None:
        return {
            source_id: memory_from_provided_experience(task)
            for source_id, task in experiences.items()
        }
    records: dict[str, dict[str, Any]] = {}
    with Path(source_trajectory_jsonl).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            source_id = record.get("source_task_id")
            if source_id not in experiences:
                raise ValueError(f"trajectory line {line_number} has unknown source_task_id: {source_id}")
            if source_id in records:
                raise ValueError(f"duplicate trajectory record for source_task_id: {source_id}")
            records[source_id] = record
    missing = sorted(set(experiences) - set(records))
    if missing:
        raise ValueError(
            "fresh trajectory mode requires one source-only record for every experience task; "
            f"missing {len(missing)} (first IDs: {missing[:5]})"
        )
    return {
        source_id: memory_from_trajectory(task, records[source_id])
        for source_id, task in experiences.items()
    }


def _structural_casebook(
    selected_ids: list[str], pools: dict[str, dict[str, Any]],
    relations: dict[tuple[str, str], Relation], linked_clean: dict[str, list[str]],
) -> list[dict[str, Any]]:
    rows = []
    for target_id in selected_ids:
        pool = pools[target_id]
        related = {source_id for (mapped_target, source_id) in relations if mapped_target == target_id}
        candidates = [
            entry for entry in pool["candidate_pool"]
            if entry["memory"]["source_task_id"] not in related
            and any(reason in entry["entry_reasons"] for reason in (
                "ISSUE_TEXT_OVERLAP", "ISSUE_SYMBOL_MATCH", "ISSUE_PATH_MATCH",
            ))
        ]
        candidates.sort(key=lambda entry: (
            -len(entry["public_similarity"]["shared_paths_in_issue_text"]),
            -len(entry["public_similarity"]["shared_symbols_in_issue_text"]),
            -len(entry["public_similarity"]["shared_issue_terms"]),
            entry["memory"]["source_task_id"],
        ))
        rows.append({
            "target_id": target_id, "candidate_pool_size": pool["candidate_count"],
            "clean_prior_related_source_ids": sorted(linked_clean[target_id]),
            "nonlinked_overlap_candidate_count": len(candidates),
            "plausibility_method": "issue-text terms, technical identifiers, or explicit paths; automatic lexical proxy only",
            "illustrative_nonlinked_candidates": [
                {
                    "source_id": entry["memory"]["source_task_id"],
                    "entry_reasons": entry["entry_reasons"],
                    "public_similarity": entry["public_similarity"],
                }
                for entry in candidates[:5]
            ],
        })
    return rows


def _size_distribution(values: list[int]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "n": len(ordered), "singleton": sum(value == 1 for value in ordered),
        "zero": sum(value == 0 for value in ordered),
        "ge_2": sum(value >= 2 for value in ordered), "ge_5": sum(value >= 5 for value in ordered),
        "ge_10": sum(value >= 10 for value in ordered),
        "median": ordered[len(ordered) // 2] if ordered else None,
        "mean": round(sum(ordered) / len(ordered), 3) if ordered else None,
        "min": ordered[0] if ordered else None, "max": ordered[-1] if ordered else None,
    }


def _numeric_distribution(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0}
    p95_index = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
    return {
        "n": len(ordered), "min": round(ordered[0], 3),
        "median": round(ordered[len(ordered) // 2], 3),
        "p95": round(ordered[p95_index], 3), "max": round(ordered[-1], 3),
        "mean": round(sum(ordered) / len(ordered), 3),
    }


def _target_stratum(audits: list[dict[str, Any]]) -> str:
    linked = [row for row in audits if row["known_related"]]
    if not linked:
        return "AMBIGUOUS_CHRONOLOGY"
    priorities = (
        "CLEAN_TEMPORAL", "EXPLICIT_PRIOR_REFERENCE", "HIGH_HINT_LEAKAGE",
        "SAME_PR_OR_CORESOLUTION", "AMBIGUOUS_CHRONOLOGY", "ENVIRONMENT_INVALID",
    )
    strata = {row["primary_stratum"] for row in linked}
    return next((value for value in priorities if value in strata), "AMBIGUOUS_CHRONOLOGY")


def _environment_metadata_valid(target: Task) -> bool:
    return bool(
        target.base_commit and target.environment_setup_commit
        and target.fail_to_pass and "PASS_TO_PASS" in target.raw and "test_patch" in target.raw
    )


def _before(source: Task, target: Task) -> tuple[bool | None, str | None]:
    from .chronology import source_precedes_target

    return source_precedes_target(source, target)


def _generation_commit(output_dir: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNCOMMITTED"


def _sha_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]], append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")


def _write_counts_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "target_id", "repository", "target_created_at", "candidate_count",
        "published_related_source_count", "published_related_sources_in_pool",
        "clean_prior_related_source_count", "plausible_distractor_count",
        "target_primary_stratum", "environment_metadata_valid", "environment_valid",
        "environment_validation_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to emit benchmark_manifest.parquet") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    parquet.write_table(pa.Table.from_pylist(rows), path)
