#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from fleet_mem_contextbench.build import build_release


def main() -> None:
    parser = argparse.ArgumentParser(description="Build natural chronological pools and their hidden audit.")
    parser.add_argument("--experience-parquet", required=True)
    parser.add_argument("--targets-parquet", required=True)
    parser.add_argument("--relationships-parquet", required=True)
    parser.add_argument("--output", default="artifacts/pools")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target-count", type=int, default=16)
    args = parser.parse_args()
    summary = build_release(
        args.experience_parquet, args.targets_parquet, args.relationships_parquet,
        args.output, seed=args.seed, target_count=args.target_count,
    )
    print(json.dumps(summary["smoke_candidate_counts"], indent=2))


if __name__ == "__main__":
    main()
