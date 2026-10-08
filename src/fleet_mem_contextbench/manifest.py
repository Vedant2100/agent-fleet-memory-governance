"""Frozen treatment arms and target-run manifest helpers."""

from __future__ import annotations


ARMS = [
    {"arm_id": "A_NO_MEMORY", "write_policy": "NONE", "read_policy": "NONE"},
    {"arm_id": "B_SHARE_ALL", "write_policy": "SHARE_ALL", "read_policy": "FIXED_DETERMINISTIC"},
    {"arm_id": "C_RANDOM_MATCHED", "write_policy": "SIZE_MATCHED_RANDOM", "read_policy": "FIXED_DETERMINISTIC"},
    {"arm_id": "D_JEV_WRITE", "write_policy": "JEV_BINARY", "read_policy": "FIXED_DETERMINISTIC"},
    {"arm_id": "E_JEV_WRITE_READ", "write_policy": "JEV_BINARY", "read_policy": "JEV_BINARY"},
    {"arm_id": "F_ORACLE_RELATED_CEILING", "write_policy": "ORACLE", "read_policy": "ORACLE_KNOWN_RELATED"},
    {"arm_id": "G_LLM_WRITE", "write_policy": "LLM_BINARY", "read_policy": "FIXED_DETERMINISTIC", "conditional": True},
]

RUN_METRIC_FIELDS = (
    "resolved", "pass_at_1", "fail_to_pass_passed", "fail_to_pass_total",
    "pass_to_pass_passed", "pass_to_pass_total", "positive_transfer", "negative_transfer",
    "preserved_success", "persistent_failure", "tokens", "steps", "tool_calls",
    "agent_latency_seconds", "memory_tokens_exposed", "worker_context_tokens",
    "write_admission_rate", "read_abstention_rate", "governor_latency_ms",
    "governor_cost", "candidate_pool_size", "treatment_order", "retrieved_memory_ids",
    "exposed_memory_ids", "shared_memory_ids",
)


def validate_arms(arms: list[dict]) -> list[str]:
    errors: list[str] = []
    found = {row.get("arm_id") for row in arms}
    expected = {row["arm_id"] for row in ARMS if not row.get("conditional")}
    allowed = expected | {row["arm_id"] for row in ARMS if row.get("conditional")}
    if not expected <= found or found - allowed:
        errors.append(f"arm IDs must include {sorted(expected)} and may include {sorted(allowed - expected)}; found {sorted(found)}")
    for arm in arms:
        if arm.get("write_policy") not in {"NONE", "SHARE_ALL", "SIZE_MATCHED_RANDOM", "JEV_BINARY", "LLM_BINARY", "ORACLE"}:
            errors.append(f"{arm.get('arm_id')}: invalid write_policy")
        if arm.get("read_policy") not in {"NONE", "FIXED_DETERMINISTIC", "JEV_BINARY", "ORACLE_KNOWN_RELATED"}:
            errors.append(f"{arm.get('arm_id')}: invalid read_policy")
    return errors
