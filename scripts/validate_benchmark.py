#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleet_mem_contextbench.validators import validate_candidate_pool, validate_manifest


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate visible benchmark files and hidden-label separation.")
    parser.add_argument("--release", default="artifacts/smoke")
    args = parser.parse_args()
    release = Path(args.release)
    manifest_path = release / "manifests/benchmark_manifest.jsonl"
    manifest = rows(manifest_path)
    errors = []
    for row in manifest:
        errors.extend(f"{row['target_id']}: {error}" for error in validate_manifest(row))
        pool = json.loads((release / row["candidate_pool_path"]).read_text(encoding="utf-8"))
        errors.extend(f"{row['target_id']}: {error}" for error in validate_candidate_pool(pool))
        if pool.get("pool_hash") != row.get("candidate_pool_hash"):
            errors.append(f"{row['target_id']}: manifest pool hash mismatch")
    if errors:
        raise SystemExit("\n".join(errors))
    print(json.dumps({"manifest_rows": len(manifest), "status": "PASS", "target_ids": [row["target_id"] for row in manifest]}, indent=2))


if __name__ == "__main__":
    main()
