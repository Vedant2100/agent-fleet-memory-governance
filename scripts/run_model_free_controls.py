#!/usr/bin/env python3
"""Run official no-patch/reference-patch grader controls for frozen smoke targets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fleet_mem_contextbench.data import load_parquet_tasks
from fleet_mem_contextbench.paired import SWEContextBenchOfficialEvaluator


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run model-free canonical grader controls.")
    parser.add_argument("--release", default="artifacts/smoke")
    parser.add_argument("--targets-parquet", required=True)
    parser.add_argument("--contextbench-root", required=True)
    parser.add_argument("--target-id", help="Defaults to the first frozen smoke target.")
    parser.add_argument("--output", default="results/controls")
    args = parser.parse_args()

    release = Path(args.release)
    manifest = read_jsonl(release / "manifests/benchmark_manifest.jsonl")
    selected = args.target_id or (manifest[0]["target_id"] if manifest else None)
    if selected is None or selected not in {row["target_id"] for row in manifest}:
        raise SystemExit(f"target ID is not in frozen smoke manifest: {selected}")
    targets = {task.task_id: task for task in load_parquet_tasks(args.targets_parquet)}
    target = targets.get(selected)
    if target is None:
        raise SystemExit(f"target is missing from supplied SWE-ContextBench target parquet: {selected}")

    evaluator = SWEContextBenchOfficialEvaluator(args.contextbench_root)
    evaluator.preflight()
    output = Path(args.output)
    rows = []
    patches = {"NO_PATCH": "", "REFERENCE_PATCH": target.patch}
    for control, patch in patches.items():
        control_dir = output / selected / control
        predictions_dir = control_dir / "predictions"
        predictions_dir.mkdir(parents=True, exist_ok=True)
        (predictions_dir / f"{selected}_preds.json").write_text(json.dumps({
            selected: {
                "model_name_or_path": f"model_free_{control.lower()}",
                "instance_id": selected, "model_patch": patch,
            }
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        grade = evaluator.evaluate(selected, predictions_dir, f"control-{control.lower()}")
        rows.append({
            "target_id": selected, "control": control,
            "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            "grade": grade,
        })
    output.mkdir(parents=True, exist_ok=True)
    (output / "controls.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
