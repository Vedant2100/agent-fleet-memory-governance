#!/usr/bin/env python3
"""Qualify one local worker and run its Oracle signal test only after a pass."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MECHANICS_GATE_AMENDMENT = "PDA-05"
CONTEXTBENCH = Path("/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench")
TARGETS = Path("/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet")
SWEEDIT = Path("/home/csgrad/vbork001/benchmarks/SWE-Edit")
SWEEDIT_ENV = Path("/home/csgrad/vbork001/.venv-sweedit-run")
PYTHON_PREFIX = Path("/home/csgrad/vbork001/miniconda3")
SIF_DIR = ROOT / "artifacts/burned-pilot/images"
PLAN = ROOT / "artifacts/burned-pilot/plan.json"


def oracle_gate_passes(complete: bool, executable_discordant_targets: int) -> bool:
    return complete and executable_discordant_targets >= 2


def worker_mechanics_gate(summary: dict[str, Any]) -> dict[str, Any]:
    records = summary.get("records", [])
    usable = [
        row for row in records
        if row.get("worker", {}).get("patch_bytes", 0) > 0
        and row.get("worker", {}).get("valid_submission") is True
        and row.get("grade", {}).get("canonical_grade_available") is True
        and row.get("grade", {}).get("patch_applied") is True
    ]
    passed = len(records) == 3 and len(usable) >= 2
    return {
        "amendment": MECHANICS_GATE_AMENDMENT,
        "status": "PASS" if passed else "STOP_WORKER_MECHANICS_FAILED",
        "task_attempts": len(records),
        "mechanically_valid_applicable_grades": len(usable),
        "minimum_valid_applicable_grades": 2,
        "minimum_resolved_tasks": 0,
        "criteria": [
            "nonempty submitted patch",
            "valid upstream finish submission",
            "patch applies to the frozen target state",
            "canonical grade is available",
        ],
    }


def apply_worker_mechanics_gate(summary: dict[str, Any]) -> dict[str, Any]:
    summary["unamended_full_resolution_gate"] = {
        "status": summary.get("status"),
        "resolved_count": summary.get("resolved_count", 0),
        "minimum_resolved": 2,
        "rule": "three valid, nonempty, applicable, canonically graded runs and at least two resolved tasks",
    }
    gate = worker_mechanics_gate(summary)
    summary["worker_mechanics_gate"] = gate
    summary["status"] = gate["status"]
    return summary


def local_model_preflight(model: str) -> dict[str, Any]:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=20) as response:
        models = json.load(response).get("models", [])
    match = next((row for row in models if row.get("name") == model), None)
    if match is None:
        raise RuntimeError(f"local model is not loaded: {model}")
    with urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=20) as response:
        version = json.load(response).get("version")
    return {
        "endpoint": "http://127.0.0.1:11434/v1/responses",
        "provider": "local Ollama OpenAI-compatible Responses API",
        "ollama_version": version,
        "requested_model": model,
        "requested_model_available": True,
        "model_digest": match.get("digest"),
        "model_size_bytes": match.get("size"),
    }


def validate_qualification(args: argparse.Namespace, pilot: Any) -> None:
    record = json.loads(args.qualification_summary.read_text(encoding="utf-8"))
    settings = pilot.load_worker_settings(args.worker_config)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if record.get("status") != "PASS":
        raise RuntimeError("candidate worker qualification did not pass")
    gate = record.get("worker_mechanics_gate", {})
    if gate.get("amendment") != MECHANICS_GATE_AMENDMENT or gate.get("status") != "PASS":
        raise RuntimeError("candidate did not pass the frozen worker-mechanics amendment")
    if record.get("requested_model") != args.model or record.get("reasoning_effort") != "xhigh":
        raise RuntimeError("qualified model or reasoning setting changed")
    if record.get("target_ids") != plan["qualification"]["target_ids"]:
        raise RuntimeError("qualification target set differs from the frozen plan")
    expected = {
        "worker_config_sha256": settings["sha256"],
        "worker_adapter_sha256": pilot.sha256_file(ROOT / "src/fleet_mem_contextbench/sweedit_worker.py"),
        "bootstrap_sha256": pilot.sha256_file(ROOT / "scripts/sweedit_bootstrap.py"),
        "pilot_runner_sha256": pilot.sha256_file(ROOT / "scripts/run_sweedit_burned.py"),
        "slurm_wrapper_sha256": pilot.sha256_file(ROOT / "scripts/run_sweedit_pilot.sbatch"),
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise RuntimeError(f"qualification input changed: {key}")


def strict_signal_summary(original, args, model_access, evaluator_preflight, sif_preflight, target_ids, rows, seed):
    summary = original(args, model_access, evaluator_preflight, sif_preflight, target_ids, rows, seed)
    complete = summary.get("complete_paired_executable_grades") is True
    count = int(summary.get("executable_discordant_targets", 0))
    passed = oracle_gate_passes(complete, count)
    summary["status"] = "ORACLE_SIGNAL_PRESENT" if passed else (
        "STOP_NO_ORACLE_SIGNAL" if complete else "STOP_SIGNAL_TEST_INCOMPLETE"
    )
    summary["meaningful_oracle_signal"] = passed
    summary["oracle_go_no_go"] = {
        "minimum_executable_discordant_targets": 2,
        "observed_executable_discordant_targets": count,
        "complete_pairs_required": True,
        "behavioral_discordance_alone_counts": False,
        "passed": passed,
    }
    print(json.dumps({"status": summary["status"], "oracle_go_no_go": summary["oracle_go_no_go"]}, indent=2))
    return summary


def stage_argv(stage: str, args: argparse.Namespace, summary: Path, run_root: Path) -> list[str]:
    return [
        "run_sweedit_burned.py", "--stage", stage,
        "--plan", str(PLAN),
        "--targets-parquet", str(TARGETS),
        "--contextbench-root", str(CONTEXTBENCH),
        "--sif-dir", str(SIF_DIR),
        "--job-tmp", str(args.job_tmp),
        "--sweedit-root", str(SWEEDIT),
        "--sweedit-env", str(SWEEDIT_ENV),
        "--python-prefix", str(PYTHON_PREFIX),
        "--worker-config", str(args.worker_config),
        "--run-root", str(run_root),
        "--summary", str(summary),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--worker-config", type=Path, required=True)
    parser.add_argument("--qualification-summary", type=Path, required=True)
    parser.add_argument("--oracle-summary", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--job-tmp", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "artifacts/development"))
    sys.path.insert(0, str(CONTEXTBENCH))
    import run_sweedit_burned as pilot
    from swebench_memory.harness import run_evaluation
    from timeout_override import extend_sympy_test_timeout

    extend_sympy_test_timeout(run_evaluation, seconds=3600)
    pilot._preflight_openai_model = local_model_preflight
    model_access = local_model_preflight(args.model)
    settings = pilot.load_worker_settings(args.worker_config)
    if settings["requested_model"] != args.model or settings["reasoning_effort"] != "xhigh":
        raise RuntimeError("worker config does not match this frozen model candidate")

    sys.argv = stage_argv("qualify", args, args.qualification_summary, args.run_root / "qualification")
    pilot.main()
    qualification = json.loads(args.qualification_summary.read_text(encoding="utf-8"))
    qualification = apply_worker_mechanics_gate(qualification)
    args.qualification_summary.write_text(json.dumps(qualification, indent=2) + "\n", encoding="utf-8")
    if qualification["status"] != "PASS":
        print(json.dumps({"worker_mechanics_gate": qualification["worker_mechanics_gate"]}, indent=2))
        return 2
    validate_qualification(args, pilot)

    def validate_frozen_qualification() -> None:
        validate_qualification(args, pilot)

    pilot._validate_qualification_freeze = validate_frozen_qualification
    original_summary = pilot._signal_summary

    def summarize_oracle_signal(*values):
        return strict_signal_summary(original_summary, *values)

    pilot._signal_summary = summarize_oracle_signal
    sys.argv = stage_argv("signal", args, args.oracle_summary, args.run_root / "oracle")
    return pilot.main()


if __name__ == "__main__":
    raise SystemExit(main())
