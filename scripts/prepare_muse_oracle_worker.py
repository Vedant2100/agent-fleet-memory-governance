#!/usr/bin/env python3
"""Validate the frozen local-worker qualification and materialize its config."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


HASHED_INPUTS = {
    "worker_adapter_sha256": "src/fleet_mem_contextbench/sweedit_worker.py",
    "bootstrap_sha256": "scripts/sweedit_bootstrap.py",
    "pilot_runner_sha256": "scripts/run_sweedit_burned.py",
    "slurm_wrapper_sha256": "scripts/run_sweedit_pilot.sbatch",
}


def prepare_worker(root: Path, qualification_path: Path, worker_config_path: Path, model: str) -> tuple[int, str]:
    """Return 0 on a matching PASS, 3 on a nonpassing prerequisite, else 1."""
    if not qualification_path.is_file():
        return 3, "qualification summary missing; Oracle stage will not start"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    if qualification.get("status") != "PASS":
        return 3, f"qualification status={qualification.get('status')!r}; Oracle stage will not start"

    base = json.loads((root / "configs/sweedit_worker_sol.json").read_text(encoding="utf-8"))
    base["model"]["requested_model"] = model
    base["model"]["reasoning_effort"] = "xhigh"
    config_bytes = (json.dumps(base, indent=2) + "\n").encode("utf-8")
    expected: dict[str, str] = {
        "worker_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
    }
    for key, relative_path in HASHED_INPUTS.items():
        expected[key] = hashlib.sha256((root / relative_path).read_bytes()).hexdigest()

    plan = json.loads((root / "artifacts/burned-pilot/plan.json").read_text(encoding="utf-8"))
    if qualification.get("target_ids") != plan["qualification"]["target_ids"]:
        return 1, "qualification target set differs from the frozen plan"
    if qualification.get("requested_model") != model or qualification.get("reasoning_effort") != "xhigh":
        return 1, "qualification model/effort differs from the candidate frozen in the amendment"
    for key, value in expected.items():
        if qualification.get(key) != value:
            return 1, f"qualification integrity check failed: {key}"

    worker_config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with worker_config_path.open("xb") as stream:
        stream.write(config_bytes)
    worker_config_path.chmod(0o600)
    return 0, "qualification=PASS; frozen worker and scaffold hashes match"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--worker-config", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    status, message = prepare_worker(args.root, args.qualification, args.worker_config, args.model)
    print(message)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
