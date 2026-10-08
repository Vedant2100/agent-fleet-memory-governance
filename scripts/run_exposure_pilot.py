#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from fleet_mem_contextbench.governors.deterministic import DeterministicGovernor
from fleet_mem_contextbench.paired import compute_exposure, exposure_gate


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_callable(spec: str):
    module_name, attribute = spec.split(":", 1)
    return getattr(importlib.import_module(module_name), attribute)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the no-model memory-exposure kill gate.")
    parser.add_argument("--release", default="artifacts/smoke")
    parser.add_argument("--output", default="artifacts/smoke/hidden/exposure_pilot.jsonl")
    parser.add_argument("--governor-factory", help="Python factory as module:callable; defaults to the deterministic baseline.")
    parser.add_argument("--memory-token-counter", help="Optional module:callable that returns exact token count for one exposed memory.")
    args = parser.parse_args()
    root = Path(args.release)
    if args.governor_factory:
        governor = load_callable(args.governor_factory)()
    else:
        governor = DeterministicGovernor()
    token_counter = load_callable(args.memory_token_counter) if args.memory_token_counter else None
    records = []
    gates = []
    for manifest in read_jsonl(root / "manifests/benchmark_manifest.jsonl"):
        pool = json.loads((root / manifest["candidate_pool_path"]).read_text(encoding="utf-8"))
        target = pool["target"]
        exposures = [
            compute_exposure(target, pool, arm_id, governor, token_counter=token_counter)
            for arm_id in (
                "B_SHARE_ALL_FIXED_READ", "C_GOVERNED_WRITE_FIXED_READ",
                "D_SHARE_ALL_GOVERNED_READ", "E_GOVERNED_WRITE_GOVERNED_READ",
            )
        ]
        gates.append(exposure_gate(exposures))
        records.append({
            "target_id": target["target_id"], "repository": target["repository"],
            "candidate_pool_size": pool["candidate_count"],
            "arms": [exposure.__dict__ for exposure in exposures],
            "pairwise_exposure_gate": gates[-1],
        })
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in records), encoding="utf-8")
    comparisons = {}
    for key in ("B_SHARE_ALL_FIXED_READ_vs_C_GOVERNED_WRITE_FIXED_READ", "D_SHARE_ALL_GOVERNED_READ_vs_E_GOVERNED_WRITE_GOVERNED_READ"):
        values = [gate[key] for gate in gates if key in gate]
        comparisons[key] = {
            "targets": len(values),
            "shared_pool_differs": sum(row["shared_pool_differs"] for row in values),
            "target_exposure_differs": sum(row["target_exposure_differs"] for row in values),
        }
    summary = {"governor": governor.name, "target_count": len(records), "comparisons": comparisons, "result_file": str(out)}
    summary["gate_passed"] = any(
        row["target_exposure_differs"] >= max(3, round(0.25 * len(records)))
        and row["shared_pool_differs"] >= max(3, round(0.25 * len(records)))
        for row in comparisons.values()
    )
    summary_path = out.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
