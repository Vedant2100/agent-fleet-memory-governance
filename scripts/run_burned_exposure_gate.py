#!/usr/bin/env python3
"""Freeze target exposures and run the second structural kill gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_mem_contextbench.governors.base import Decision
from fleet_mem_contextbench.governors.jev_system_one import JevSystemOneGovernor
from fleet_mem_contextbench.pilot_runtime import (
    analysis_target_ids, clean_related_sources_by_target, load_decisions, load_frozen_pilot, sha256_file,
)
from fleet_mem_contextbench.treatments import (
    deterministic_retrieval, freeze_size_matched_random, treatment_exposure,
)


ARM_IDS = (
    "A_NO_MEMORY", "B_SHARE_ALL", "C_RANDOM_MATCHED", "D_JEV_WRITE",
    "E_JEV_WRITE_READ", "F_ORACLE_RELATED_CEILING", "G_LLM_WRITE",
)


def main() -> int:
    args = _parse_args()
    paths = _output_paths(args)
    if args.stage == "write-check":
        return _run_write_check(args, paths)
    return _run_exposure_freeze(args, paths)


def _run_write_check(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    if paths["write_gate"].exists():
        raise RuntimeError("Jev write exposure gate already exists; refusing to repeat")
    state = _load_jev_assignments(args)
    if _stop_on_degenerate_write(args, paths, state):
        return 2
    gate_data = _measure_write_exposure_gate(state)
    if _stop_on_trivial_exposure(args, paths, state, gate_data):
        return 2
    if _stop_on_trivial_read_eligibility(args, paths, state, gate_data):
        return 2
    _write_write_gate(args, paths, state, gate_data)
    _print_gate(json.loads(paths["write_gate"].read_text(encoding="utf-8")))
    return 0


def _run_exposure_freeze(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    _require_fresh_outputs(paths, allow_existing_write_gate=True)
    state = _load_assignments(args)
    gate_data = _measure_write_exposure_gate(state)
    _validate_prior_write_gate(args, paths["write_gate"], state, gate_data)
    state["base_exposures"] = gate_data["base_exposures"]
    read_rows = _collect_jev_read_decisions(args, state, paths)
    _write_read_decisions(args, paths, read_rows)
    exposures = _build_treatment_exposures(state, read_rows)
    gate = _make_exposure_gate(args, state, gate_data, read_rows, exposures)
    _write_final_exposure_artifacts(paths, gate, exposures)
    _print_gate(gate)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("write-check", "finish"), default="finish")
    parser.add_argument("--plan", type=Path, default=ROOT / "artifacts/burned-pilot/plan.json")
    parser.add_argument("--governor-dir", type=Path, default=ROOT / "artifacts/burned-pilot/governors")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/burned-pilot")
    return parser.parse_args()


def _output_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "gate": args.output_dir / "exposure_gate.json",
        "write_gate": args.output_dir / "exposure_write_gate.json",
        "exposures": args.output_dir / "treatment_exposures.jsonl",
        "read_decisions": args.governor_dir / "jev_read_decisions.jsonl",
        "read_summary": args.governor_dir / "jev_read_summary.json",
        "read_journal": args.governor_dir / "jev_read_journal.jsonl",
        "read_lock": args.governor_dir / ".jev_read.lock",
    }


def _require_fresh_outputs(paths: dict[str, Path], allow_existing_write_gate: bool = False) -> None:
    existing = [
        str(path) for key, path in paths.items()
        if path.exists() and not (allow_existing_write_gate and key == "write_gate")
    ]
    if existing:
        raise RuntimeError(f"burned exposure assignment already exists; refusing to repeat decisions: {existing}")


def _load_jev_assignments(args: argparse.Namespace) -> dict[str, Any]:
    plan, pools, memories = load_frozen_pilot(args.plan)
    jev_rows, jev_summary = load_decisions(args.governor_dir / "jev_write_decisions.jsonl", memories, args.plan)
    random_rows = _load_random_table(args.governor_dir, memories, jev_rows)
    return {
        "plan": plan, "pools": pools, "memories": memories,
        "jev_rows": jev_rows, "jev_summary": jev_summary,
        "random_rows": random_rows,
        "jev_admitted": _admitted(jev_rows),
        "random_admitted": _admitted(random_rows),
        "all_admitted": set(memories),
    }


def _load_assignments(args: argparse.Namespace) -> dict[str, Any]:
    state = _load_jev_assignments(args)
    llm_rows, _ = load_decisions(args.governor_dir / "llm_write_decisions.jsonl", state["memories"], args.plan)
    llm_admitted = _admitted(llm_rows)
    state.update({
        "llm_rows": llm_rows,
        "llm_admitted": llm_admitted,
        "admitted": {
            "A_NO_MEMORY": set(), "B_SHARE_ALL": set(state["memories"]),
            "C_RANDOM_MATCHED": state["random_admitted"],
            "D_JEV_WRITE": state["jev_admitted"],
            "E_JEV_WRITE_READ": state["jev_admitted"],
            "F_ORACLE_RELATED_CEILING": set(), "G_LLM_WRITE": llm_admitted,
        },
    })
    return state


def _load_random_table(
    governor_dir: Path,
    memories: dict[str, dict[str, Any]],
    jev_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    path = governor_dir / "random_matched_write_decisions.jsonl"
    if not path.is_file():
        raise RuntimeError("size-matched random admission table is missing")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = freeze_size_matched_random(memories, jev_rows, seed=42)
    if rows != expected:
        raise RuntimeError("stored random table is not the deterministic exact-count Jev match")
    return rows


def _admitted(rows: list[dict[str, Any]]) -> set[str]:
    return {row["memory_id"] for row in rows if row["action"] == "SHARE"}


def _stop_on_degenerate_write(args: argparse.Namespace, paths: dict[str, Path], state: dict[str, Any]) -> bool:
    count = len(state["memories"])
    admitted = len(state["jev_admitted"])
    if admitted not in {0, count}:
        return False
    report = {
        "status": "STOP_DEGENERATE_JEV_WRITE", "share_count": admitted,
        "candidate_count": count, "reason": "Jev admitted either no memories or every memory",
        "plan_sha256": sha256_file(args.plan),
    }
    _write_json(paths["gate"], report)
    _print_gate(report)
    return True


def _measure_write_exposure_gate(state: dict[str, Any]) -> dict[str, Any]:
    target_rows = []
    views: dict[tuple[str, str], dict[str, Any]] = {}
    for target_id in analysis_target_ids(state["plan"]):
        pool = state["pools"][target_id]
        share_all = treatment_exposure(
            target=pool["target"], pool=pool, arm_id="B_SHARE_ALL",
            admitted_ids=state["all_admitted"],
        )
        jev = treatment_exposure(
            target=pool["target"], pool=pool, arm_id="D_JEV_WRITE",
            admitted_ids=state["jev_admitted"],
        )
        row = _write_discordance_row(target_id, share_all, jev)
        read_candidates = [
            entry["memory"]["memory_id"] for entry in deterministic_retrieval(pool)
            if entry["memory"]["memory_id"] in state["jev_admitted"]
        ]
        row["jev_read_candidate_ids"] = read_candidates
        row["jev_read_candidate_count"] = len(read_candidates)
        row["jev_read_eligible"] = bool(read_candidates)
        target_rows.append(row)
        views[(target_id, "B_SHARE_ALL")] = share_all
        views[(target_id, "D_JEV_WRITE")] = jev
    return {
        "per_target": target_rows,
        "base_exposures": views,
        "discordant_target_count": sum(row["exposure_differs"] for row in target_rows),
        "minimum": state["plan"]["stop_rules"]["minimum_shareall_vs_jev_exposure_discordance_targets"],
        "read_eligible_target_count": sum(row["jev_read_eligible"] for row in target_rows),
        "minimum_read_eligible": state["plan"]["stop_rules"]["minimum_jev_read_eligible_targets"],
    }


def _write_discordance_row(
    target_id: str, share_all: dict[str, Any], jev: dict[str, Any],
) -> dict[str, Any]:
    all_ids = set(share_all["exposed_memory_ids"])
    jev_ids = set(jev["exposed_memory_ids"])
    return {
        "target_id": target_id,
        "share_all_exposed_memory_ids": sorted(all_ids),
        "jev_write_exposed_memory_ids": sorted(jev_ids),
        "exposure_differs": all_ids != jev_ids,
        "symmetric_difference": sorted(all_ids ^ jev_ids),
    }


def _stop_on_trivial_exposure(
    args: argparse.Namespace, paths: dict[str, Path], state: dict[str, Any], data: dict[str, Any],
) -> bool:
    if data["discordant_target_count"] >= data["minimum"]:
        return False
    report = {
        "status": "STOP_TRIVIAL_WRITE_EXPOSURE",
        "share_count": len(state["jev_admitted"]),
        "candidate_count": len(state["memories"]),
        "jev_share_rate": state["jev_summary"]["share_rate"],
        "random_share_count": len(state["random_admitted"]),
        "targets_with_shareall_vs_jev_exposure_difference": data["discordant_target_count"],
        "required_targets": data["minimum"],
        "per_target": data["per_target"],
        "plan_sha256": sha256_file(args.plan),
    }
    _write_json(paths["gate"], report)
    _print_gate(report)
    return True


def _stop_on_trivial_read_eligibility(
    args: argparse.Namespace, paths: dict[str, Path], state: dict[str, Any], data: dict[str, Any],
) -> bool:
    if data["read_eligible_target_count"] >= data["minimum_read_eligible"]:
        return False
    report = {
        "status": "STOP_TRIVIAL_JEV_READ_ELIGIBILITY",
        "candidate_count": len(state["memories"]),
        "jev_share_count": len(state["jev_admitted"]),
        "targets_with_at_least_one_jev_memory_in_fixed_retrieval": data["read_eligible_target_count"],
        "required_targets": data["minimum_read_eligible"],
        "targets_with_shareall_vs_jev_exposure_difference": data["discordant_target_count"],
        "per_target": data["per_target"],
        "plan_sha256": sha256_file(args.plan),
    }
    _write_json(paths["gate"], report)
    _print_gate(report)
    return True


def _write_write_gate(args: argparse.Namespace, paths: dict[str, Path], state: dict[str, Any], data: dict[str, Any]) -> None:
    report = {
        "status": "PASS_WRITE_EXPOSURE_GATE", "plan_sha256": sha256_file(args.plan),
        "jev_decisions_sha256": sha256_file(args.governor_dir / "jev_write_decisions.jsonl"),
        "random_decisions_sha256": sha256_file(args.governor_dir / "random_matched_write_decisions.jsonl"),
        "candidate_count": len(state["memories"]), "jev_share_count": len(state["jev_admitted"]),
        "jev_share_rate": state["jev_summary"]["share_rate"],
        "minimum_discordant_targets": data["minimum"],
        "targets_with_shareall_vs_jev_exposure_difference": data["discordant_target_count"],
        "minimum_read_eligible_targets": data["minimum_read_eligible"],
        "targets_with_jev_read_eligibility": data["read_eligible_target_count"],
        "per_target": data["per_target"],
    }
    _write_json(paths["write_gate"], report)


def _validate_prior_write_gate(
    args: argparse.Namespace, path: Path, state: dict[str, Any], data: dict[str, Any],
) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    valid = (
        report.get("status") == "PASS_WRITE_EXPOSURE_GATE"
        and report.get("plan_sha256") == sha256_file(args.plan)
        and report.get("jev_decisions_sha256") == sha256_file(args.governor_dir / "jev_write_decisions.jsonl")
        and report.get("random_decisions_sha256") == sha256_file(args.governor_dir / "random_matched_write_decisions.jsonl")
        and report.get("jev_share_count") == len(state["jev_admitted"])
        and report.get("minimum_read_eligible_targets") == data["minimum_read_eligible"]
        and report.get("targets_with_shareall_vs_jev_exposure_difference") == data["discordant_target_count"]
        and report.get("targets_with_jev_read_eligibility") == data["read_eligible_target_count"]
        and report.get("per_target") == data["per_target"]
    )
    if not valid:
        raise RuntimeError("Jev write exposure gate is missing, failed, or bound to different frozen decisions")


def _collect_jev_read_decisions(
    args: argparse.Namespace, state: dict[str, Any], paths: dict[str, Path],
) -> list[dict[str, Any]]:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Jev target-read decisions must run in the preregistered Slurm allocation")
    governor = JevSystemOneGovernor()
    lock_fd = os.open(paths["read_lock"], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(lock_fd, f"pid={os.getpid()}\n".encode())
    os.close(lock_fd)
    rows = []
    try:
        for target_id in analysis_target_ids(state["plan"]):
            pool = state["pools"][target_id]
            memories = _admitted_retrieval(pool, state["jev_admitted"])
            for memory in memories:
                rows.append(_ask_jev_read_once(governor, target_id, pool["target"], memory, paths["read_journal"]))
    finally:
        paths["read_lock"].unlink(missing_ok=True)
    return rows


def _admitted_retrieval(pool: dict[str, Any], admitted: set[str]) -> list[dict[str, Any]]:
    return [
        entry["memory"] for entry in deterministic_retrieval(pool)
        if entry["memory"]["memory_id"] in admitted
    ]


def _ask_jev_read_once(
    governor: JevSystemOneGovernor, target_id: str, target: dict[str, Any],
    memory: dict[str, Any], journal: Path,
) -> dict[str, Any]:
    source_input = {"target": target, "candidate": memory}
    input_hash = hashlib.sha256(_canonical(source_input).encode("utf-8")).hexdigest()
    _append_row(journal, {
        "event": "CALL_STARTED", "target_id": target_id,
        "memory_id": memory["memory_id"], "input_sha256": input_hash,
    })
    try:
        decision = governor.decide_read(target, [memory])[0]
        decision.validate("read")
    except Exception as exc:
        _append_row(journal, {
            "event": "CALL_FAILED", "target_id": target_id,
            "memory_id": memory["memory_id"], "input_sha256": input_hash,
            "error_type": type(exc).__name__,
        })
        raise RuntimeError(f"Jev read decision failed for {target_id}/{memory['memory_id']}; it was not retried") from exc
    row = {"target_id": target_id, "memory_id": memory["memory_id"], "input_sha256": input_hash, **_decision_record(decision)}
    _append_row(journal, {"event": "DECISION_RECORDED", **row})
    return row


def _write_read_decisions(args: argparse.Namespace, paths: dict[str, Path], rows: list[dict[str, Any]]) -> None:
    with paths["read_decisions"].open("x", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    costs = [row.get("cost") for row in rows]
    summary = {
        "status": "COMPLETE", "plan_sha256": sha256_file(args.plan),
        "decision_count": len(rows),
        "action_counts": {action: sum(row["action"] == action for row in rows) for action in ("EXPOSE", "WITHHOLD")},
        "latency_ms_sum": sum(row.get("latency_ms") or 0 for row in rows),
        "cost_sum": _sum_complete(costs),
        "input_tokens": _sum_complete(row.get("input_tokens") for row in rows),
        "output_tokens": _sum_complete(row.get("output_tokens") for row in rows),
        "decisions_sha256": sha256_file(paths["read_decisions"]),
        "journal_sha256": sha256_file(paths["read_journal"]),
    }
    _write_json(paths["read_summary"], summary)


def _build_treatment_exposures(state: dict[str, Any], read_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    read_table = _read_decisions_by_target(read_rows)
    relation_ids = clean_related_sources_by_target()
    source_rows = _source_rows_by_id(state)
    random_rows = {row["memory_id"]: row for row in state["random_rows"]}
    exposure_rows = []
    for target_id in analysis_target_ids(state["plan"]):
        target_rows = _exposures_for_target(state, target_id, read_table, relation_ids)
        exposure_rows.extend(
            _serialize_exposure(target_id, arm_id, exposure, state, source_rows, random_rows)
            for arm_id, exposure in target_rows.items()
        )
    return exposure_rows


def _exposures_for_target(
    state: dict[str, Any], target_id: str,
    read_table: dict[str, dict[str, Decision]], relation_ids: dict[str, set[str]],
) -> dict[str, dict[str, Any]]:
    pool = state["pools"][target_id]
    target = pool["target"]
    writes = state["admitted"]
    exposures = {
        "A_NO_MEMORY": treatment_exposure(target=target, pool=pool, arm_id="A_NO_MEMORY", admitted_ids=writes["A_NO_MEMORY"]),
        "B_SHARE_ALL": state["base_exposures"][(target_id, "B_SHARE_ALL")],
        "C_RANDOM_MATCHED": treatment_exposure(target=target, pool=pool, arm_id="C_RANDOM_MATCHED", admitted_ids=writes["C_RANDOM_MATCHED"]),
        "D_JEV_WRITE": state["base_exposures"][(target_id, "D_JEV_WRITE")],
        "E_JEV_WRITE_READ": treatment_exposure(
            target=target, pool=pool, arm_id="E_JEV_WRITE_READ", admitted_ids=writes["E_JEV_WRITE_READ"],
            frozen_read_decisions=read_table.get(target_id, {}),
        ),
        "F_ORACLE_RELATED_CEILING": treatment_exposure(
            target=target, pool=pool, arm_id="F_ORACLE_RELATED_CEILING", admitted_ids=set(),
            related_source_ids=relation_ids.get(target_id, set()),
        ),
        "G_LLM_WRITE": treatment_exposure(target=target, pool=pool, arm_id="G_LLM_WRITE", admitted_ids=writes["G_LLM_WRITE"]),
    }
    return exposures


def _serialize_exposure(
    target_id: str, arm_id: str, exposure: dict[str, Any], state: dict[str, Any],
    source_rows: dict[str, dict[str, Any]], random_rows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidate_ids = {entry["memory"]["memory_id"] for entry in state["pools"][target_id]["candidate_pool"]}
    write_actions = _actions_for_arm(arm_id, candidate_ids, exposure, source_rows, random_rows)
    write_costs = _write_cost_rows(arm_id, candidate_ids, source_rows)
    read_decisions = exposure["read_decisions"]
    return {
        "target_id": target_id, "arm_id": arm_id,
        "candidate_pool_size": exposure["candidate_pool_size"],
        "candidate_memory_ids": sorted(candidate_ids),
        "source_write_decision_origin": _decision_origin(arm_id),
        "source_write_decisions": write_actions,
        "source_write_cost_attribution_nonadditive": _write_cost_attribution(write_costs),
        "shared_memory_ids": exposure["shared_memory_ids"],
        "retrieval_window_ids": exposure["retrieval_window_ids"],
        "retrieved_memory_ids": exposure["retrieved_memory_ids"],
        "read_decisions": read_decisions,
        "exposed_memory_ids": exposure["exposed_memory_ids"],
        "memory_token_estimate": exposure["memory_tokens_exposed"],
        "memory_token_estimate_method": exposure["memory_token_count_method"],
        "memory_token_counts_retrieved": exposure["memory_token_counts"],
        "memory_token_counts_exposed": exposure["memory_token_counts_exposed"],
        "memory_card_sizes": exposure["memory_card_sizes"],
        "exposed_memory_card_sizes": exposure["exposed_memory_card_sizes"],
        "memory_serialized_bytes_exposed": exposure["memory_serialized_bytes_exposed"],
        "read_abstention_rate": exposure["read_abstention_rate"],
        "read_governor_cost": _sum_complete(row.get("cost") for row in read_decisions.values()),
        "read_governor_latency_ms": sum(row.get("latency_ms") or 0 for row in read_decisions.values()),
        "write_admission_rate": sum(action == "SHARE" for action in write_actions.values()) / max(1, len(candidate_ids)),
    }


def _actions_for_arm(
    arm_id: str, candidate_ids: set[str], exposure: dict[str, Any],
    source_rows: dict[str, dict[str, Any]], random_rows: dict[str, dict[str, Any]],
) -> dict[str, str]:
    if arm_id == "A_NO_MEMORY":
        return {memory_id: "DO_NOT_SHARE" for memory_id in candidate_ids}
    if arm_id == "B_SHARE_ALL":
        return {memory_id: "SHARE" for memory_id in candidate_ids}
    if arm_id == "F_ORACLE_RELATED_CEILING":
        shared = set(exposure["shared_memory_ids"])
        return {memory_id: "SHARE" if memory_id in shared else "DO_NOT_SHARE" for memory_id in candidate_ids}
    table = random_rows if arm_id == "C_RANDOM_MATCHED" else source_rows[arm_id]
    return {memory_id: table[memory_id]["action"] for memory_id in candidate_ids}


def _decision_origin(arm_id: str) -> str:
    if arm_id in {"D_JEV_WRITE", "E_JEV_WRITE_READ"}:
        return "frozen_jev_source_decision"
    if arm_id == "G_LLM_WRITE":
        return "frozen_deliberative_llm_source_decision"
    if arm_id == "C_RANDOM_MATCHED":
        return "seeded_size_matched_random_assignment"
    if arm_id == "F_ORACLE_RELATED_CEILING":
        return "hidden_known_relation_oracle"
    return "factorial_arm_assignment"


def _write_cost_rows(
    arm_id: str, candidate_ids: set[str], source_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if arm_id in {"D_JEV_WRITE", "E_JEV_WRITE_READ", "G_LLM_WRITE"}:
        table = source_rows[arm_id]
    else:
        return []
    return [table[memory_id] for memory_id in candidate_ids]


def _write_cost_attribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"latency_ms": 0, "cost": 0.0, "input_tokens": 0, "output_tokens": 0, "unique_calls": 0}
    return {
        "latency_ms": sum(row.get("latency_ms") or 0 for row in rows),
        "cost": _sum_complete(row.get("cost") for row in rows),
        "input_tokens": _sum_complete(row.get("input_tokens") for row in rows),
        "output_tokens": _sum_complete(row.get("output_tokens") for row in rows),
        "unique_calls": len(rows),
    }


def _source_rows_by_id(state: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "D_JEV_WRITE": {row["memory_id"]: row for row in state["jev_rows"]},
        "E_JEV_WRITE_READ": {row["memory_id"]: row for row in state["jev_rows"]},
        "G_LLM_WRITE": {row["memory_id"]: row for row in state["llm_rows"]},
    }


def _read_decisions_by_target(rows: list[dict[str, Any]]) -> dict[str, dict[str, Decision]]:
    result: dict[str, dict[str, Decision]] = {}
    for row in rows:
        result.setdefault(row["target_id"], {})[row["memory_id"]] = Decision(
            action=row["action"], confidence=row["confidence"], probabilities=row["probabilities"],
            rationale=row["rationale"], latency_ms=row["latency_ms"], cost=row["cost"],
            input_tokens=row["input_tokens"], output_tokens=row["output_tokens"],
        )
    return result


def _make_exposure_gate(
    args: argparse.Namespace, state: dict[str, Any], write_gate: dict[str, Any],
    read_rows: list[dict[str, Any]], exposures: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "PASS", "plan_sha256": sha256_file(args.plan),
        "candidate_count": len(state["memories"]),
        "jev_share_count": len(state["jev_admitted"]),
        "jev_share_rate": state["jev_summary"]["share_rate"],
        "random_admission_count": len(state["random_admitted"]),
        "llm_share_count": len(state["llm_admitted"]),
        "minimum_shareall_vs_jev_exposure_discordance_targets": write_gate["minimum"],
        "targets_with_shareall_vs_jev_exposure_difference": write_gate["discordant_target_count"],
        "minimum_jev_read_eligible_targets": write_gate["minimum_read_eligible"],
        "targets_with_jev_read_eligibility": write_gate["read_eligible_target_count"],
        "per_target": write_gate["per_target"],
        "frozen_jev_read_decision_count": len(read_rows),
        "treatment_arm_count": len(ARM_IDS),
        "treatment_exposure_rows": len(exposures),
    }


def _write_final_exposure_artifacts(
    paths: dict[str, Path], gate: dict[str, Any], rows: list[dict[str, Any]],
) -> None:
    with paths["exposures"].open("x", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    gate["treatment_exposures_sha256"] = sha256_file(paths["exposures"])
    _write_json(paths["gate"], gate)


def _decision_record(decision: Decision) -> dict[str, Any]:
    return {
        "action": decision.action, "confidence": decision.confidence,
        "probabilities": decision.probabilities, "rationale": decision.rationale,
        "latency_ms": decision.latency_ms, "cost": decision.cost,
        "input_tokens": decision.input_tokens, "output_tokens": decision.output_tokens,
    }


def _sum_complete(values) -> int | float | None:
    items = list(values)
    return sum(items) if all(isinstance(value, (int, float)) for value in items) else None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _print_gate(gate: dict[str, Any]) -> None:
    keys = (
        "status", "share_count", "candidate_count",
        "targets_with_shareall_vs_jev_exposure_difference",
        "required_targets", "jev_share_count", "random_admission_count",
        "frozen_jev_read_decision_count",
        "targets_with_jev_read_eligibility",
    )
    print(json.dumps({key: gate[key] for key in keys if key in gate}, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
