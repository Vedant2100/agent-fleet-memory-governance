#!/usr/bin/env python3
"""Run the frozen seven-arm, ten-target primary executable burned pilot."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_mem_contextbench.apptainer_evaluator import SWEContextBenchApptainerEvaluator
from fleet_mem_contextbench.governors.base import Decision
from fleet_mem_contextbench.pilot_runtime import (
    analysis_target_ids, clean_related_sources_by_target, load_decisions, load_frozen_pilot, read_jsonl,
    sha256_file,
)
from fleet_mem_contextbench.treatments import (
    freeze_size_matched_random, treatment_exposure,
)
from fleet_mem_contextbench.worker import WORKER_MODEL, preflight_ollama, solve_with_mini_swe_agent


ARM_IDS = [
    "A_NO_MEMORY", "B_SHARE_ALL", "C_RANDOM_MATCHED", "D_JEV_WRITE",
    "E_JEV_WRITE_READ", "F_ORACLE_RELATED_CEILING", "G_LLM_WRITE",
]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def ollama_preflight(base_url: str) -> dict[str, Any]:
    return preflight_ollama(base_url, WORKER_MODEL)


def decision_objects(path: Path) -> dict[tuple[str, str], Decision]:
    rows = read_jsonl(path)
    return {
        (row["target_id"], row["memory_id"]): Decision(
            action=row["action"], confidence=row.get("confidence"), probabilities=row.get("probabilities"),
            rationale=row.get("rationale", ""), latency_ms=row.get("latency_ms"), cost=row.get("cost"),
            input_tokens=row.get("input_tokens"), output_tokens=row.get("output_tokens"),
        )
        for row in rows
    }


def _grade(grade: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "canonical_grade_available", "resolved", "fail_to_pass_passed", "fail_to_pass_total",
        "pass_to_pass_passed", "pass_to_pass_total", "latency_seconds",
    )
    return {key: grade.get(key) for key in keys}


def _transfer(treatment: dict[str, Any], baseline: dict[str, Any]) -> dict[str, bool | None]:
    tgrade, bgrade = treatment.get("grade", {}), baseline.get("grade", {})
    if not tgrade.get("canonical_grade_available") or not bgrade.get("canonical_grade_available"):
        return {"positive_transfer": None, "negative_transfer": None, "preserved_success": None, "persistent_failure": None}
    tr, br = tgrade.get("resolved"), bgrade.get("resolved")
    tf, bf = tgrade.get("fail_to_pass_passed", 0), bgrade.get("fail_to_pass_passed", 0)
    tp, bp = tgrade.get("pass_to_pass_passed", 0), bgrade.get("pass_to_pass_passed", 0)
    return {
        "positive_transfer": _positive_transfer(tr, br, tf, bf, tp, bp),
        "negative_transfer": _negative_transfer(tr, br, tf, bf, tp, bp),
        "preserved_success": bool(br and tr and tf >= bf and tp >= bp),
        "persistent_failure": bool(not br and not tr),
    }


def _positive_transfer(tr: Any, br: Any, tf: int, bf: int, tp: int, bp: int) -> bool:
    return bool((tr and not br) or (tf > bf and tp >= bp))


def _negative_transfer(tr: Any, br: Any, tf: int, bf: int, tp: int, bp: int) -> bool:
    return bool((br and not tr) or tf < bf or tp < bp)


def _outcome_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    grade = row.get("grade", {})
    return (
        grade.get("resolved"), grade.get("fail_to_pass_passed"),
        grade.get("pass_to_pass_passed"), grade.get("canonical_grade_available"),
    )


def _read_attr(rows: dict[tuple[str, str], Decision], target_id: str) -> dict[str, Decision]:
    return {memory_id: decision for (tid, memory_id), decision in rows.items() if tid == target_id}


def main() -> int:
    args = _parse_args()
    _validate_job(args)
    state = _load_study_inputs(args)
    runtime = _prepare_runtime(args, state["plan"])
    journal, result_path, completed, by_target = _load_resume_state(args, state["plan"])
    _execute_treatment_grid(args, state, runtime["evaluator"], journal, result_path, completed, by_target)
    summary = _build_summary(args, state["plan"], runtime, journal, result_path, by_target)
    _write_summary(args.summary, summary)
    print(json.dumps({"status": summary["status"], "run_count": summary["run_count"], "summary": str(args.summary), "next_stage_allowed": False}, indent=2))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "artifacts/burned-pilot/plan.json")
    parser.add_argument("--targets-parquet", type=Path, required=True)
    parser.add_argument("--contextbench-root", type=Path, required=True)
    parser.add_argument("--sif-dir", type=Path, default=ROOT / "artifacts/burned-pilot/images")
    parser.add_argument("--job-tmp", type=Path, required=True)
    parser.add_argument("--mini-bin", type=Path, required=True)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--run-root", type=Path, default=ROOT / "results/burned-pilot/treatments")
    parser.add_argument("--summary", type=Path, default=ROOT / "artifacts/burned-pilot/treatment_summary.json")
    parser.add_argument("--resume", action="store_true", help="Continue only after fully journaled runs; incomplete runs are never replayed.")
    return parser.parse_args()


def _validate_job(args: argparse.Namespace) -> None:
    if not os.environ.get("SLURM_JOB_ID") or os.environ.get("OLLAMA_NO_CLOUD") != "1":
        raise RuntimeError("paired worker treatment must run in Slurm with OLLAMA_NO_CLOUD=1")
    if args.summary.exists():
        raise RuntimeError(f"pilot summary already exists; refusing duplicate study: {args.summary}")


def _load_study_inputs(args: argparse.Namespace) -> dict[str, Any]:
    plan, pools, memories = load_frozen_pilot(args.plan)
    _validate_qualified_worker(plan, args.plan)
    controls = _load_controls(plan, args.plan)
    gate = _load_exposure_gate(plan, args.plan)
    tables = _load_governor_tables(args.plan, memories)
    exposures = _load_exposure_manifest(plan)
    return {
        "plan": plan,
        "pools": pools,
        "memories": memories,
        "controls_by_target": controls,
        "exposure_by_key": exposures,
        "write_by_id": tables["write_by_id"],
        "read_by_key": tables["read_by_key"],
        "related_by_target": clean_related_sources_by_target(),
        "exposure_gate": gate,
    }


def _validate_qualified_worker(plan: dict[str, Any], plan_path: Path) -> None:
    expected = plan["qualification"]["worker"]
    current = {
        "worker_config_sha256": sha256_file(ROOT / "configs/worker.yaml"),
        "worker_adapter_sha256": sha256_file(ROOT / "src/fleet_mem_contextbench/worker.py"),
    }
    if any(current[key] != expected[key] for key in current):
        raise RuntimeError("frozen worker config or code hash changed")
    qualification_path = ROOT / "artifacts/burned-pilot/qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    if qualification.get("plan_sha256") != sha256_file(plan_path) or qualification.get("status") != "PASS":
        raise RuntimeError("worker did not pass the frozen three-target qualification")


def _load_controls(plan: dict[str, Any], plan_path: Path) -> dict[str, dict[str, Any]]:
    path = ROOT / "artifacts/burned-pilot/controls_summary.json"
    controls = json.loads(path.read_text(encoding="utf-8"))
    primary_ids = analysis_target_ids(plan)
    if (
        controls.get("plan_sha256") != sha256_file(plan_path)
        or controls.get("status") != "PASS"
        or controls.get("control_count") != 2 * len(primary_ids)
        or controls.get("target_ids") != primary_ids
    ):
        raise RuntimeError("model-free canonical controls are required for every frozen primary target")
    grouped: dict[str, dict[str, Any]] = {}
    for row in controls["rows"]:
        grouped.setdefault(row["target_id"], {})[row["control_id"]] = row
    if set(grouped) != set(primary_ids):
        raise RuntimeError("canonical controls do not cover the frozen primary targets")
    return grouped


def _load_exposure_gate(plan: dict[str, Any], plan_path: Path) -> dict[str, Any]:
    path = ROOT / "artifacts/burned-pilot/exposure_gate.json"
    gate = json.loads(path.read_text(encoding="utf-8"))
    exposures_path = ROOT / "artifacts/burned-pilot/treatment_exposures.jsonl"
    if (
        gate.get("plan_sha256") != sha256_file(plan_path)
        or gate.get("status") != "PASS"
        or gate.get("treatment_exposures_sha256") != sha256_file(exposures_path)
    ):
        raise RuntimeError("Share-All vs Jev exposure kill gate has not passed")
    minimum = plan["stop_rules"]["minimum_shareall_vs_jev_exposure_discordance_targets"]
    if gate.get("targets_with_shareall_vs_jev_exposure_difference", 0) < minimum:
        raise RuntimeError("frozen Jev exposures fail the preregistered discordance gate")
    read_minimum = plan["stop_rules"]["minimum_jev_read_eligible_targets"]
    if gate.get("targets_with_jev_read_eligibility", 0) < read_minimum:
        raise RuntimeError("Jev read arm has too few eligible target-memory pairs")
    return gate


def _load_governor_tables(plan_path: Path, memories: dict[str, dict[str, Any]]) -> dict[str, Any]:
    gov_dir = ROOT / "artifacts/burned-pilot/governors"
    jev_rows, _ = load_decisions(gov_dir / "jev_write_decisions.jsonl", memories, plan_path)
    llm_rows, _ = load_decisions(gov_dir / "llm_write_decisions.jsonl", memories, plan_path)
    random_rows = read_jsonl(gov_dir / "random_matched_write_decisions.jsonl")
    from fleet_mem_contextbench.treatments import validate_source_decisions

    validate_source_decisions(memories, random_rows)
    jev_share_count = sum(row["action"] == "SHARE" for row in jev_rows)
    random_share_count = sum(row["action"] == "SHARE" for row in random_rows)
    if random_share_count != jev_share_count:
        raise RuntimeError("random admission count is not exactly matched to Jev")
    admitted = {
        "A_NO_MEMORY": set(),
        "B_SHARE_ALL": set(memories),
        "C_RANDOM_MATCHED": {row["memory_id"] for row in random_rows if row["action"] == "SHARE"},
        "D_JEV_WRITE": {row["memory_id"] for row in jev_rows if row["action"] == "SHARE"},
        "E_JEV_WRITE_READ": {row["memory_id"] for row in jev_rows if row["action"] == "SHARE"},
        "F_ORACLE_RELATED_CEILING": set(),
        "G_LLM_WRITE": {row["memory_id"] for row in llm_rows if row["action"] == "SHARE"},
    }
    read_path = gov_dir / "jev_read_decisions.jsonl"
    if not read_path.is_file():
        raise RuntimeError("frozen Jev target-time read decisions are missing")
    return {"write_by_id": admitted, "read_by_key": decision_objects(read_path)}


def _load_exposure_manifest(plan: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = read_jsonl(ROOT / "artifacts/burned-pilot/treatment_exposures.jsonl")
    by_key = {(row["target_id"], row["arm_id"]): row for row in rows}
    primary_ids = analysis_target_ids(plan)
    expected = {(target_id, arm_id) for target_id in primary_ids for arm_id in ARM_IDS}
    if set(by_key) != expected or len(rows) != len(expected):
        raise RuntimeError("frozen treatment exposure manifest is incomplete or has duplicates")
    return by_key


def _prepare_runtime(args: argparse.Namespace, plan: dict[str, Any]) -> dict[str, Any]:
    preflight = ollama_preflight(args.ollama_base_url)
    evaluator = SWEContextBenchApptainerEvaluator(
        args.contextbench_root, args.targets_parquet, args.sif_dir, args.job_tmp,
    )
    grader_preflight = evaluator.preflight(analysis_target_ids(plan))
    return {"worker_preflight": preflight, "grader_preflight": grader_preflight, "evaluator": evaluator}


def _load_resume_state(
    args: argparse.Namespace, plan: dict[str, Any],
) -> tuple[Path, Path, set[tuple[str, str]], dict[str, dict[str, Any]]]:
    args.run_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    journal = args.run_root / "treatment_journal.jsonl"
    result_path = args.run_root / "treatment_results.jsonl"
    events = read_jsonl(journal) if journal.is_file() else []
    completed, started = _journal_pairs(events)
    ambiguous = started - completed
    if ambiguous:
        raise RuntimeError(f"worker/evaluator run was interrupted after starting; refusing to replay: {sorted(ambiguous)}")
    if completed and not args.resume:
        raise RuntimeError("treatment journal already contains completed runs; pass --resume to continue without replay")
    expected = {(target_id, arm_id) for target_id in analysis_target_ids(plan) for arm_id in ARM_IDS}
    if completed - expected:
        raise RuntimeError("treatment journal contains rows outside the frozen target-arm grid")
    records = read_jsonl(result_path) if result_path.is_file() else []
    by_target = _group_run_records(records)
    if {(row["target_id"], row["arm_id"]) for row in records} != completed:
        raise RuntimeError("completed run journal and saved run records disagree")
    return journal, result_path, completed, by_target


def _journal_pairs(events: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    completed = set()
    started = set()
    failed = set()
    for event in events:
        key = (event.get("target_id"), event.get("arm_id"))
        if event.get("event") == "RUN_STARTED":
            if key in started or key in completed or key in failed:
                raise RuntimeError(f"duplicate or out-of-order RUN_STARTED event: {key}")
            started.add(key)
        elif event.get("event") == "RUN_COMPLETED":
            if key not in started or key in completed or key in failed:
                raise RuntimeError(f"duplicate or out-of-order RUN_COMPLETED event: {key}")
            completed.add(key)
        elif event.get("event") == "RUN_FAILED":
            if key not in started or key in completed or key in failed:
                raise RuntimeError(f"duplicate or out-of-order RUN_FAILED event: {key}")
            failed.add(key)
        else:
            raise RuntimeError(f"unknown treatment journal event: {event.get('event')!r}")
    return completed, started


def _group_run_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in records:
        arms = grouped.setdefault(row["target_id"], {})
        if row["arm_id"] in arms:
            raise RuntimeError(f"duplicate treatment result record: {row['target_id']}/{row['arm_id']}")
        arms[row["arm_id"]] = row
    return grouped


def _execute_treatment_grid(
    args: argparse.Namespace,
    state: dict[str, Any],
    evaluator: SWEContextBenchApptainerEvaluator,
    journal: Path,
    result_path: Path,
    completed: set[tuple[str, str]],
    by_target: dict[str, dict[str, Any]],
) -> None:
    plan = state["plan"]
    for target_id in analysis_target_ids(plan):
        pool = state["pools"][target_id]
        target = pool["target"]
        frozen_order = plan["target_governance"]["arm_order_by_target"][target_id]
        if set(frozen_order) != set(ARM_IDS):
            raise RuntimeError(f"frozen treatment order is incomplete for {target_id}")
        for position, arm_id in enumerate(frozen_order, start=1):
            key = (target_id, arm_id)
            if key in completed:
                continue
            result = _execute_one_arm(
                args, state, evaluator, journal, result_path, target_id,
                target, pool, arm_id, position,
            )
            completed.add(key)
            by_target.setdefault(target_id, {})[arm_id] = result
            _print_run_result(result)


def _execute_one_arm(
    args: argparse.Namespace, state: dict[str, Any],
    evaluator: SWEContextBenchApptainerEvaluator, journal: Path, result_path: Path,
    target_id: str, target: dict[str, Any], pool: dict[str, Any],
    arm_id: str, position: int,
) -> dict[str, Any]:
    exposure = _rebuild_exposure(
        target_id, target, pool, arm_id, state["write_by_id"][arm_id],
        state["read_by_key"], state["related_by_target"],
    )
    frozen = state["exposure_by_key"][(target_id, arm_id)]
    _compare_frozen_exposure(target_id, arm_id, exposure, frozen)
    run_dir = args.run_root / target_id / arm_id
    append_jsonl(journal, {
        "event": "RUN_STARTED", "target_id": target_id, "arm_id": arm_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "exposed_memory_ids": exposure["exposed_memory_ids"],
    })
    try:
        result = _run_worker_and_grade(args, evaluator, target_id, target, exposure, run_dir)
        result.update(_make_run_record(
            target_id, arm_id, exposure, frozen,
            result.pop("worker"), result.pop("grade_full"), run_dir,
            treatment_order=position,
            environment_valid=_target_environment_valid(state["controls_by_target"][target_id]),
        ))
        _persist_completed_run(result, run_dir, journal, result_path)
        return result
    except Exception as exc:
        append_jsonl(journal, {
            "event": "RUN_FAILED", "target_id": target_id, "arm_id": arm_id,
            "failed_at_utc": datetime.now(timezone.utc).isoformat(),
            "error_type": type(exc).__name__,
        })
        raise


def _run_worker_and_grade(
    args: argparse.Namespace,
    evaluator: SWEContextBenchApptainerEvaluator,
    target_id: str,
    target: dict[str, Any],
    exposure: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    worker = solve_with_mini_swe_agent(
        target, exposure["exposed_memories"], sif_path=args.sif_dir / f"{target_id}.sif",
        output_dir=run_dir / "worker", repo_root=ROOT,
        worker_config=ROOT / "configs/worker.yaml", mini_bin=args.mini_bin,
        ollama_base_url=args.ollama_base_url,
    )
    patch = Path(worker["patch_path"]).read_text(encoding="utf-8")
    if patch.strip():
        grade = evaluator.evaluate(
            target_id, patch, run_id=f"burned-pilot-{target_id}-{exposure['arm_id']}",
            output_dir=run_dir / "evaluation",
        )
    else:
        grade = {
            "target_id": target_id, "canonical_grade_available": False,
            "resolved": None,
            "reason": "worker submitted no nonempty patch; no synthetic patch was graded",
        }
    return {"worker": worker, "grade_full": grade}


def _target_environment_valid(controls: dict[str, Any]) -> bool:
    noop_passes = controls["NO_PATCH_SEMANTIC_NOOP"]["resolved"] is False
    reference_passes = controls["REFERENCE_PATCH"]["resolved"] is True
    return noop_passes and reference_passes


def _persist_completed_run(
    result: dict[str, Any], run_dir: Path, journal: Path, result_path: Path,
) -> None:
    record_path = run_dir / "run_record.json"
    record_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with record_path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    append_jsonl(result_path, result)
    append_jsonl(journal, {
        "event": "RUN_COMPLETED", "target_id": result["target_id"], "arm_id": result["arm_id"],
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_record_sha256": sha256_file(record_path),
    })


def _print_run_result(result: dict[str, Any]) -> None:
    grade = result["grade"]
    print(json.dumps({
        "target_id": result["target_id"], "arm_id": result["arm_id"],
        "exposed_memory_ids": result["exposed_memory_ids"], "resolved": grade["resolved"],
        "fail_to_pass": [grade["fail_to_pass_passed"], grade["fail_to_pass_total"]],
        "pass_to_pass": [grade["pass_to_pass_passed"], grade["pass_to_pass_total"]],
    }, sort_keys=True))


def _build_summary(
    args: argparse.Namespace,
    plan: dict[str, Any],
    runtime: dict[str, Any],
    journal: Path,
    result_path: Path,
    by_target: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    _attach_transfer(by_target)
    primary_ids = analysis_target_ids(plan)
    records = [by_target[target_id][arm_id] for target_id in primary_ids for arm_id in ARM_IDS]
    no_memory_resolved = sum(
        by_target[target_id]["A_NO_MEMORY"]["grade"].get("resolved") is True
        for target_id in primary_ids
    )
    summary = _pilot_summary_fields(args, plan, runtime, journal, result_path, records, no_memory_resolved)
    return summary


def _pilot_summary_fields(
    args: argparse.Namespace, plan: dict[str, Any], runtime: dict[str, Any],
    journal: Path, result_path: Path, records: list[dict[str, Any]], no_memory_resolved: int,
) -> dict[str, Any]:
    minimum = plan["qualification"]["minimum_no_memory_resolved_for_interpretable_pilot"]
    return {
        "schema_version": 1,
        "stage": "BURNED_PAIRED_EXECUTABLE_PILOT",
        "status": "COMPLETE_STOP_LOW_NO_MEMORY_BASELINE" if no_memory_resolved < minimum else "COMPLETE_BURNED_PILOT_NO_SCALING_AUTHORIZED",
        "plan_sha256": sha256_file(args.plan),
        "treatment_result_sha256": sha256_file(result_path),
        "journal_sha256": sha256_file(journal),
        "worker_preflight": runtime["worker_preflight"],
        "grader_preflight": runtime["grader_preflight"],
        "target_count": len(analysis_target_ids(plan)), "arm_count": len(ARM_IDS), "run_count": len(records),
        "primary_target_ids": analysis_target_ids(plan),
        "no_memory_resolved_count": no_memory_resolved,
        "minimum_no_memory_resolved_for_interpretability": minimum,
        "resolved_by_arm": {
            arm_id: sum(row["grade"].get("resolved") is True for row in records if row["arm_id"] == arm_id)
            for arm_id in ARM_IDS
        },
        "valid_grade_count_by_arm": {
            arm_id: sum(row["grade"].get("canonical_grade_available") is True for row in records if row["arm_id"] == arm_id)
            for arm_id in ARM_IDS
        },
        "transfer_counts_vs_no_memory": _transfer_counts(records),
        "treatment_discordance": _discordant_cases(_records_by_target(records)),
        "per_target_arm_records": records,
        "next_stage_allowed": False,
    }


def _records_by_target(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in records:
        grouped.setdefault(row["target_id"], {})[row["arm_id"]] = row
    return grouped


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

def _rebuild_exposure(
    target_id: str,
    target: dict[str, Any],
    pool: dict[str, Any],
    arm_id: str,
    admitted_ids: set[str],
    read_decisions: dict[tuple[str, str], Decision],
    related_by_target: dict[str, set[str]],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "target": target, "pool": pool, "arm_id": arm_id,
        "admitted_ids": admitted_ids,
    }
    if arm_id == "E_JEV_WRITE_READ":
        kwargs["frozen_read_decisions"] = _read_attr(read_decisions, target_id)
    if arm_id == "F_ORACLE_RELATED_CEILING":
        kwargs["related_source_ids"] = related_by_target.get(target_id, set())
    exposure = treatment_exposure(**kwargs)
    candidate_ids = {row["memory"]["memory_id"] for row in pool["candidate_pool"]}
    shared_ids = set(exposure["shared_memory_ids"])
    exposure["source_write_decisions"] = {
        memory_id: "SHARE" if memory_id in shared_ids else "DO_NOT_SHARE"
        for memory_id in sorted(candidate_ids)
    }
    return exposure


def _compare_frozen_exposure(target_id: str, arm_id: str, actual: dict[str, Any], frozen: dict[str, Any]) -> None:
    fields = (
        "candidate_pool_size", "shared_memory_ids", "retrieval_window_ids", "retrieved_memory_ids",
        "source_write_decisions", "write_admission_rate", "read_decisions", "exposed_memory_ids",
        "memory_tokens_exposed", "memory_token_count_method",
        "memory_token_counts", "memory_token_counts_exposed", "memory_card_sizes",
        "exposed_memory_card_sizes", "memory_serialized_bytes_exposed", "read_abstention_rate",
    )
    for field in fields:
        aliases = {
            "memory_tokens_exposed": "memory_token_estimate",
            "memory_token_count_method": "memory_token_estimate_method",
            "memory_token_counts": "memory_token_counts_retrieved",
        }
        if actual.get(field) != frozen.get(aliases.get(field, field)):
            raise RuntimeError(f"frozen treatment exposure changed for {target_id}/{arm_id}: {field}")


def _make_run_record(
    target_id: str, arm_id: str, exposure: dict[str, Any], frozen: dict[str, Any],
    worker: dict[str, Any], grade: dict[str, Any], run_dir: Path,
    *, treatment_order: int, environment_valid: bool,
) -> dict[str, Any]:
    read_decisions = exposure["read_decisions"]
    write_cost = frozen["source_write_cost_attribution_nonadditive"]
    cost, latency = _governor_cost_attribution(write_cost, read_decisions)
    canonical_path = run_dir / "evaluation/canonical_result.json"
    return {
        "target_id": target_id,
        "arm_id": arm_id,
        "treatment_order": treatment_order,
        "environment_valid": environment_valid,
        "environment_validation_status": "CANONICAL_NOOP_AND_REFERENCE_CONTROLS_PASS" if environment_valid else "INVALID_CANONICAL_CONTROL",
        "candidate_pool_size": exposure["candidate_pool_size"],
        "source_write_decisions": frozen["source_write_decisions"],
        "source_write_decision_origin": frozen["source_write_decision_origin"],
        "write_admission_rate": frozen["write_admission_rate"],
        "source_write_cost_attribution_nonadditive": write_cost,
        "shared_memory_ids": exposure["shared_memory_ids"],
        "retrieval_window_ids": exposure["retrieval_window_ids"],
        "retrieved_memory_ids": exposure["retrieved_memory_ids"],
        "read_decisions": read_decisions,
        "read_abstention_rate": exposure["read_abstention_rate"],
        "exposed_memory_ids": exposure["exposed_memory_ids"],
        "memory_count_exposed": len(exposure["exposed_memory_ids"]),
        "memory_tokens_exposed_estimate": exposure["memory_tokens_exposed"],
        "memory_token_estimate_method": exposure["memory_token_count_method"],
        "memory_token_counts_retrieved": exposure["memory_token_counts"],
        "memory_token_counts_exposed": exposure["memory_token_counts_exposed"],
        "memory_card_sizes": exposure["memory_card_sizes"],
        "exposed_memory_card_sizes": exposure["exposed_memory_card_sizes"],
        "memory_serialized_bytes_exposed": exposure["memory_serialized_bytes_exposed"],
        "worker": worker,
        "worker_input_tokens": worker.get("worker_input_tokens"),
        "worker_output_tokens": worker.get("worker_output_tokens"),
        "context_tokens_per_call": worker.get("context_tokens_per_call"),
        "agent_steps": worker.get("agent_steps"),
        "tool_calls": worker.get("tool_calls"),
        "agent_latency_seconds": worker.get("wall_seconds"),
        "governor_calls_attributed": write_cost.get("unique_calls", 0) + len(read_decisions),
        "governor_latency_ms_attributed": latency,
        "governor_cost_attributed": cost,
        "grade": _grade(grade),
        "canonical_result_path": str(canonical_path) if canonical_path.is_file() else None,
        "canonical_result_sha256": sha256_file(canonical_path) if canonical_path.is_file() else None,
        "run_directory": str(run_dir),
    }


def _governor_cost_attribution(
    write_cost: dict[str, Any], read_decisions: dict[str, dict[str, Any]],
) -> tuple[int | float | None, int | float]:
    write_calls = write_cost.get("unique_calls", 0)
    read_costs = [row.get("cost") for row in read_decisions.values()]
    costs = ([write_cost.get("cost")] if write_calls else [])
    if read_costs:
        costs.append(sum(read_costs) if all(isinstance(value, (int, float)) for value in read_costs) else None)
    total_cost = sum(costs) if costs and all(isinstance(value, (int, float)) for value in costs) else (0.0 if not costs else None)
    read_latency = sum(
        row.get("latency_ms") or 0 for row in read_decisions.values()
        if isinstance(row.get("latency_ms"), (int, float))
    )
    return total_cost, (write_cost.get("latency_ms") or 0) + read_latency


def _attach_transfer(by_target: dict[str, dict[str, Any]]) -> None:
    for arms in by_target.values():
        baseline = arms.get("A_NO_MEMORY")
        if baseline is None:
            continue
        for arm_id, row in arms.items():
            row.update(
                {"positive_transfer": None, "negative_transfer": None, "preserved_success": None, "persistent_failure": None}
                if arm_id == "A_NO_MEMORY" else _transfer(row, baseline)
            )


def _transfer_counts(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        arm_id: {
            metric: sum(row.get(metric) is True for row in rows if row["arm_id"] == arm_id)
            for metric in ("positive_transfer", "negative_transfer", "preserved_success", "persistent_failure")
        }
        for arm_id in ARM_IDS if arm_id != "A_NO_MEMORY"
    }


def _discordant_cases(by_target: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    cases = {name: [] for name in ("exposure", "outcome", "both", "write", "read")}
    for target_id, arms in by_target.items():
        for left, right in itertools.combinations(ARM_IDS, 2):
            if left not in arms or right not in arms:
                continue
            pair = _pair_discordance(target_id, left, right, arms[left], arms[right])
            for name, value in pair.items():
                if value is not None:
                    cases[name].append(value)
    return {
        "exposure_discordant_cases": cases["exposure"],
        "outcome_discordant_cases": cases["outcome"],
        "exposure_and_outcome_discordant_cases": cases["both"],
        "source_write_decision_discordant_cases": cases["write"],
        "target_read_decision_discordant_cases": cases["read"],
    }


def _pair_discordance(
    target_id: str, left: str, right: str, a: dict[str, Any], b: dict[str, Any],
) -> dict[str, dict[str, Any] | None]:
    exposed_a, exposed_b = set(a["exposed_memory_ids"]), set(b["exposed_memory_ids"])
    outcome_a, outcome_b = _outcome_signature(a), _outcome_signature(b)
    exposure_diff = exposed_a != exposed_b
    outcome_diff = outcome_a != outcome_b
    common = {
        "target_id": target_id, "left_arm": left, "right_arm": right,
        "left_exposed_memory_ids": a["exposed_memory_ids"],
        "right_exposed_memory_ids": b["exposed_memory_ids"],
        "symmetric_difference_exposed_ids": sorted(exposed_a ^ exposed_b),
        "left_outcome": outcome_a, "right_outcome": outcome_b,
    }
    return {
        "exposure": common if exposure_diff else None,
        "outcome": common if outcome_diff else None,
        "both": common if exposure_diff and outcome_diff else None,
        "write": _write_discordance(target_id, left, right, a, b),
        "read": _read_discordance(target_id, left, right, a, b),
    }


def _write_discordance(
    target_id: str, left: str, right: str, a: dict[str, Any], b: dict[str, Any],
) -> dict[str, Any] | None:
    left_actions, right_actions = a["source_write_decisions"], b["source_write_decisions"]
    different = _different_assignment_ids(left_actions, right_actions)
    return {"target_id": target_id, "left_arm": left, "right_arm": right, "different_memory_ids": different} if different else None


def _read_discordance(
    target_id: str, left: str, right: str, a: dict[str, Any], b: dict[str, Any],
) -> dict[str, Any] | None:
    left_actions = {memory_id: value.get("action") for memory_id, value in a["read_decisions"].items()}
    right_actions = {memory_id: value.get("action") for memory_id, value in b["read_decisions"].items()}
    different = _different_assignment_ids(left_actions, right_actions)
    return {
        "target_id": target_id, "left_arm": left, "right_arm": right,
        "different_memory_ids": different, "left_actions": left_actions, "right_actions": right_actions,
    } if different else None


def _different_assignment_ids(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    return sorted(
        memory_id for memory_id in set(left) | set(right)
        if left.get(memory_id) != right.get(memory_id)
    )


if __name__ == "__main__":
    raise SystemExit(main())
