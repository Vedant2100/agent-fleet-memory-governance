#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from fleet_mem_contextbench.build import build_release


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full Lite chronology and leakage audit.")
    parser.add_argument("--experience-parquet", required=True)
    parser.add_argument("--targets-parquet", required=True)
    parser.add_argument("--relationships-parquet", required=True)
    parser.add_argument("--output", default="artifacts/audit")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    summary = build_release(
        args.experience_parquet, args.targets_parquet, args.relationships_parquet,
        args.output, seed=args.seed, target_count=0,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
