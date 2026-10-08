#!/usr/bin/env python3
"""Freeze the amended analysis plan against the existing 11-target smoke release."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_mem_contextbench.treatments import unique_source_memories


EXPECTED_TARGETS = {
    "sympy__sympy-19235", "sympy__sympy-21203", "django__django-35356",
    "sympy__sympy-16342", "sympy__sympy-16946", "matplotlib__matplotlib-22482",
    "sympy__sympy-21309", "django__django-34176", "sympy__sympy-16953",
    "scikit-learn__scikit-learn-13771", "sympy__sympy-9384",
}
QUALIFICATION_TARGETS = [
    "sympy__sympy-21309", "django__django-34176", "sympy__sympy-16953",
]
PRETREATMENT_EXCLUSION = {
    "target_id": "matplotlib__matplotlib-22482",
    "reason": "SEMANTIC_NOOP_RESOLVED_PRETREATMENT",
    "control_artifact": "artifacts/burned-pilot/control_gate.json",
}
PROTOCOL_SEED = 20261005


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="artifacts/smoke")
    parser.add_argument("--output", default="artifacts/burned-pilot/plan.json")
    args = parser.parse_args()
    release = _rooted(Path(args.release))
    manifest_path = release / "manifests/benchmark_manifest.jsonl"
    manifest_rows = [
        json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    target_ids = [row["target_id"] for row in manifest_rows]
    if len(target_ids) != 11 or set(target_ids) != EXPECTED_TARGETS:
        raise SystemExit("frozen release is not the predeclared 11-target pilot; refusing reselection")

    pools: dict[str, dict] = {}
    pool_hashes: dict[str, dict] = {}
    for target_id in target_ids:
        pool_path = release / "pools" / f"{target_id}.json"
        pool = _json(pool_path)
        if pool["target"]["target_id"] != target_id:
            raise SystemExit(f"pool target mismatch for {target_id}")
        pools[target_id] = pool
        pool_hashes[target_id] = {
            "path": str(pool_path),
            "file_sha256": _sha256_bytes(pool_path.read_bytes()),
            "pool_hash": pool["pool_hash"],
            "candidate_count": pool["candidate_count"],
        }

    memories = unique_source_memories(pools)
    if len(memories) != 211:
        raise SystemExit(f"frozen candidate union changed: expected 211 unique memories, found {len(memories)}")
    protocol_path = ROOT / "docs/EXPERIMENT_PROTOCOL.md"
    amendment_path = ROOT / "docs/PILOT_PRETREATMENT_AMENDMENT.md"
    worker_amendment_path = ROOT / "docs/PILOT_WORKER_INTERFACE_AMENDMENT.md"
    try:
        repo_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("The pilot freeze requires an inspectable Git checkout.") from exc
    if dirty:
        raise SystemExit("Commit the protocol and runner changes before freezing the pilot plan.")
    source_provenance = _json(release / "manifests/source_provenance.json")
    model_assets = _json(ROOT / "configs/model_assets.lock.json")
    analysis_target_ids = [target_id for target_id in target_ids if target_id != PRETREATMENT_EXCLUSION["target_id"]]
    if len(analysis_target_ids) != 10 or not set(QUALIFICATION_TARGETS).issubset(analysis_target_ids):
        raise SystemExit("amended primary target or qualification subset is invalid")
    prior_control_evidence = _prior_control_evidence(analysis_target_ids)
    arm_order = {
        target_id: sorted(
            ["A_NO_MEMORY", "B_SHARE_ALL", "C_RANDOM_MATCHED", "D_JEV_WRITE",
             "E_JEV_WRITE_READ", "F_ORACLE_RELATED_CEILING", "G_LLM_WRITE"],
            key=lambda arm: (_sha256_text(f"fleet-mem-contextbench-burned-v2:order:{PROTOCOL_SEED}:{target_id}:{arm}"), arm),
        )
        for target_id in target_ids
    }
    plan = {
        "plan_version": "burned-pilot-v2",
        "protocol_status": "FROZEN_BEFORE_TREATMENTS",
        "benchmark_generation_commit": source_provenance.get("benchmark_generation_commit"),
        "contextbench_commit": source_provenance.get("contextbench_git_commit"),
        "hf_revision": source_provenance.get("huggingface_revision"),
        "source_dataset_sha256": source_provenance.get("input_sha256"),
        "hidden_relation_annotations_sha256": _sha256_bytes(
            (release / "hidden/relationship_annotations.jsonl").read_bytes()
        ),
        "benchmark_manifest_sha256": _sha256_bytes(manifest_path.read_bytes()),
        "protocol_sha256": _sha256_bytes(protocol_path.read_bytes()),
        "analysis_amendment_path": amendment_path.relative_to(ROOT).as_posix(),
        "analysis_amendment_sha256": _sha256_bytes(amendment_path.read_bytes()),
        "worker_interface_amendment_path": worker_amendment_path.relative_to(ROOT).as_posix(),
        "worker_interface_amendment_sha256": _sha256_bytes(worker_amendment_path.read_bytes()),
        "repo_commit_at_freeze": repo_commit,
        "experiment_file_sha256": _experiment_file_hashes(),
        "model_assets_lock_sha256": _sha256_bytes((ROOT / "configs/model_assets.lock.json").read_bytes()),
        "target_ids": target_ids,
        "analysis_target_ids": analysis_target_ids,
        "analysis_exclusions": [PRETREATMENT_EXCLUSION],
        **({"prior_control_evidence": prior_control_evidence} if prior_control_evidence else {}),
        "target_pool_freeze": pool_hashes,
        "unique_source_memory_count": len(memories),
        "unique_source_memory_ids": sorted(memories),
        "unique_source_memory_union_sha256": _sha256_text(json.dumps(
            memories, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )),
        "source_candidate_extraction": {
            "extractor_version": "provided-experience-metadata-v1",
            "source_mode": "PROVIDED_EXPERIENCE_SMOKE",
            "high_recall_rule": "include every source card already present in the frozen target history union",
            "target_information_used": False,
            "future_reusability_filter": False,
            "source_agent_outcomes_claimed": False,
        },
        "source_governance": {
            "decision_actions": ["SHARE", "DO_NOT_SHARE"],
            "calls_per_unique_candidate": 1,
            "target_input_allowed": False,
            "freeze_before_target_runs": True,
            "random_seed": 42,
            "random_admission_algorithm": "ascending SHA256(fleet-mem-contextbench-burned-v2:random:42:<memory_id>), first K, K equals Jev SHARE count",
            "degenerate_share_rate_stop": [0.0, 1.0],
        },
        "target_governance": {
            "decision_actions": ["EXPOSE", "WITHHOLD"],
            "fixed_retrieval_order": "created_at descending, source_task_id ascending, memory_id ascending",
            "fixed_retrieval_count": 3,
            "memory_count_budget": 3,
            "memory_token_cap": None,
            "token_count_method": "Ollama worker prompt usage plus per-card character estimate",
            "arm_order_seed": PROTOCOL_SEED,
            "arm_order_by_target": arm_order,
        },
        "qualification": {
            "target_ids": QUALIFICATION_TARGETS,
            "pre_treatment_interface_retry": {
                "allowed_once": True,
                "trigger": "FORMAT_ERROR_THEN_TERMINAL_SENTINEL_BEFORE_REPOSITORY_INSPECTION",
                "same_target_ids": True,
                "same_model_and_budgets": True,
                "treatment_results_available": False,
            },
            "worker": {
                "scaffold": "mini-swe-agent",
                "scaffold_version": "2.4.6",
                "model": "qwen2.5-coder:32b",
                "model_manifest_sha256": model_assets["models"]["qwen2.5-coder:32b"]["manifest_sha256"],
                "model_runtime": "Ollama 0.34.4 local, cloud disabled",
                "temperature": 0.0,
                "seed": 42,
                "context_window_tokens": 16384,
                "max_agent_steps": 12,
                "max_generation_tokens_per_call": 1024,
                "wall_time_limit_seconds": 900,
                "worker_prompt_id": "contextbench-worker-command-interface-v3",
                "worker_config_sha256": _sha256_bytes((ROOT / "configs/worker.yaml").read_bytes()),
                "worker_adapter_sha256": _sha256_bytes((ROOT / "src/fleet_mem_contextbench/worker.py").read_bytes()),
                "per_run_clean_checkout": True,
            },
            "pass_rule": "all 3 runs submit a nonempty patch and at least 2/3 are canonically resolved; all target evaluator controls pass",
            "minimum_no_memory_resolved_for_interpretable_pilot": 3,
        },
        "treatments": [
            {"arm_id": "A_NO_MEMORY", "targets": "primary_10"},
            {"arm_id": "B_SHARE_ALL", "targets": "primary_10"},
            {"arm_id": "C_RANDOM_MATCHED", "targets": "primary_10"},
            {"arm_id": "D_JEV_WRITE", "targets": "primary_10"},
            {"arm_id": "E_JEV_WRITE_READ", "targets": "primary_10"},
            {"arm_id": "F_ORACLE_RELATED_CEILING", "targets": "primary_10", "uses_hidden_relations": True},
            {"arm_id": "G_LLM_WRITE", "targets": "primary_10", "source_candidate_count": len(memories),
             "governor_model": "qwen2.5:32b", "runtime": "Ollama 0.34.4 local; cloud disabled",
             "governor_model_manifest_sha256": model_assets["models"]["qwen2.5:32b"]["manifest_sha256"],
             "full_pilot_feasible": True,
             "feasibility_basis": "211 short source cards and a local Qwen2.5 32B model asset are available before outcomes"},
        ],
        "stop_rules": {
            "share_all_or_share_none": True,
            "minimum_shareall_vs_jev_exposure_discordance_targets": 6,
            "minimum_jev_read_eligible_targets": 6,
            "minimum_no_memory_resolved_targets": 3,
            "failed_evaluator_controls": "stop if any primary target fails, retain all frozen targets, do not replace; Matplotlib is the sole pre-treatment amendment exclusion",
            "pretreatment_exclusion": PRETREATMENT_EXCLUSION,
            "benchmark_changes_after_outcomes": False,
            "main_study_authorized": False,
        },
    }
    output = _rooted(Path(args.output))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "plan": str(output), "target_count": len(target_ids),
        "unique_source_memory_count": len(memories),
        "benchmark_manifest_sha256": plan["benchmark_manifest_sha256"],
        "protocol_sha256": plan["protocol_sha256"],
        "analysis_target_count": len(analysis_target_ids),
        "llm_targets": "primary_10",
    }, indent=2))


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _experiment_file_hashes() -> dict[str, str]:
    paths = [
        *(ROOT / "src/fleet_mem_contextbench").rglob("*.py"),
        *(ROOT / "scripts").glob("*"),
        *(ROOT / "configs").glob("*"),
        ROOT / "pyproject.toml",
        ROOT / "docs/EXPERIMENT_PROTOCOL.md",
        ROOT / "docs/PILOT_PRETREATMENT_AMENDMENT.md",
        ROOT / "docs/PILOT_WORKER_INTERFACE_AMENDMENT.md",
    ]
    return {
        path.relative_to(ROOT).as_posix(): _sha256_bytes(path.read_bytes())
        for path in sorted(set(paths), key=lambda item: item.relative_to(ROOT).as_posix())
        if path.is_file()
    }


def _prior_control_evidence(primary_target_ids: list[str]) -> dict[str, str] | None:
    path = ROOT / "artifacts/burned-pilot/controls_summary.json"
    if not path.is_file():
        return None
    summary = _json(path)
    if (
        summary.get("status") != "PASS"
        or summary.get("all_controls_passed") is not True
        or summary.get("target_ids") != primary_target_ids
        or summary.get("target_count") != len(primary_target_ids)
        or summary.get("control_count") != 2 * len(primary_target_ids)
    ):
        raise SystemExit("existing primary control evidence is incomplete; refusing to supersede it")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "artifact_sha256": _sha256_bytes(path.read_bytes()),
        "source_plan_sha256": summary["plan_sha256"],
    }


if __name__ == "__main__":
    main()
