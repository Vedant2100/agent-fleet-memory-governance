#!/usr/bin/env python3
"""Qualify the frozen worker on three preregistered No-Memory targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_mem_contextbench.apptainer_evaluator import SWEContextBenchApptainerEvaluator
from fleet_mem_contextbench.pilot_runtime import analysis_target_ids, load_frozen_pilot, sha256_file
from fleet_mem_contextbench.worker import WORKER_MODEL, preflight_ollama, solve_with_mini_swe_agent


def ollama_preflight(base_url: str) -> dict[str, Any]:
    return preflight_ollama(base_url, WORKER_MODEL)


def main() -> int:
    args = _parse_args()
    if args.summary.exists():
        raise RuntimeError(f"qualification summary already exists; refusing duplicate runs: {args.summary}")
    state = _prepare_qualification(args)
    records = _run_qualification_tasks(args, state)
    summary = _qualification_summary(args, state, records)
    _write_summary(args.summary, summary)
    print(json.dumps({
        "status": summary["status"],
        "nonempty_patches": summary["nonempty_patch_count"],
        "resolved": summary["resolved_count"],
    }, indent=2))
    return 0 if summary["status"] == "PASS" else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "artifacts/burned-pilot/plan.json")
    parser.add_argument("--targets-parquet", type=Path, required=True)
    parser.add_argument("--contextbench-root", type=Path, required=True)
    parser.add_argument("--sif-dir", type=Path, default=ROOT / "artifacts/burned-pilot/images")
    parser.add_argument("--job-tmp", type=Path, required=True)
    parser.add_argument("--mini-bin", type=Path, required=True)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--run-root", type=Path, default=ROOT / "results/burned-pilot/qualification")
    parser.add_argument("--summary", type=Path, default=ROOT / "artifacts/burned-pilot/qualification.json")
    return parser.parse_args()


def _prepare_qualification(args: argparse.Namespace) -> dict[str, Any]:
    if not os.environ.get("SLURM_JOB_ID") or os.environ.get("OLLAMA_NO_CLOUD") != "1":
        raise RuntimeError("worker qualification must run in Slurm with OLLAMA_NO_CLOUD=1")
    plan, pools, _ = load_frozen_pilot(args.plan)
    _validate_worker_freeze(plan)
    mini_preflight = _mini_python_preflight(args.mini_bin)
    evaluator = SWEContextBenchApptainerEvaluator(
        args.contextbench_root, args.targets_parquet, args.sif_dir, args.job_tmp,
    )
    grader_preflight = evaluator.preflight(plan["qualification"]["target_ids"])
    worker_preflight = ollama_preflight(args.ollama_base_url)
    controls = _validate_controls(args.plan)
    args.run_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    return {
        "plan": plan, "pools": pools, "evaluator": evaluator,
        "grader_preflight": grader_preflight, "worker_preflight": worker_preflight,
        "mini_preflight": mini_preflight, "controls": controls,
    }


def _mini_python_preflight(mini_bin: Path) -> dict[str, Any]:
    python = os.environ.get("FMC_MINI_PYTHON")
    if not python or not Path(python).is_file():
        raise RuntimeError("FMC_MINI_PYTHON must identify the pinned mini-SWE-agent interpreter")
    wrapper = mini_bin.resolve(strict=True)
    if not os.access(wrapper, os.X_OK):
        raise RuntimeError(f"mini-SWE-agent wrapper is not executable: {wrapper}")
    probe = r'''
import importlib.metadata as metadata
import importlib.util
import json
import sys

distribution = metadata.distribution("mini-swe-agent")
spec = importlib.util.find_spec("minisweagent")
print(json.dumps({
    "executable": sys.executable,
    "prefix": sys.prefix,
    "mini_swe_agent_version": distribution.version,
    "litellm_version": metadata.version("litellm"),
    "module_origin": spec.origin if spec else None,
    "mini_entry_points": [
        {"name": point.name, "value": point.value}
        for point in distribution.entry_points if point.name == "mini"
    ],
}))
'''
    try:
        result = subprocess.run(
            [python, "-c", probe], capture_output=True, text=True, timeout=30, check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"mini-SWE-agent interpreter preflight failed: {exc.stderr[-2000:]}") from exc
    observed = json.loads(result.stdout)
    prefix = Path(observed["prefix"]).resolve()
    module_origin = Path(observed["module_origin"]).resolve()
    expected_entry = {"name": "mini", "value": "minisweagent.run.mini:app"}
    if (
        observed["mini_swe_agent_version"] != "2.4.6"
        or observed["litellm_version"] != "1.102.1"
        or not module_origin.is_relative_to(prefix)
        or expected_entry not in observed["mini_entry_points"]
        or "shared-mem-gov-pilot" in " ".join((python, str(prefix), str(module_origin))).casefold()
    ):
        raise RuntimeError(f"mini-SWE-agent runtime does not match the standalone frozen worker: {observed}")
    return {**observed, "wrapper": str(wrapper), "wrapper_sha256": sha256_file(wrapper)}


def _validate_worker_freeze(plan: dict[str, Any]) -> None:
    frozen = plan["qualification"]["worker"]
    current = {
        "worker_config_sha256": sha256_file(ROOT / "configs/worker.yaml"),
        "worker_adapter_sha256": sha256_file(ROOT / "src/fleet_mem_contextbench/worker.py"),
    }
    if any(current[key] != frozen[key] for key in current):
        raise RuntimeError("frozen worker config/adapter hash changed")


def _validate_controls(plan_path: Path) -> dict[str, Any]:
    path = ROOT / "artifacts/burned-pilot/controls_summary.json"
    controls = json.loads(path.read_text(encoding="utf-8"))
    primary_ids = analysis_target_ids(json.loads(plan_path.read_text(encoding="utf-8")))
    valid = (
        controls.get("plan_sha256") == sha256_file(plan_path)
        and controls.get("all_controls_passed") is True
        and controls.get("target_count") == len(primary_ids)
        and controls.get("control_count") == 2 * len(primary_ids)
        and controls.get("target_ids") == primary_ids
    )
    if not valid:
        raise RuntimeError("canonical no-op/reference evaluator controls did not pass for every primary target")
    expected_ids = set(primary_ids)
    covered = {row.get("target_id") for row in controls.get("rows", [])}
    if covered != expected_ids:
        raise RuntimeError("canonical controls do not cover the amended primary target set")
    return controls


def _run_qualification_tasks(args: argparse.Namespace, state: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for target_id in state["plan"]["qualification"]["target_ids"]:
        records.append(_run_qualification_target(args, state, target_id))
    return records


def _run_qualification_target(
    args: argparse.Namespace, state: dict[str, Any], target_id: str,
) -> dict[str, Any]:
    target = state["pools"][target_id]["target"]
    run_dir = args.run_root / target_id
    worker = solve_with_mini_swe_agent(
        target, [], sif_path=args.sif_dir / f"{target_id}.sif", output_dir=run_dir / "worker",
        repo_root=ROOT, worker_config=ROOT / "configs/worker.yaml", mini_bin=args.mini_bin,
        ollama_base_url=args.ollama_base_url,
    )
    grade = _grade_qualification_target(state["evaluator"], target_id, worker, run_dir)
    row = {
        "target_id": target_id, "arm_id": "QUALIFICATION_NO_MEMORY",
        "exposed_memory_ids": [], "memory_count": 0, "worker": worker,
        "grade": _grade_summary(grade),
        "canonical_result_sha256": _result_hash(run_dir),
    }
    print(json.dumps({"target_id": target_id, "patch_bytes": worker["patch_bytes"], "resolved": grade.get("resolved")}))
    return row


def _grade_qualification_target(evaluator, target_id: str, worker: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    if not worker["patch_bytes"]:
        return {
            "target_id": target_id, "canonical_grade_available": False,
            "resolved": None,
            "reason": "worker did not submit a nonempty patch; no synthetic patch was graded",
        }
    patch = Path(worker["patch_path"]).read_text(encoding="utf-8")
    return evaluator.evaluate(
        target_id, patch, run_id=f"burned-qualification-{target_id}",
        output_dir=run_dir / "evaluation",
    )


def _result_hash(run_dir: Path) -> str | None:
    path = run_dir / "evaluation/canonical_result.json"
    return sha256_file(path) if path.is_file() else None


def _qualification_summary(
    args: argparse.Namespace, state: dict[str, Any], records: list[dict[str, Any]],
) -> dict[str, Any]:
    resolved = sum(row["grade"].get("resolved") is True for row in records)
    nonempty = sum(row["worker"].get("patch_bytes", 0) > 0 for row in records)
    passed = nonempty == 3 and resolved >= 2
    return {
        "schema_version": 1, "stage": "BURNED_WORKER_QUALIFICATION",
        "status": "PASS" if passed else "STOP_WORKER_QUALIFICATION_FAILED",
        "plan_sha256": sha256_file(args.plan),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "worker_preflight": state["worker_preflight"],
        "mini_python_preflight": state["mini_preflight"],
        "grader_preflight": state["grader_preflight"],
        "evaluator_controls_sha256": sha256_file(ROOT / "artifacts/burned-pilot/controls_summary.json"),
        "nonempty_patch_count": nonempty, "resolved_count": resolved,
        "records": records,
    }


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

def _grade_summary(grade: dict[str, Any]) -> dict[str, Any]:
    return {
        key: grade.get(key) for key in (
            "canonical_grade_available", "resolved", "fail_to_pass_passed", "fail_to_pass_total",
            "pass_to_pass_passed", "pass_to_pass_total", "latency_seconds",
        )
    } | ({"reason": grade["reason"]} if grade.get("reason") else {})


if __name__ == "__main__":
    raise SystemExit(main())
