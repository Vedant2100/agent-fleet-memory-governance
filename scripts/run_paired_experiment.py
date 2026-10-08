#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from fleet_mem_contextbench.governors.deterministic import DeterministicGovernor
from fleet_mem_contextbench.paired import (
    CommandSolver, SWEContextBenchOfficialEvaluator, run_paired_target,
    transfer_vs_no_memory,
)


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_factory(spec: str):
    module_name, attribute = spec.split(":", 1)
    factory = getattr(importlib.import_module(module_name), attribute)
    return factory()


def load_callable(spec: str):
    module_name, attribute = spec.split(":", 1)
    return getattr(importlib.import_module(module_name), attribute)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paired executable ContextBench target arms.")
    parser.add_argument("--release", default="artifacts/smoke")
    parser.add_argument("--solver-command", required=True, help="JSON stdin/stdout adapter; output must include patch.")
    parser.add_argument("--contextbench-root", required=True, help="Pinned SWE-ContextBench checkout containing evaluation.sh and cases/.")
    parser.add_argument("--governor-factory", help="Python factory as module:callable; defaults to fixed deterministic baseline.")
    parser.add_argument("--memory-token-counter", help="Optional module:callable that returns exact token count for one exposed memory.")
    parser.add_argument("--output", default="results/pilot")
    parser.add_argument("--include-oracle", action="store_true", help="Run F as a separate ceiling using hidden relationship annotations.")
    args = parser.parse_args()
    root = Path(args.release)
    governor = load_factory(args.governor_factory) if args.governor_factory else DeterministicGovernor()
    solver = CommandSolver(args.solver_command)
    evaluator = SWEContextBenchOfficialEvaluator(args.contextbench_root)
    evaluator.preflight()
    token_counter = load_callable(args.memory_token_counter) if args.memory_token_counter else None
    all_results = []
    related_by_target = {}
    if args.include_oracle:
        for relation in rows(root / "hidden/relationship_annotations.jsonl"):
            related_by_target.setdefault(relation["target_id"], set()).add(relation["source_id"])
    for manifest in rows(root / "manifests/benchmark_manifest.jsonl"):
        pool = json.loads((root / manifest["candidate_pool_path"]).read_text(encoding="utf-8"))
        call = {
            "target": pool["target"], "pool": pool, "governor": governor,
            "solver": solver, "evaluator": evaluator, "output_root": args.output,
            "token_counter": token_counter,
        }
        if args.include_oracle:
            from fleet_mem_contextbench.manifest import ARMS
            call["arms"] = [row["arm_id"] for row in ARMS]
            call["related_source_ids"] = related_by_target.get(pool["target"]["target_id"], set())
        all_results.extend(run_paired_target(**call))
    grouped = {}
    for row in all_results:
        grouped.setdefault(row["target_id"], {})[row["arm_id"]] = row
    for arms in grouped.values():
        baseline = arms.get("A_NO_MEMORY")
        if baseline:
            for arm_id, row in arms.items():
                if arm_id != "A_NO_MEMORY":
                    row.update(transfer_vs_no_memory(row, baseline))
    output = Path(args.output) / "paired_results.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in all_results), encoding="utf-8")
    print(f"wrote {len(all_results)} paired arm records to {output}")


if __name__ == "__main__":
    main()
