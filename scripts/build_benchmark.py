#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleet_mem_contextbench.build import build_release


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the frozen SWE-ContextBench Lite smoke release.")
    parser.add_argument("--experience-parquet", required=True)
    parser.add_argument("--targets-parquet", required=True)
    parser.add_argument("--relationships-parquet", required=True)
    parser.add_argument("--output", default="artifacts/smoke")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target-count", type=int, default=16)
    parser.add_argument("--hf-revision", default=None)
    parser.add_argument("--contextbench-commit", default=None)
    parser.add_argument("--source-trajectory-jsonl", help="Fresh mode: one source-only trajectory record per experience task.")
    args = parser.parse_args()
    kwargs = {}
    if args.hf_revision:
        kwargs["hf_revision"] = args.hf_revision
    if args.contextbench_commit:
        kwargs["contextbench_commit"] = args.contextbench_commit
    if args.source_trajectory_jsonl:
        kwargs["source_trajectory_jsonl"] = args.source_trajectory_jsonl
    summary = build_release(
        args.experience_parquet, args.targets_parquet, args.relationships_parquet,
        args.output, seed=args.seed, target_count=args.target_count, **kwargs,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
