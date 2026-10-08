#!/usr/bin/env python3
"""Regrade saved Luna 289648 patches after dropping test-path file diffs.

Raw signal-run patches and canonical results are read-only inputs. Filtered
patches, evaluator outputs, and provenance are written to a separate directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, "/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench-luna-regrade-clean2")
sys.path.insert(0, str(ROOT / "artifacts/development"))

from swebench_memory.harness import run_evaluation

from fleet_mem_contextbench.apptainer_evaluator import SWEContextBenchApptainerEvaluator
from fleet_mem_contextbench.pilot_runtime import sha256_file
from fleet_mem_contextbench.working_tree import is_test_path
from timeout_override import extend_sympy_test_timeout


SUMMARY_PATH = ROOT / "artifacts/development/luna_oracle_signal_289648.json"
CONTEXTBENCH_ROOT = Path("/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench-luna-regrade-clean2")
TARGETS_PARQUET = Path("/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet")
SIF_DIR = ROOT / "artifacts/burned-pilot/images"
OUTPUT_ROOT = ROOT / "results/development/oracle-signal-luna-289648-test-filtered-regrade"

TARGETS_AND_ARMS = (
    ("scikit-learn__scikit-learn-13771", "A_NO_MEMORY"),
    ("scikit-learn__scikit-learn-13771", "F_ORACLE_RELATED_CEILING"),
    ("sympy__sympy-16342", "A_NO_MEMORY"),
    ("sympy__sympy-16342", "F_ORACLE_RELATED_CEILING"),
    ("sympy__sympy-19235", "A_NO_MEMORY"),
    ("sympy__sympy-19235", "F_ORACLE_RELATED_CEILING"),
    ("sympy__sympy-21203", "A_NO_MEMORY"),
    ("sympy__sympy-21203", "F_ORACLE_RELATED_CEILING"),
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _summary_records() -> dict[str, dict[str, Any]]:
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    if summary.get("stage") != "BURNED_NO_MEMORY_VS_ORACLE_SIGNAL_TEST":
        raise RuntimeError("input summary is not the frozen Luna signal run")
    if set(summary.get("target_ids", [])) != {row["target_id"] for row in summary.get("records", [])}:
        raise RuntimeError("signal summary target list and records differ")
    return {row["target_id"]: row for row in summary["records"]}


def _paths_from_diff_header(section: str) -> tuple[str, str]:
    first_line = section.splitlines()[0] if section.splitlines() else ""
    match = re.fullmatch(r"diff --git a/(.+) b/(.+)", first_line)
    if not match:
        raise ValueError(f"unsupported diff header: {first_line!r}")
    return match.group(1), match.group(2)


def filter_patch(patch: str) -> tuple[str, list[str], list[str]]:
    """Drop complete file sections whose repository paths are test paths."""
    sections = re.split(r"(?=^diff --git )", patch, flags=re.MULTILINE)
    if not sections or any(section.strip() and not section.startswith("diff --git ") for section in sections):
        raise ValueError("patch contains unexpected content outside diff sections")
    kept: list[str] = []
    kept_paths: list[str] = []
    excluded_paths: list[str] = []
    for section in sections:
        if not section:
            continue
        old_path, new_path = _paths_from_diff_header(section)
        if is_test_path(old_path) or is_test_path(new_path):
            excluded_paths.append(new_path)
        else:
            kept.append(section)
            kept_paths.append(new_path)
    sanitized = "".join(kept)
    if not sanitized.strip():
        raise ValueError("test-path filtering removed the entire worker patch")
    if any(is_test_path(path) for path in kept_paths):
        raise AssertionError("test path survived filtering")
    return sanitized, kept_paths, excluded_paths


def _prepare() -> None:
    if OUTPUT_ROOT.exists():
        raise FileExistsError(f"refusing to overwrite regrade output: {OUTPUT_ROOT}")
    records = _summary_records()
    manifest_tasks: list[dict[str, Any]] = []
    for index, (target_id, arm_id) in enumerate(TARGETS_AND_ARMS):
        row = records.get(target_id)
        if row is None:
            raise KeyError(f"target missing from frozen summary: {target_id}")
        arm = row["no_memory"] if arm_id == "A_NO_MEMORY" else row["oracle_related"]
        worker = arm["worker"]
        source_path = Path(worker["patch_path"]).resolve(strict=True)
        source_bytes = source_path.read_bytes()
        source_hash = _sha256(source_bytes)
        if source_hash != worker.get("patch_sha256") or source_hash != worker.get("authoritative_diff_sha256"):
            raise RuntimeError(f"saved worker patch hash mismatch: {source_path}")
        sanitized, kept_paths, excluded_paths = filter_patch(source_bytes.decode("utf-8"))
        sanitized_bytes = sanitized.encode("utf-8")
        task_dir = OUTPUT_ROOT / target_id / arm_id
        task_dir.mkdir(parents=True, mode=0o700)
        sanitized_path = task_dir / "sanitized.patch"
        sanitized_path.write_bytes(sanitized_bytes)
        metadata = {
            "schema_version": 1,
            "run_id": 289648,
            "target_id": target_id,
            "arm_id": arm_id,
            "source_patch_path": str(source_path),
            "source_patch_sha256": source_hash,
            "source_patch_bytes": len(source_bytes),
            "sanitized_patch_path": str(sanitized_path),
            "sanitized_patch_sha256": _sha256(sanitized_bytes),
            "sanitized_patch_bytes": len(sanitized_bytes),
            "included_paths": kept_paths,
            "excluded_test_paths": excluded_paths,
            "filter_rule": "directory component test/tests or basename test_*.py",
            "evaluator_commit": "12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b",
            "collector_source_sha256": sha256_file(ROOT / "src/fleet_mem_contextbench/working_tree.py"),
        }
        metadata_path = task_dir / "filter_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_tasks.append({"task_index": index, **metadata})
        print(json.dumps({
            "task_index": index,
            "target_id": target_id,
            "arm_id": arm_id,
            "included_paths": kept_paths,
            "excluded_test_paths": excluded_paths,
            "sanitized_patch_bytes": len(sanitized_bytes),
        }, sort_keys=True), flush=True)

    manifest = {
        "schema_version": 1,
        "raw_run_id": 289648,
        "raw_summary_path": str(SUMMARY_PATH),
        "raw_summary_sha256": sha256_file(SUMMARY_PATH),
        "evaluator_commit": "12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b",
        "timeout_seconds": {"sympy": 1800, "other": 600},
        "tasks": manifest_tasks,
    }
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )


def _run_one(task_index: int) -> None:
    manifest_path = OUTPUT_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    task = manifest["tasks"][task_index]
    if task.get("task_index") != task_index:
        raise RuntimeError("manifest task order is inconsistent")
    patch_path = Path(task["sanitized_patch_path"]).resolve(strict=True)
    patch_bytes = patch_path.read_bytes()
    if _sha256(patch_bytes) != task["sanitized_patch_sha256"]:
        raise RuntimeError(f"sanitized patch hash mismatch: {patch_path}")
    source_path = Path(task["source_patch_path"]).resolve(strict=True)
    if sha256_file(source_path) != task["source_patch_sha256"]:
        raise RuntimeError(f"raw signal-run patch changed: {source_path}")
    if not os.environ.get("SLURM_JOB_ID") or not os.environ.get("SLURM_ARRAY_TASK_ID"):
        raise RuntimeError("regrade must run as an indexed Slurm job")
    job_tmp_base = Path(os.environ.get("SLURM_TMPDIR", "/tmp")).resolve(strict=True)
    if ROOT == job_tmp_base or ROOT in job_tmp_base.parents:
        raise RuntimeError("Apptainer scratch must be outside the project filesystem")
    job_tmp = job_tmp_base / f"fmc-luna-filtered-regrade-{os.environ['SLURM_JOB_ID']}-{task_index}"
    job_tmp.mkdir(mode=0o700, parents=True, exist_ok=False)
    run_tmp = job_tmp / "apptainer-cache"
    xdg_tmp = job_tmp / "xdg-cache"
    run_tmp.mkdir(mode=0o700)
    xdg_tmp.mkdir(mode=0o700)
    os.environ["TMPDIR"] = str(job_tmp)
    os.environ["APPTAINER_TMPDIR"] = str(job_tmp)
    os.environ["APPTAINER_CACHEDIR"] = str(run_tmp)
    os.environ["XDG_CACHE_HOME"] = str(xdg_tmp)

    target_id = task["target_id"]
    extend_sympy_test_timeout(run_evaluation, seconds=1800)
    evaluator = SWEContextBenchApptainerEvaluator(
        CONTEXTBENCH_ROOT,
        TARGETS_PARQUET,
        SIF_DIR,
        job_tmp / "evaluator-work",
    )
    preflight = evaluator.preflight([target_id])
    task_dir = OUTPUT_ROOT / target_id / task["arm_id"]
    evaluation_dir = task_dir / "evaluation"
    if evaluation_dir.exists():
        raise FileExistsError(f"refusing to overwrite evaluator output: {evaluation_dir}")
    result = evaluator.evaluate(
        target_id,
        patch_bytes.decode("utf-8"),
        run_id=f"luna-289648-filtered-{os.environ['SLURM_JOB_ID']}-{task_index}",
        output_dir=evaluation_dir,
    )
    metadata_path = task_dir / "filter_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update({
        "slurm_job_id": os.environ["SLURM_JOB_ID"],
        "slurm_array_task_id": task_index,
        "evaluator_preflight": preflight,
        "canonical_result_path": result.get("canonical_result_path"),
        "canonical_result_sha256": result.get("canonical_result_sha256"),
        "grade": {key: result.get(key) for key in (
            "canonical_grade_available", "patch_applied", "resolved",
            "fail_to_pass_passed", "fail_to_pass_total",
            "pass_to_pass_passed", "pass_to_pass_total", "latency_seconds",
        )},
    })
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "task_index": task_index,
        "target_id": target_id,
        "arm_id": task["arm_id"],
        **metadata["grade"],
        "canonical_result_path": metadata["canonical_result_path"],
    }, sort_keys=True), flush=True)
    if result.get("canonical_grade_available") is not True or result.get("patch_applied") is not True:
        raise RuntimeError(f"filtered regrade did not produce an applied canonical grade for {target_id}/{task['arm_id']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--task-index", type=int)
    args = parser.parse_args()
    if args.prepare == (args.task_index is not None):
        parser.error("choose exactly one of --prepare or --task-index")
    if args.prepare:
        _prepare()
    else:
        _run_one(args.task_index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
