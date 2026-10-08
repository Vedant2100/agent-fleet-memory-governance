#!/usr/bin/env python3
"""Assemble the ten-target primary control table from completed canonical runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleet_mem_contextbench.pilot_runtime import analysis_target_ids, load_frozen_pilot, sha256_file


INITIAL_CORRECTED_TARGETS = [
    "sympy__sympy-19235", "sympy__sympy-21203", "django__django-35356",
    "sympy__sympy-16342", "sympy__sympy-16946",
]
CONTROL_IDS = ("NO_PATCH_SEMANTIC_NOOP", "REFERENCE_PATCH")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "artifacts/burned-pilot/plan.json")
    parser.add_argument("--remaining-summary", type=Path, required=True)
    parser.add_argument("--corrected-root", type=Path, default=ROOT / "results/burned-pilot/controls")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/burned-pilot/controls_summary.json")
    parser.add_argument("--replace-rebound-summary", action="store_true")
    args = parser.parse_args()

    plan, _, _ = load_frozen_pilot(args.plan)
    primary_ids = analysis_target_ids(plan)
    replaced_summary_sha256 = None
    prior_summary = None
    if args.output.exists():
        prior = plan.get("prior_control_evidence", {})
        actual_sha256 = sha256_file(args.output)
        if not args.replace_rebound_summary or actual_sha256 != prior.get("artifact_sha256"):
            raise RuntimeError(f"control summary already exists and is not the frozen prior artifact: {args.output}")
        replaced_summary_sha256 = actual_sha256
        prior_summary = json.loads(args.output.read_text(encoding="utf-8"))
    if primary_ids[:5] != INITIAL_CORRECTED_TARGETS:
        raise RuntimeError("the corrected initial control batch no longer matches the frozen primary order")

    remaining = json.loads(args.remaining_summary.read_text(encoding="utf-8"))
    expected_remaining = primary_ids[5:]
    accepted_source_plans = {
        sha256_file(args.plan),
        plan.get("prior_control_evidence", {}).get("source_plan_sha256"),
    }
    if prior_summary:
        remaining_sha256 = sha256_file(args.remaining_summary)
        remaining_path = args.remaining_summary.resolve()
        for batch in prior_summary.get("batches", []):
            batch_path = batch.get("summary_path")
            if (
                batch.get("targets") == expected_remaining
                and batch_path
                and (ROOT / batch_path).resolve() == remaining_path
                and batch.get("summary_sha256") == remaining_sha256
                and batch.get("source_plan_sha256") == remaining.get("plan_sha256")
            ):
                accepted_source_plans.add(batch["source_plan_sha256"])
    if (
        remaining.get("status") != "PASS"
        or remaining.get("plan_sha256") not in accepted_source_plans
        or remaining.get("target_ids") != expected_remaining
        or remaining.get("control_count") != 2 * len(expected_remaining)
    ):
        raise RuntimeError("remaining-target control batch is incomplete or bound to a different frozen pilot")

    rows: list[dict[str, Any]] = []
    for target_id in INITIAL_CORRECTED_TARGETS:
        for control_id in CONTROL_IDS:
            path = args.corrected_root / target_id / control_id / "canonical_result.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            rows.append(_row(target_id, control_id, path, result))
    remaining_log_path = Path(remaining["full_log_path"])
    if not remaining_log_path.is_absolute():
        remaining_log_path = ROOT / remaining_log_path
    remaining_log = json.loads(remaining_log_path.read_text(encoding="utf-8"))
    for row in remaining_log.get("rows", []):
        result = row["result"]
        path = Path(result["canonical_result_path"])
        if not path.is_absolute():
            path = ROOT / path
        rows.append(_row(row["target_id"], row["control_id"], path, result))

    expected_pairs = {(target, control) for target in primary_ids for control in CONTROL_IDS}
    actual_pairs = {(row["target_id"], row["control_id"]) for row in rows}
    if len(rows) != 20 or actual_pairs != expected_pairs:
        raise RuntimeError("assembled control table has missing, duplicate, or out-of-scope target-control rows")
    rows.sort(key=lambda row: (primary_ids.index(row["target_id"]), CONTROL_IDS.index(row["control_id"])))
    for row in rows:
        passing = row["canonical_grade_available"] and (
            row["resolved"] is False if row["control_id"] == "NO_PATCH_SEMANTIC_NOOP"
            else row["resolved"] is True
        )
        if not passing:
            raise RuntimeError(f"primary evaluator control failed for {row['target_id']}/{row['control_id']}")

    prior_control_gate = json.loads((ROOT / "artifacts/burned-pilot/control_gate.json").read_text(encoding="utf-8"))
    output = {
        "schema_version": 2,
        "status": "PASS",
        "plan_sha256": sha256_file(args.plan),
        "target_ids": primary_ids,
        "target_count": len(primary_ids),
        "control_count": len(rows),
        "all_controls_passed": True,
        "control_definition": "semantic no-op unresolved; canonical reference patch resolved",
        "replaced_rebound_summary_sha256": replaced_summary_sha256,
        "batches": [
            {"targets": INITIAL_CORRECTED_TARGETS, "job_id": "289186",
             "source_plan_sha256": prior_control_gate["pilot_plan"]["sha256"],
             "source": "corrected initial canonical control outputs"},
            {"targets": expected_remaining, "summary_path": str(args.remaining_summary),
             "summary_sha256": sha256_file(args.remaining_summary),
             "source_plan_sha256": remaining["plan_sha256"]},
        ],
        "excluded_audit_target": {
            "target_id": "matplotlib__matplotlib-22482",
            "reason": "SEMANTIC_NOOP_RESOLVED_PRETREATMENT",
            "control_gate_path": "artifacts/burned-pilot/control_gate.json",
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "targets": len(primary_ids), "controls": len(rows),
                      "output": str(args.output), "sha256": sha256_file(args.output)}, indent=2))


def _row(target_id: str, control_id: str, path: Path, result: dict[str, Any]) -> dict[str, Any]:
    path = path.resolve(strict=True)
    if result.get("target_id") != target_id or result.get("evaluator") != "pinned SWE-ContextBench evaluate_instance":
        raise RuntimeError(f"canonical result identity/evaluator mismatch at {path}")
    if result.get("canonical_grade_available") is not True or result.get("resolved") not in (True, False):
        raise RuntimeError(f"canonical grade unavailable at {path}")
    return {
        "target_id": target_id,
        "control_id": control_id,
        "patch_sha256": result.get("model_patch_sha256"),
        "canonical_result_path": path.relative_to(ROOT).as_posix(),
        "canonical_result_sha256": sha256_file(path),
        "canonical_grade_available": result["canonical_grade_available"],
        "resolved": result["resolved"],
        "fail_to_pass_passed": result.get("fail_to_pass_passed"),
        "fail_to_pass_total": result.get("fail_to_pass_total"),
        "pass_to_pass_passed": result.get("pass_to_pass_passed"),
        "pass_to_pass_total": result.get("pass_to_pass_total"),
        "latency_seconds": result.get("latency_seconds"),
    }


if __name__ == "__main__":
    main()
