#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fleet_mem_contextbench.data import load_parquet_tasks
from fleet_mem_contextbench.memory_schema import patch_paths


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a source-only index from ContextBench Lite experience rows.")
    parser.add_argument("--experience-parquet", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = []
    for source in sorted(load_parquet_tasks(args.experience_parquet), key=lambda item: item.task_id):
        rows.append({
            "source_task_id": source.task_id, "repository": source.repo,
            "source_created_at": source.created_at, "base_commit": source.base_commit,
            "problem_sha256": digest(source.problem_statement), "reference_patch_sha256": digest(source.patch),
            "reference_patch_paths": sorted(patch_paths(source.patch)),
            "source_outcome": "unknown",
            "source_mode": "PROVIDED_EXPERIENCE_SMOKE",
        })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    print(f"wrote {len(rows)} source records to {output}")


if __name__ == "__main__":
    main()
