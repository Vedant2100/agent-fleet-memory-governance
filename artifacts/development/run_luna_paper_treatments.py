#!/usr/bin/env python3
"""Run the four remaining Luna paper arms after the frozen signal gate."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_burned_exposure_gate as exposure_gate
import run_source_governor as source_governor
import run_sweedit_burned as pilot
from fleet_mem_contextbench.governors.base import Decision
from fleet_mem_contextbench.pilot_runtime import analysis_target_ids, sha256_file
from fleet_mem_contextbench.sweedit_worker import load_worker_settings
from fleet_mem_contextbench.treatments import treatment_exposure


PLAN = ROOT / "artifacts/burned-pilot/plan.json"
SIGNAL = ROOT / "artifacts/development/luna_oracle_signal_289648_test_filtered_regrade.json"
BASELINE = ROOT / "artifacts/development/luna_oracle_signal_289648.json"
OUT = ROOT / "results/development/paper-treatments-luna"
ATTEMPT_NAME = os.environ.get("FMC_TREATMENT_ATTEMPT", "attempt-0001")
RUN_OUT = OUT / ATTEMPT_NAME
PRIOR_ATTEMPT = os.environ.get("FMC_PRIOR_ATTEMPT")
REUSE_DECISIONS_FROM = os.environ.get("FMC_REUSE_DECISIONS_FROM")
ARMS = ("B_SHARE_ALL", "C_RANDOM_MATCHED", "D_JEV_WRITE", "E_JEV_WRITE_READ")


def main() -> int:
    _require_slurm()
    _require_signal_gate()
    if RUN_OUT.exists():
        raise RuntimeError(f"treatment attempt already exists; refusing to repeat calls: {RUN_OUT}")
    RUN_OUT.mkdir(mode=0o700, parents=True)
    if REUSE_DECISIONS_FROM:
        decision_root = OUT / REUSE_DECISIONS_FROM
        governors = decision_root / "governors"
        gates = decision_root / "gates"
        if not governors.is_dir() or not gates.is_dir():
            raise RuntimeError(f"frozen Jev decisions are missing from {decision_root}")
    else:
        governors = RUN_OUT / "governors"
        gates = RUN_OUT / "gates"
        governors.mkdir(mode=0o700)
        gates.mkdir(mode=0o700)

        # Amendment 07 and the observed 3/10 Luna signal authorize this Luna run;
        # the older Qwen mini-worker qualification applies to a separate protocol.
        source_governor._require_prequalification = lambda _plan: None

        def load_source_inputs(plan_path):
            loaded_plan, _, memories = pilot._load_frozen_pilot_with_documented_baseline(plan_path)
            return loaded_plan, memories

        source_governor.load_frozen_inputs = load_source_inputs
        exposure_gate.load_frozen_pilot = pilot._load_frozen_pilot_with_documented_baseline
        _invoke_module(source_governor.main, [
            "--plan", str(PLAN), "--governor", "jev", "--output-dir", str(governors),
        ])

        gate_status = _invoke_module(exposure_gate.main, [
            "--stage", "write-check", "--plan", str(PLAN),
            "--governor-dir", str(governors), "--output-dir", str(gates),
        ])
        if gate_status != 0:
            raise RuntimeError("Jev write exposure gate did not pass; treatment workers were not launched")

    exposure_gate.load_frozen_pilot = pilot._load_frozen_pilot_with_documented_baseline
    gate_args = Namespace(plan=PLAN, governor_dir=governors, output_dir=gates)
    gate_paths = exposure_gate._output_paths(gate_args)
    state = exposure_gate._load_jev_assignments(gate_args)
    write_gate = json.loads(gate_paths["write_gate"].read_text(encoding="utf-8"))
    write_data = exposure_gate._measure_write_exposure_gate(state)
    exposure_gate._validate_prior_write_gate(gate_args, gate_paths["write_gate"], state, write_data)
    if REUSE_DECISIONS_FROM:
        read_rows = _load_reused_read_decisions(state, governors)
    else:
        read_rows = exposure_gate._collect_jev_read_decisions(gate_args, state, gate_paths)
        exposure_gate._write_read_decisions(gate_args, gate_paths, read_rows)

    read_table = exposure_gate._read_decisions_by_target(read_rows)
    exposure_by_target: dict[str, dict[str, dict]] = {}
    for target_id in analysis_target_ids(state["plan"]):
        pool = state["pools"][target_id]
        candidate_ids = {row["memory"]["memory_id"] for row in pool["candidate_pool"]}
        target_exposures = {
            "B_SHARE_ALL": treatment_exposure(
                target=pool["target"], pool=pool, arm_id="B_SHARE_ALL", admitted_ids=candidate_ids,
            ),
            "C_RANDOM_MATCHED": treatment_exposure(
                target=pool["target"], pool=pool, arm_id="C_RANDOM_MATCHED",
                admitted_ids=state["random_admitted"],
            ),
            "D_JEV_WRITE": treatment_exposure(
                target=pool["target"], pool=pool, arm_id="D_JEV_WRITE",
                admitted_ids=state["jev_admitted"],
            ),
            "E_JEV_WRITE_READ": treatment_exposure(
                target=pool["target"], pool=pool, arm_id="E_JEV_WRITE_READ",
                admitted_ids=state["jev_admitted"],
                frozen_read_decisions=read_table.get(target_id, {}),
            ),
        }
        exposure_by_target[target_id] = target_exposures

    pilot._require_slurm()
    settings = load_worker_settings(pilot.DEFAULT_WORKER_CONFIG)
    if settings["requested_model"] != "gpt-6-luna" or settings["reasoning_effort"] != "xhigh":
        raise RuntimeError("Paper treatments require the frozen GPT-6 Luna xhigh worker config")
    plan, pools, _ = pilot._load_frozen_pilot_with_documented_baseline(PLAN)
    pilot._validate_controls(plan, PLAN)
    model_access = pilot._preflight_openai_model(settings["requested_model"])

    job_tmp = Path(os.environ["FMC_JOB_TMP"]).resolve(strict=True)
    args = Namespace(
        plan=PLAN,
        targets_parquet=Path(os.environ["FMC_TARGETS_PARQUET"]),
        contextbench_root=Path(os.environ["FMC_CONTEXTBENCH_ROOT"]),
        sif_dir=ROOT / "artifacts/burned-pilot/images",
        job_tmp=job_tmp,
        sweedit_root=Path(os.environ["FMC_SWEEDIT_ROOT"]),
        sweedit_env=Path(os.environ["FMC_SWEEDIT_ENV"]),
        python_prefix=Path(os.environ["FMC_PYTHON_PREFIX"]),
        worker_config=pilot.DEFAULT_WORKER_CONFIG,
        run_root=RUN_OUT / "workers",
        summary=RUN_OUT / "summary.json",
    )
    args.run_root.mkdir(mode=0o700)
    target_ids = analysis_target_ids(plan)
    evaluator = pilot.SWEContextBenchApptainerEvaluator(
        args.contextbench_root, args.targets_parquet, args.sif_dir, args.job_tmp,
    )
    evaluator_preflight = evaluator.preflight(target_ids)
    sif_preflight = pilot._preflight_sif_bases(args, pools, target_ids)

    exposure_path = RUN_OUT / "treatment_exposures.jsonl"
    records_path = RUN_OUT / "treatment_results.jsonl"
    records = []
    with exposure_path.open("x", encoding="utf-8") as exposure_file, records_path.open("x", encoding="utf-8") as results_file:
        for target_id in target_ids:
            pool = pools[target_id]
            target_rows = {}
            order = sorted(ARMS, key=lambda arm: hashlib.sha256(
                f"fleet-mem-contextbench-luna-paper:20261006:{target_id}:{arm}".encode()
            ).hexdigest())
            for arm_id in order:
                exposure = exposure_by_target[target_id][arm_id]
                exposure_record = {
                    "target_id": target_id,
                    "arm_id": arm_id,
                    "exposed_memory_ids": exposure["exposed_memory_ids"],
                    "retrieved_memory_ids": exposure["retrieved_memory_ids"],
                    "memory_tokens_exposed": exposure["memory_tokens_exposed"],
                    "memory_count_budget": exposure["memory_count_budget"],
                    "candidate_pool_size": exposure["candidate_pool_size"],
                }
                exposure_file.write(json.dumps(exposure_record, sort_keys=True) + "\n")
                result = pilot._run_arm(args, evaluator, pool, arm_id, exposure)
                record = {"target_id": target_id, "pair_order": order, **result}
                results_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                results_file.flush()
                os.fsync(results_file.fileno())
                target_rows[arm_id] = record
                print(json.dumps({
                    "target_id": target_id, "arm_id": arm_id,
                    "resolved": result["grade"].get("resolved"),
                    "patch_applied": result["grade"].get("patch_applied"),
                }), flush=True)
            records.append({"target_id": target_id, "pair_order": order, "arms": target_rows})

    result_count = sum(len(row["arms"]) for row in records)
    valid_count = sum(
        arm["grade"].get("canonical_grade_available") is True and arm["grade"].get("patch_applied") is True
        for row in records for arm in row["arms"].values()
    )
    summary = {
        "schema_version": 1,
        "status": "COMPLETE" if result_count == len(target_ids) * len(ARMS) and valid_count == result_count else "COMPLETE_WITH_INVALID_GRADES",
        "treatment_arms": list(ARMS),
        "target_ids": target_ids,
        "worker_model": settings["requested_model"],
        "reasoning_effort": settings["reasoning_effort"],
        "signal_gate": json.loads(SIGNAL.read_text(encoding="utf-8")),
        "signal_gate_sha256": sha256_file(SIGNAL),
        "baseline_summary": str(BASELINE.relative_to(ROOT)),
        "baseline_summary_sha256": sha256_file(BASELINE),
        "development_amendment": "PILOT_DEVELOPMENT_AMENDMENT_07",
        "qwen_qualification_gate_bypass": "Luna signal-pass treatment execution explicitly authorized by user; no Qwen runs included",
        "attempt": ATTEMPT_NAME,
        "prior_attempt": PRIOR_ATTEMPT,
        "decision_source_attempt": REUSE_DECISIONS_FROM or ATTEMPT_NAME,
        "resume_context": (
            f"Reusing completed Jev decisions from {REUSE_DECISIONS_FROM}; the prior attempt stopped before worker inference "
            "because its ContextBench checkout was dirty. No Jev calls are repeated."
            if REUSE_DECISIONS_FROM else (
                "Prior attempt stopped on candidate 1 before DNS resolution; user directed resume after DNS/HTTPS preflight passed. "
                "The failed journal is retained separately and no Jev response was received."
            )
            if PRIOR_ATTEMPT else None
        ),
        "jev_write_gate": write_gate,
        "jev_read_decision_count": len(read_rows),
        "model_access_preflight": model_access,
        "evaluator_preflight": evaluator_preflight,
        "sif_base_preflight": sif_preflight,
        "result_count": result_count,
        "canonical_valid_grade_count": valid_count,
        "treatment_exposures": str(exposure_path.relative_to(ROOT)),
        "treatment_results": str(records_path.relative_to(ROOT)),
        "records": records,
    }
    with args.summary.open("x", encoding="utf-8") as output:
        json.dump(summary, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    print(json.dumps({"status": summary["status"], "result_count": result_count, "valid_grades": valid_count}), flush=True)
    return 0 if summary["status"] == "COMPLETE" else 2


def _invoke_module(function, arguments: list[str]) -> int:
    previous = sys.argv
    try:
        sys.argv = ["treatment-stage", *arguments]
        return function()
    finally:
        sys.argv = previous


def _require_signal_gate() -> None:
    signal = json.loads(SIGNAL.read_text(encoding="utf-8"))
    if (
        signal.get("decision") != "ORACLE_SIGNAL_PRESENT"
        or signal.get("executable_discordant_targets", 0) < 2
        or signal.get("paired_target_count") != 10
        or signal.get("complete_paired_executable_grades") is not True
    ):
        raise RuntimeError("the frozen Luna signal gate is incomplete or did not pass")


def _load_reused_read_decisions(state: dict, governor_dir: Path) -> list[dict]:
    decisions_path = governor_dir / "jev_read_decisions.jsonl"
    summary_path = governor_dir / "jev_read_summary.json"
    journal_path = governor_dir / "jev_read_journal.jsonl"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if (
        summary.get("status") != "COMPLETE"
        or summary.get("plan_sha256") != sha256_file(PLAN)
        or summary.get("decisions_sha256") != sha256_file(decisions_path)
        or summary.get("journal_sha256") != sha256_file(journal_path)
    ):
        raise RuntimeError("reused Jev read decisions are incomplete or fail their recorded integrity checks")

    expected: dict[tuple[str, str], str] = {}
    for target_id in analysis_target_ids(state["plan"]):
        pool = state["pools"][target_id]
        for memory in exposure_gate._admitted_retrieval(pool, state["jev_admitted"]):
            source_input = {"target": pool["target"], "candidate": memory}
            input_hash = hashlib.sha256(exposure_gate._canonical(source_input).encode("utf-8")).hexdigest()
            expected[(target_id, memory["memory_id"])] = input_hash

    rows = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.get("target_id"), row.get("memory_id"))
        if key in seen or key not in expected or row.get("input_sha256") != expected[key]:
            raise RuntimeError("reused Jev read table does not match fixed retrieval inputs")
        decision = Decision(
            action=row.get("action"), confidence=row.get("confidence"),
            probabilities=row.get("probabilities"), rationale=row.get("rationale"),
            latency_ms=row.get("latency_ms"), cost=row.get("cost"),
            input_tokens=row.get("input_tokens"), output_tokens=row.get("output_tokens"),
        )
        decision.validate("read")
        seen.add(key)
    if seen != set(expected) or len(rows) != summary.get("decision_count"):
        raise RuntimeError("reused Jev read table has missing or extra decisions")
    return rows


def _require_slurm() -> None:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("paper treatments must run under Slurm")


if __name__ == "__main__":
    raise SystemExit(main())
