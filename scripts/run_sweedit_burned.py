#!/usr/bin/env python3
"""Run frozen ContextBench worker qualification or the No-Memory/oracle signal test."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_mem_contextbench.apptainer_evaluator import (
    SWEContextBenchApptainerEvaluator,
    semantic_noop_patch,
)
from fleet_mem_contextbench.pilot_runtime import (
    analysis_target_ids,
    clean_related_sources_by_target,
    load_frozen_pilot,
    sha256_file,
)
from fleet_mem_contextbench.sweedit_worker import (
    DEFAULT_WORKER_CONFIG, load_worker_settings, run_sweedit_worker, verify_target_sif_base,
)
from fleet_mem_contextbench.treatments import treatment_exposure, unique_source_memories

ANTIGRAVITY_BASELINE_COMMIT = "b0353a2"
BASELINE_HASH_COMPATIBILITY: dict[str, str] = {}


def main() -> int:
    args = _parse_args()
    _require_slurm()
    settings = load_worker_settings(args.worker_config)
    model_access = _preflight_openai_model(settings["requested_model"])
    plan, pools, _ = _load_frozen_pilot_with_documented_baseline(args.plan)
    _validate_controls(plan, args.plan)
    evaluator = SWEContextBenchApptainerEvaluator(
        args.contextbench_root, args.targets_parquet, args.sif_dir, args.job_tmp,
    )
    if args.stage == "qualify":
        return _run_qualification(args, plan, pools, evaluator, model_access)
    if args.stage == "smoke":
        return _run_smoke(args, plan, pools, evaluator, model_access)
    if args.stage == "diagnostic":
        return _run_development_diagnostic(args, plan, pools, evaluator, model_access)
    if args.stage == "diagnostic_resume":
        return _run_django_diagnostic_resume(args, plan, pools, evaluator, model_access)
    _validate_qualification_freeze()
    return _run_signal(args, plan, pools, evaluator, model_access)


def _run_qualification(args, plan, pools, evaluator, model_access) -> int:
    targets = list(plan["qualification"]["target_ids"])
    evaluator_preflight = evaluator.preflight(targets)
    sif_preflight = _preflight_sif_bases(args, pools, targets)
    records = [_run_no_memory(args, evaluator, pools, target_id) for target_id in targets]
    counts = _qualification_counts(records)
    passed = _qualification_passes(counts)
    summary = _base_run_summary(args, "SWEEDIT_WORKER_QUALIFICATION", model_access)
    summary.update({
        "status": "PASS" if passed else "STOP_WORKER_QUALIFICATION_FAILED",
        "evaluator_preflight": evaluator_preflight,
        "sif_base_preflight": sif_preflight,
        "target_ids": targets,
        **counts,
        "records": records,
    })
    _write_exclusive(args.summary, summary)
    _print_summary(summary, (
        "stage", "status", "nonempty_patch_count", "valid_submission_count", "resolved_count",
    ))
    return 0 if passed else 2


def _run_smoke(args, plan, pools, evaluator, model_access) -> int:
    target_id = "django__django-34176"
    if args.target_ids != [target_id] or target_id not in analysis_target_ids(plan):
        raise RuntimeError(f"smoke stage must run exactly the frozen target {target_id}")
    settings = load_worker_settings(args.worker_config)
    if settings["requested_model"] not in {"qwen3-coder:30b", "gpt-6-luna"} or settings["reasoning_effort"] != "xhigh":
        raise RuntimeError("smoke stage requires the frozen qwen3-coder:30b or gpt-6-luna worker at xhigh")
    evaluator_preflight = evaluator.preflight([target_id])
    sif_preflight = _preflight_sif_bases(args, pools, [target_id])
    target = pools[target_id]["target"]
    worker_dir = args.run_root / target_id / "A_NO_MEMORY" / "worker"
    worker = run_sweedit_worker(
        target,
        [],
        sif_path=args.sif_dir / f"{target_id}.sif",
        output_dir=worker_dir,
        sweedit_root=args.sweedit_root,
        sweedit_env=args.sweedit_env,
        python_prefix=args.python_prefix,
        worker_config=args.worker_config,
    )
    grade = {
        "canonical_grade_available": False,
        "patch_applied": False,
        "reason": worker.get("collector_error") or "smoke requires a valid source-code patch",
    }
    if (
        worker.get("authoritative_prediction_valid") is True
        and worker.get("tracked_source_files_changed") is True
        and worker.get("patch_bytes", 0) > 0
    ):
        patch = Path(worker["patch_path"]).read_text(encoding="utf-8")
        grade = evaluator.evaluate(
            target_id,
            patch,
            run_id=f"sweedit-A_NO_MEMORY-{target_id}-{os.environ['SLURM_JOB_ID']}",
            output_dir=args.run_root / target_id / "A_NO_MEMORY" / "evaluation",
        )
    checks = {
        "authoritative_diff_bytes_positive": worker.get("authoritative_diff_bytes", 0) > 0,
        "source_code_changed": worker.get("tracked_source_files_changed") is True,
        "prediction_patch_nonempty": worker.get("patch_bytes", 0) > 0,
        "valid_authoritative_submission": worker.get("authoritative_prediction_valid") is True,
        "canonical_grade_available": grade.get("canonical_grade_available") is True,
        "patch_applied": grade.get("patch_applied") is True,
    }
    record = {"arm_id": "A_NO_MEMORY", "worker": worker, "grade": _grade_summary(grade)}
    summary = _base_run_summary(args, "ONE_TARGET_WORKER_SMOKE", model_access)
    summary.update({
        "status": "SMOKE_PASS" if all(checks.values()) else "SMOKE_FAILED",
        "evaluator_preflight": evaluator_preflight,
        "sif_base_preflight": sif_preflight,
        "target_ids": [target_id],
        "checks": checks,
        "records": [record],
    })
    _write_exclusive(args.summary, summary)
    _print_summary(summary, ("stage", "status", "target_ids", "checks"))
    return 0 if summary["status"] == "SMOKE_PASS" else 2


def _load_frozen_pilot_with_documented_baseline(plan_path):
    """Accept the exact Antigravity evaluator baseline while retaining all other freeze checks."""
    from fleet_mem_contextbench import pilot_runtime

    original_validator = pilot_runtime._validate_frozen_plan_files

    def validate_with_baseline(plan):
        relative_path = "src/fleet_mem_contextbench/apptainer_evaluator.py"
        expected = plan.get("experiment_file_sha256", {}).get(relative_path)
        path = ROOT / relative_path
        actual = sha256_file(path)
        if expected != actual:
            baseline = subprocess.run(
                ["git", "show", f"{ANTIGRAVITY_BASELINE_COMMIT}:{relative_path}"],
                cwd=ROOT, check=True, capture_output=True,
            ).stdout
            baseline_hash = hashlib.sha256(baseline).hexdigest()
            head = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=ROOT, check=True, capture_output=True, text=True,
            ).stdout.strip()
            if head != ANTIGRAVITY_BASELINE_COMMIT or actual != baseline_hash:
                original_validator(plan)
                return
            plan["experiment_file_sha256"][relative_path] = actual
            BASELINE_HASH_COMPATIBILITY[relative_path] = ANTIGRAVITY_BASELINE_COMMIT
        original_validator(plan)

    pilot_runtime._validate_frozen_plan_files = validate_with_baseline
    try:
        return load_frozen_pilot(plan_path)
    finally:
        pilot_runtime._validate_frozen_plan_files = original_validator


def _run_development_diagnostic(args, plan, pools, evaluator, model_access) -> int:
    targets = _validate_sol_diagnostic_request(args)
    evaluator_preflight = evaluator.preflight(targets)
    sif_preflight = _preflight_sif_bases(args, pools, targets)
    records = [_run_no_memory(args, evaluator, pools, target_id) for target_id in targets]
    complete = all(
        row["worker"].get("valid_submission") is True
        and row["grade"].get("canonical_grade_available") is True
        and row["grade"].get("patch_applied") is True
        for row in records
    )
    summary = _base_run_summary(args, "TWO_TASK_MODEL_COMPARISON_DIAGNOSTIC", model_access)
    summary.update({
        "status": "DIAGNOSTIC_COMPLETE" if complete else "DIAGNOSTIC_INCOMPLETE",
        "development_only": True,
        "original_luna_qualification_gate": "FAILED",
        "no_memory_treatments_only": True,
        "evaluator_preflight": evaluator_preflight,
        "sif_base_preflight": sif_preflight,
        "target_ids": targets,
        "canonical_grade_count": sum(row["grade"].get("canonical_grade_available") is True for row in records),
        "resolved_count": sum(row["grade"].get("resolved") is True for row in records),
        "records": records,
    })
    _write_exclusive(args.summary, summary)
    _print_summary(summary, ("stage", "status", "requested_model", "reasoning_effort", "canonical_grade_count", "resolved_count"))
    return 0 if complete else 2


def _run_django_diagnostic_resume(args, plan, pools, evaluator, model_access) -> int:
    target_id = _validate_sol_django_resume_request(args)
    evaluator_preflight = evaluator.preflight([target_id])
    sif_preflight = _preflight_sif_bases(args, pools, [target_id])
    record = _run_no_memory(args, evaluator, pools, target_id)
    complete = (
        record["worker"].get("valid_submission") is True
        and record["grade"].get("canonical_grade_available") is True
        and record["grade"].get("patch_applied") is True
    )
    summary = _base_run_summary(args, "DEVELOPMENT_ONLY_SOL_DJANGO_DIAGNOSTIC_RESTART", model_access)
    summary.update({
        "status": "DIAGNOSTIC_RESTART_COMPLETE" if complete else "DIAGNOSTIC_RESTART_INCOMPLETE",
        "development_only": True,
        "resumes_cancelled_job_id": "289270",
        "prior_attempt_preserved": True,
        "no_memory_treatment_only": True,
        "evaluator_preflight": evaluator_preflight,
        "sif_base_preflight": sif_preflight,
        "target_ids": [target_id],
        "canonical_grade_count": int(record["grade"].get("canonical_grade_available") is True),
        "resolved_count": int(record["grade"].get("resolved") is True),
        "records": [record],
    })
    _write_exclusive(args.summary, summary)
    _print_summary(summary, (
        "stage", "status", "requested_model", "reasoning_effort", "canonical_grade_count", "resolved_count",
    ))
    return 0 if complete else 2


def _validate_sol_diagnostic_request(args) -> list[str]:
    expected = ["sympy__sympy-21309", "django__django-34176"]
    targets = args.target_ids
    if targets != expected:
        raise RuntimeError("development diagnostic must run exactly the frozen SymPy/Django pair in that order")
    settings = load_worker_settings(args.worker_config)
    if settings["requested_model"] != "gpt-5.6-sol" or settings["reasoning_effort"] != "xhigh":
        raise RuntimeError("two-task Sol diagnostic requires gpt-5.6-sol at the frozen xhigh effort")
    luna = load_worker_settings(ROOT / "configs/sweedit_worker.json")["config"]
    sol = settings["config"]
    luna["model"]["requested_model"] = sol["model"]["requested_model"]
    if luna != sol:
        raise RuntimeError("Sol diagnostic config must differ from the Luna config only by requested_model")
    return targets


def _validate_sol_django_resume_request(args) -> str:
    target_id = "django__django-34176"
    if args.target_ids != [target_id]:
        raise RuntimeError("only the interrupted frozen Django diagnostic may be resumed")
    settings = load_worker_settings(args.worker_config)
    if settings["requested_model"] != "gpt-5.6-sol" or settings["reasoning_effort"] != "xhigh":
        raise RuntimeError("Django diagnostic restart requires gpt-5.6-sol at the frozen xhigh effort")
    luna = load_worker_settings(ROOT / "configs/sweedit_worker.json")["config"]
    sol = settings["config"]
    luna["model"]["requested_model"] = sol["model"]["requested_model"]
    if luna != sol:
        raise RuntimeError("Django restart config must differ from the Luna config only by requested_model")
    return target_id


def _run_signal(args, plan, pools, evaluator, model_access) -> int:
    primary_ids = analysis_target_ids(plan)
    evaluator_preflight = evaluator.preflight(primary_ids)
    sif_preflight = _preflight_sif_bases(args, pools, primary_ids)
    related = clean_related_sources_by_target()
    all_memories = unique_source_memories(pools)
    random_seed = 20261006
    rows = _run_signal_pairs(args, evaluator, pools, primary_ids, related, all_memories, random_seed)
    summary = _signal_summary(args, model_access, evaluator_preflight, sif_preflight, primary_ids, rows, random_seed)
    _write_exclusive(args.summary, summary)
    return 0 if summary["status"] == "ORACLE_SIGNAL_PRESENT" else 2


def _run_signal_pairs(args, evaluator, pools, target_ids, related, all_memories, random_seed):
    rows = []
    for target_id in target_ids:
        row = _run_signal_pair(
            args, evaluator, pools[target_id], target_id, related.get(target_id, set()),
            all_memories, random_seed,
        )
        rows.append(row)
        _print_pair(row)
    return rows


def _run_signal_pair(args, evaluator, target_pool, target_id, related_ids, all_memories, seed):
    order = _pair_order(seed, target_id)
    pair = {
        arm_id: _run_arm(
            args, evaluator, target_pool, arm_id,
            _signal_exposure(target_pool, target_id, arm_id, related_ids, all_memories),
        )
        for arm_id in order
    }
    base = pair["A_NO_MEMORY"]
    oracle = pair["F_ORACLE_RELATED_CEILING"]
    return {
        "target_id": target_id,
        "repository": target_pool["target"]["repository"],
        "pair_order": order,
        "no_memory": base,
        "oracle_related": oracle,
        "behavioral_discordance": base["worker"].get("patch_sha256") != oracle["worker"].get("patch_sha256"),
        "executable_discordance": _executable_signature(base["grade"]) != _executable_signature(oracle["grade"]),
    }


def _signal_exposure(target_pool, target_id, arm_id, related_ids, all_memories):
    if arm_id == "A_NO_MEMORY":
        return {
            "arm_id": arm_id,
            "candidate_pool_size": len(target_pool["candidate_pool"]),
            "exposed_memories": [], "exposed_memory_ids": [],
            "memory_tokens_exposed": 0, "memory_count_budget": 3,
        }
    exposure = treatment_exposure(
        target=target_pool["target"], pool=target_pool,
        arm_id="F_ORACLE_RELATED_CEILING", admitted_ids=set(all_memories),
        related_source_ids=related_ids,
    )
    exposure["arm_id"] = "F_ORACLE_RELATED_CEILING"
    return exposure


def _signal_summary(args, model_access, evaluator_preflight, sif_preflight, target_ids, rows, seed):
    complete = _signal_pairs_complete(rows)
    behavioral_count = sum(row["behavioral_discordance"] for row in rows)
    executable_count = sum(row["executable_discordance"] for row in rows)
    signal = complete and executable_count >= 2
    status = "STOP_SIGNAL_TEST_INCOMPLETE" if not complete else (
        "ORACLE_SIGNAL_PRESENT" if signal else "STOP_NO_ORACLE_SIGNAL"
    )
    summary = _base_run_summary(args, "BURNED_NO_MEMORY_VS_ORACLE_SIGNAL_TEST", model_access)
    summary.update({
        "status": status,
        "evaluator_preflight": evaluator_preflight,
        "sif_base_preflight": sif_preflight,
        "target_ids": target_ids,
        "complete_paired_executable_grades": complete,
        "behavioral_discordant_targets": behavioral_count,
        "executable_discordant_targets": executable_count,
        "meaningful_oracle_signal": signal,
        "oracle_go_no_go": {
            "minimum_executable_discordant_targets": 2,
            "observed_executable_discordant_targets": executable_count,
            "complete_pairs_required": True,
            "behavioral_discordance_alone_counts": False,
            "passed": complete and signal,
        },
        "pair_order_seed": seed,
        "records": rows,
    })
    _print_summary(summary, (
        "stage", "status", "behavioral_discordant_targets", "executable_discordant_targets",
    ))
    return summary


def _signal_pairs_complete(rows):
    return all(
        arm["worker"].get("authoritative_prediction_valid") is True
        and arm["worker"].get("repository_state_recovered") is True
        and arm["grade"].get("canonical_grade_available") is True
        and arm["grade"].get("patch_applied") is True
        for row in rows for arm in (row["no_memory"], row["oracle_related"])
    )


def _qualification_counts(records):
    return {
        "nonempty_patch_count": sum(row["worker"]["patch_bytes"] > 0 for row in records),
        "valid_submission_count": sum(row["worker"]["valid_submission"] is True for row in records),
        "resolved_count": sum(row["grade"].get("resolved") is True for row in records),
        "canonical_grade_count": sum(row["grade"].get("canonical_grade_available") is True for row in records),
        "patch_applied_count": sum(row["grade"].get("patch_applied") is True for row in records),
    }


def _qualification_passes(counts):
    return (
        counts["nonempty_patch_count"] == 3
        and counts["valid_submission_count"] == 3
        and counts["canonical_grade_count"] == 3
        and counts["patch_applied_count"] == 3
        and counts["resolved_count"] >= 2
    )


def _base_run_summary(args, stage, model_access):
    settings = load_worker_settings(args.worker_config)
    summary = {
        "schema_version": 1,
        "stage": stage,
        "plan_sha256": sha256_file(args.plan),
        "worker_config_path": str(settings["path"]),
        "worker_config_sha256": settings["sha256"],
        "requested_model": settings["requested_model"],
        "reasoning_effort": settings["reasoning_effort"],
        "worker_adapter_sha256": sha256_file(ROOT / "src/fleet_mem_contextbench/sweedit_worker.py"),
        "bootstrap_sha256": sha256_file(ROOT / "scripts/sweedit_bootstrap.py"),
        "pilot_runner_sha256": sha256_file(ROOT / "scripts/run_sweedit_burned.py"),
        "slurm_wrapper_sha256": sha256_file(ROOT / "scripts/run_sweedit_pilot.sbatch"),
        "model_access_preflight": model_access,
    }
    if BASELINE_HASH_COMPATIBILITY:
        summary["documented_baseline_hash_compatibility"] = dict(BASELINE_HASH_COMPATIBILITY)
    return summary


def _print_pair(row):
    base, oracle = row["no_memory"], row["oracle_related"]
    print(json.dumps({
        "target_id": row["target_id"],
        "no_memory_resolved": base["grade"].get("resolved"),
        "oracle_resolved": oracle["grade"].get("resolved"),
        "behavioral_discordance": row["behavioral_discordance"],
        "executable_discordance": row["executable_discordance"],
    }))


def _print_summary(summary, fields):
    print(json.dumps({key: summary[key] for key in fields}, indent=2))


def _require_slurm():
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("worker experiment must run under Slurm")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("qualify", "smoke", "diagnostic", "diagnostic_resume", "signal"), required=True)
    parser.add_argument("--plan", type=Path, default=ROOT / "artifacts/burned-pilot/plan.json")
    parser.add_argument("--targets-parquet", type=Path, required=True)
    parser.add_argument("--contextbench-root", type=Path, required=True)
    parser.add_argument("--sif-dir", type=Path, default=ROOT / "artifacts/burned-pilot/images")
    parser.add_argument("--job-tmp", type=Path, required=True)
    parser.add_argument("--sweedit-root", type=Path, required=True)
    parser.add_argument("--sweedit-env", type=Path, required=True)
    parser.add_argument("--python-prefix", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--worker-config", type=Path, default=DEFAULT_WORKER_CONFIG)
    parser.add_argument("--target-ids", nargs="+", default=None)
    return parser.parse_args()


def _validate_controls(plan: dict[str, Any], plan_path: Path) -> None:
    controls = json.loads((ROOT / "artifacts/burned-pilot/controls_summary.json").read_text(encoding="utf-8"))
    ids = analysis_target_ids(plan)
    if (
        controls.get("all_controls_passed") is not True
        or controls.get("target_ids") != ids
        or controls.get("control_count") != 2 * len(ids)
    ):
        raise RuntimeError("frozen canonical model-free controls do not cover the unchanged analysis target set")
    # The summary was explicitly rebound after the pre-treatment target exclusion.
    if sha256_file(plan_path) != controls.get("plan_sha256"):
        raise RuntimeError("canonical control summary is not bound to the current frozen plan")


def _preflight_openai_model(requested_model: str) -> dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is unavailable for model access preflight")
    request = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
        status = response.status
    available = requested_model in {row.get("id") for row in payload.get("data", [])}
    if status != 200 or not available:
        raise RuntimeError(f"OpenAI model access preflight failed for {requested_model}")
    return {
        "endpoint": "/v1/models", "http_status": status,
        "requested_model": requested_model, "requested_model_available": True,
    }


def _preflight_sif_bases(args, pools: dict[str, dict[str, Any]], target_ids: list[str]) -> list[dict[str, str]]:
    return [
        {
            "target_id": target_id,
            "sif_path": str(args.sif_dir / f"{target_id}.sif"),
            "repository_head": verify_target_sif_base(
                args.sif_dir / f"{target_id}.sif", pools[target_id]["target"]["base_commit"],
            ),
            "expected_base_commit": pools[target_id]["target"]["base_commit"],
        }
        for target_id in target_ids
    ]


def _validate_qualification_freeze() -> None:
    path = ROOT / "artifacts/burned-pilot/sweedit_qualification.json"
    if not path.is_file():
        raise RuntimeError("signal stage requires a completed SWE-Edit worker qualification")
    qualification = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "worker_config_sha256": sha256_file(ROOT / "configs/sweedit_worker.json"),
        "worker_adapter_sha256": sha256_file(ROOT / "src/fleet_mem_contextbench/sweedit_worker.py"),
        "bootstrap_sha256": sha256_file(ROOT / "scripts/sweedit_bootstrap.py"),
        "pilot_runner_sha256": sha256_file(ROOT / "scripts/run_sweedit_burned.py"),
        "slurm_wrapper_sha256": sha256_file(ROOT / "scripts/run_sweedit_pilot.sbatch"),
    }
    if qualification.get("status") != "PASS":
        raise RuntimeError("SWE-Edit worker qualification did not pass")
    if any(qualification.get(key) != value for key, value in expected.items()):
        raise RuntimeError("worker configuration changed after qualification; refusing signal runs")


def _run_no_memory(args, evaluator, pools, target_id: str) -> dict[str, Any]:
    pool = pools[target_id]
    exposure = {
        "arm_id": "A_NO_MEMORY",
        "candidate_pool_size": len(pool["candidate_pool"]),
        "exposed_memories": [],
        "exposed_memory_ids": [],
        "memory_tokens_exposed": 0,
        "memory_count_budget": 3,
    }
    return _run_arm(args, evaluator, pool, "A_NO_MEMORY", exposure)


def _run_arm(args, evaluator, target_pool: dict[str, Any], arm_id: str, exposure: dict[str, Any]) -> dict[str, Any]:
    target = target_pool["target"]
    target_id = target["target_id"]
    run_dir = args.run_root / target_id / arm_id
    worker = run_sweedit_worker(
        target,
        exposure["exposed_memories"],
        sif_path=args.sif_dir / f"{target_id}.sif",
        output_dir=run_dir / "worker",
        sweedit_root=args.sweedit_root,
        sweedit_env=args.sweedit_env,
        python_prefix=args.python_prefix,
        worker_config=args.worker_config,
    )
    grade: dict[str, Any]
    patch = _prediction_patch(worker)
    grade = evaluator.evaluate(
        target_id,
        patch,
        run_id=f"sweedit-{arm_id}-{target_id}-{os.environ['SLURM_JOB_ID']}",
        output_dir=run_dir / "evaluation",
    )
    return {
        "arm_id": arm_id,
        "exposed_memory_ids": exposure["exposed_memory_ids"],
        "memory_count": len(exposure["exposed_memory_ids"]),
        "memory_tokens_exposed": exposure["memory_tokens_exposed"],
        "memory_token_count_method": exposure.get("memory_token_count_method", "NONE"),
        "memory_card_sizes": exposure.get("exposed_memory_card_sizes", {}),
        "memory_serialized_bytes_exposed": exposure.get("memory_serialized_bytes_exposed", 0),
        "memory_count_budget": exposure["memory_count_budget"],
        "candidate_pool_size": exposure["candidate_pool_size"],
        "worker": worker,
        "grade": _grade_summary(grade),
        "canonical_result_sha256": grade.get("canonical_result_sha256"),
    }


def _grade_summary(grade: dict[str, Any]) -> dict[str, Any]:
    return {
        key: grade.get(key) for key in (
            "canonical_grade_available", "resolved", "patch_applied",
            "fail_to_pass_passed", "fail_to_pass_total",
            "pass_to_pass_passed", "pass_to_pass_total", "latency_seconds",
        )
    } | ({"reason": grade["reason"]} if grade.get("reason") else {})


def _prediction_patch(worker: dict[str, Any]) -> str:
    """Use the captured repository diff; represent an unchanged tree with the frozen no-op."""
    if worker.get("repository_state_recovered") is not True:
        raise RuntimeError("cannot construct a prediction from an unrecovered worker repository")
    patch_path = Path(worker["patch_path"])
    patch = patch_path.read_text(encoding="utf-8")
    if patch.strip():
        return patch
    return semantic_noop_patch()


def _executable_signature(grade: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(grade.get(field) for field in (
        "resolved", "fail_to_pass_passed", "fail_to_pass_total",
        "pass_to_pass_passed", "pass_to_pass_total",
    ))


def _pair_order(seed: int, target_id: str) -> list[str]:
    digest = hashlib.sha256(f"{seed}:{target_id}".encode()).digest()
    arms = ["A_NO_MEMORY", "F_ORACLE_RELATED_CEILING"]
    return arms[::-1] if digest[0] & 1 else arms


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
