#!/usr/bin/env python3
"""Run canonical semantic-no-op and reference-patch controls on all frozen targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_mem_contextbench.apptainer_evaluator import (
    SWEContextBenchApptainerEvaluator, semantic_noop_patch,
)
from fleet_mem_contextbench.pilot_runtime import analysis_target_ids, load_frozen_pilot


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default="artifacts/burned-pilot/plan.json")
    parser.add_argument("--targets-parquet", required=True)
    parser.add_argument("--contextbench-root", required=True)
    parser.add_argument("--sif-dir", default="artifacts/burned-pilot/images")
    parser.add_argument("--job-tmp", required=True)
    parser.add_argument("--output", default="results/burned-pilot/controls")
    parser.add_argument("--summary", default="artifacts/burned-pilot/controls_summary.json")
    parser.add_argument("--target-ids", nargs="+", help="Explicit frozen target subset for a separately recorded control batch")
    args = parser.parse_args()
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Canonical controls must run in the configured Slurm Apptainer allocation")

    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:
        raise SystemExit("pyarrow is required for frozen ContextBench controls") from exc

    plan_path = Path(args.plan)
    summary_path = Path(args.summary)
    output = Path(args.output)
    if summary_path.exists() or (output / "controls.json").exists():
        raise RuntimeError("canonical control artifacts already exist; refusing to overwrite or repeat them")
    plan, pools, _ = load_frozen_pilot(plan_path)
    primary_ids = analysis_target_ids(plan)
    target_ids = args.target_ids or primary_ids
    if len(target_ids) != len(set(target_ids)) or not set(target_ids).issubset(primary_ids):
        raise RuntimeError("control batch IDs must be a unique subset of the frozen primary targets")
    evaluator = SWEContextBenchApptainerEvaluator(
        args.contextbench_root, args.targets_parquet, args.sif_dir, args.job_tmp,
    )
    preflight = evaluator.preflight(target_ids)
    table = parquet.read_table(args.targets_parquet, columns=["instance_id", "patch"])
    reference_patches = {row["instance_id"]: row["patch"] for row in table.to_pylist()}
    output.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for target_id in target_ids:
        reference_patch = reference_patches.get(target_id)
        if not isinstance(reference_patch, str) or not reference_patch.strip():
            raise RuntimeError(f"missing hidden reference patch for frozen target {target_id}")
        controls = (
            ("NO_PATCH_SEMANTIC_NOOP", semantic_noop_patch()),
            ("REFERENCE_PATCH", reference_patch),
        )
        target_rows = []
        for control_id, patch in controls:
            result = evaluator.evaluate(
                target_id=target_id,
                model_patch=patch,
                run_id=f"burned-control-{target_id}-{control_id.lower()}",
                output_dir=output / target_id / control_id,
            )
            row = {
                "target_id": target_id,
                "control_id": control_id,
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
                "result": result,
            }
            target_rows.append(row)
            all_rows.append(row)
        noop, reference = target_rows
        if not noop["result"]["canonical_grade_available"] or noop["result"]["resolved"]:
            raise RuntimeError(f"semantic no-op control failed for {target_id}; inspect saved canonical logs")
        if not reference["result"]["canonical_grade_available"] or not reference["result"]["resolved"]:
            raise RuntimeError(f"reference-patch control failed for {target_id}; inspect saved canonical logs")
        print(json.dumps({
            "target_id": target_id,
            "no_patch_resolved": noop["result"]["resolved"],
            "reference_resolved": reference["result"]["resolved"],
        }, sort_keys=True))

    full_log = {
        "plan_sha256": sha256(plan_path),
        "preflight": preflight,
        "target_ids": target_ids,
        "target_count": len(target_ids),
        "control_count": len(all_rows),
        "all_controls_passed": True,
        "rows": all_rows,
    }
    full_log_path = output / "controls.json"
    full_log_path.write_text(json.dumps(full_log, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit = {
        "schema_version": 1,
        "status": "PASS",
        "plan_sha256": sha256(plan_path),
        "control_count": len(all_rows),
        "target_ids": target_ids,
        "target_count": len(target_ids),
        "all_controls_passed": True,
        "preflight": preflight,
        "full_log_path": str(full_log_path),
        "full_log_sha256": sha256(full_log_path),
        "rows": [
            {
                "target_id": row["target_id"],
                "control_id": row["control_id"],
                "patch_sha256": row["patch_sha256"],
                "canonical_result_path": row["result"].get("canonical_result_path"),
                "canonical_result_sha256": sha256(
                    Path(row["result"]["canonical_result_path"])
                ) if row["result"].get("canonical_result_path") else None,
                "canonical_grade_available": row["result"]["canonical_grade_available"],
                "resolved": row["result"]["resolved"],
            }
            for row in all_rows
        ],
    }
    audit_path = summary_path
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "target_count": len(target_ids), "full_log": str(full_log_path), "audit_summary": str(audit_path), "controls": len(all_rows)}, indent=2))


if __name__ == "__main__":
    main()
