"""Offline target/source leakage audit. Never imported by governor adapters."""

from __future__ import annotations

import re
from typing import Any

from .chronology import source_precedes_target, temporal_distance_days
from .data import Task
from .memory_schema import patch_paths
from .relations import Relation


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_URL_NUMBER = re.compile(r"/(?:issues|pull|ticket)/(\d+)(?:\b|/|$)", re.I)


def audit_pair(
    source: Task,
    target: Task,
    relation: Relation | None,
    source_count_for_target: int,
    included: bool,
    exclusion_reason: str | None,
    environment_metadata_valid: bool,
) -> dict[str, Any]:
    before, chronology_reason = source_precedes_target(source, target)
    source_files = patch_paths(source.patch)
    target_files = patch_paths(target.patch)
    file_overlap = sorted(source_files & target_files)
    source_symbols = _patch_identifiers(source.patch)
    target_symbols = _patch_identifiers(target.patch)
    symbol_overlap = sorted(source_symbols & target_symbols)
    patch_overlap = _patch_line_jaccard(source.patch, target.patch)
    target_text = f"{target.problem_statement}\n{target.hints_text}"
    source_issue_number = _issue_number(source.task_id)
    referenced_numbers = set(_URL_NUMBER.findall(target_text))
    explicit_url_reference = False
    if relation:
        for url in relation.source_issue_urls + relation.source_pr_urls:
            if url:
                explicit_url_reference = explicit_url_reference or url.lower() in target_text.lower()
                match = _URL_NUMBER.search(url)
                if match:
                    referenced_numbers.add(match.group(1))
    mentions = explicit_url_reference or any(
        _explicit_number_reference(target_text, number)
        for number in referenced_numbers | ({source_issue_number} if source_issue_number else set())
    )
    exact_hint = _contains_source_solution_text(target_text, source.patch)
    solution_hint = exact_hint
    same_pr = relation.same_pr if relation else None
    metadata_valid = environment_metadata_valid
    if not metadata_valid:
        stratum = "ENVIRONMENT_INVALID"
    elif same_pr is True:
        stratum = "SAME_PR_OR_CORESOLUTION"
    elif before is not True:
        stratum = "AMBIGUOUS_CHRONOLOGY"
    elif solution_hint or patch_overlap >= 0.20:
        stratum = "HIGH_HINT_LEAKAGE"
    elif mentions:
        stratum = "EXPLICIT_PRIOR_REFERENCE"
    else:
        stratum = "CLEAN_TEMPORAL"
    if same_pr is True or solution_hint or patch_overlap >= 0.20:
        risk = "HIGH"
    elif mentions or file_overlap or symbol_overlap:
        risk = "MEDIUM"
    elif before is True:
        risk = "LOW"
    else:
        risk = "UNKNOWN"
    return {
        "source_id": source.task_id,
        "target_id": target.task_id,
        "repository": target.repo,
        "source_created_at": source.created_at,
        "target_created_at": target.created_at,
        "source_before_target": before,
        "chronology_exclusion_reason": chronology_reason,
        "same_pr": same_pr,
        "same_commit": None,
        "same_base_commit": bool(source.base_commit and target.base_commit and source.base_commit == target.base_commit),
        "source_in_target_git_ancestry": None,
        "target_mentions_source_issue_or_pr": mentions,
        "target_describes_source_failure": None,
        "target_contains_solution_hint": solution_hint,
        "solution_hint_method": "exact_added_line_string_from_source_patch",
        "file_overlap": file_overlap,
        "symbol_overlap": symbol_overlap,
        "patch_overlap": round(patch_overlap, 6),
        "relationship_type": relation.hidden_record()["relationship_type"] if relation else None,
        "known_related": relation is not None,
        "source_count_for_target": source_count_for_target,
        "environment_valid": None,
        "environment_validation_status": "NOT_RUN",
        "environment_metadata_valid": metadata_valid,
        "leakage_risk": risk,
        "primary_stratum": stratum,
        "in_candidate_pool": included,
        "exclusion_reason": exclusion_reason,
        "temporal_distance_days": temporal_distance_days(source, target),
    }


def _patch_identifiers(patch: str) -> set[str]:
    changed = [line[1:] for line in patch.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    return {name for line in changed for name in _IDENTIFIER.findall(line)}


def _patch_line_jaccard(left: str, right: str) -> float:
    left_lines = _changed_lines(left)
    right_lines = _changed_lines(right)
    if not left_lines or not right_lines:
        return 0.0
    union = left_lines | right_lines
    return len(left_lines & right_lines) / len(union) if union else 0.0


def _changed_lines(patch: str) -> set[str]:
    return {
        re.sub(r"\s+", " ", line[1:].strip())
        for line in patch.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")) and len(line.strip()) >= 12
    }


def _contains_source_solution_text(target_text: str, source_patch: str) -> bool:
    normalized = re.sub(r"\s+", " ", target_text).lower()
    return any(
        (line[1:].strip().lower() in normalized)
        for line in source_patch.splitlines()
        if line.startswith("+") and not line.startswith("+++") and len(line[1:].strip()) >= 24
    )


def _issue_number(task_id: str) -> str | None:
    match = re.search(r"-(\d+)$", task_id)
    return match.group(1) if match else None


def _explicit_number_reference(text: str, number: str) -> bool:
    return bool(re.search(rf"(?:#|issue\s+|pull request\s+|PR\s+)\s*{re.escape(number)}\b", text, re.I))
