#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter

from fleet_mem_contextbench.data import load_parquet_tasks


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the pinned SWE-ContextBench Lite parquet inputs.")
    parser.add_argument("--experience-parquet", required=True)
    parser.add_argument("--targets-parquet", required=True)
    args = parser.parse_args()
    experience = load_parquet_tasks(args.experience_parquet)
    targets = load_parquet_tasks(args.targets_parquet)
    print(json.dumps({
        "experience_count": len(experience),
        "target_count": len(targets),
        "experience_repositories": dict(sorted(Counter(row.repo for row in experience).items())),
        "target_repositories": dict(sorted(Counter(row.repo for row in targets).items())),
        "missing_source_timestamps": sum(row.created_at is None for row in experience),
        "missing_target_timestamps": sum(row.created_at is None for row in targets),
        "missing_target_base_commits": sum(row.base_commit is None for row in targets),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
