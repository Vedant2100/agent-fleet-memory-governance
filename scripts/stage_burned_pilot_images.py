#!/usr/bin/env python3
"""Stage the exact SWE-ContextBench Lite evaluator image tags as Apptainer SIFs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default="artifacts/burned-pilot/plan.json")
    parser.add_argument("--image-dir", default="artifacts/burned-pilot/images")
    parser.add_argument("--job-tmp", required=True, help="Local scratch path for Apptainer temp/cache files.")
    parser.add_argument("--target-id", action="append", help="Stage only this frozen target; repeatable.")
    args = parser.parse_args()

    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("SWE-ContextBench image staging must run in the configured Slurm Apptainer allocation")

    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    targets = args.target_id or plan["target_ids"]
    unknown = sorted(set(targets) - set(plan["target_ids"]))
    if unknown:
        raise SystemExit(f"target IDs are outside the frozen pilot: {unknown}")
    if not shutil.which("apptainer"):
        raise SystemExit("Apptainer executable is unavailable")

    image_dir = Path(args.image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    job_tmp = Path(args.job_tmp).resolve(strict=True)
    env = os.environ.copy()
    env["TMPDIR"] = str(job_tmp)
    env["APPTAINER_TMPDIR"] = str(job_tmp)
    env["APPTAINER_CACHEDIR"] = str(job_tmp / "apptainer-cache")
    Path(env["APPTAINER_CACHEDIR"]).mkdir(mode=0o700, parents=True, exist_ok=True)

    version = subprocess.run(["apptainer", "--version"], text=True, capture_output=True, check=True).stdout.strip()
    records = []
    for target_id in targets:
        image_tag = target_id.replace("__", ".").lower()
        image_ref = f"docker://jiayuanz3/swecontextbench:{image_tag}"
        sif = image_dir / f"{target_id}.sif"
        metadata_path = sif.with_suffix(".sif.json")
        if sif.exists() or metadata_path.exists():
            raise SystemExit(f"refusing to overwrite existing staged target image: {sif}")
        log_path = sif.with_suffix(".pull.log")
        command = ["apptainer", "pull", str(sif), image_ref]
        result = subprocess.run(command, env=env, text=True, capture_output=True, check=False)
        log_path.write_text(
            "command=" + json.dumps(command) + "\n"
            + f"returncode={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            encoding="utf-8",
        )
        if result.returncode:
            sif.unlink(missing_ok=True)
            raise RuntimeError(f"Apptainer image pull failed for {target_id}; see {log_path}")
        smoke = subprocess.run(
            ["apptainer", "exec", "--cleanenv", str(sif), "bash", "-lc",
             'test -d /testbed && test -d /testbed/.git && printf "swecontextbench_image_ok\\n"'],
            env=env, text=True, capture_output=True, check=False,
        )
        if smoke.returncode:
            raise RuntimeError(f"staged image failed /testbed smoke check for {target_id}: {smoke.stderr}")
        record = {
            "target_id": target_id,
            "image_ref": image_ref,
            "sif_path": str(sif),
            "sif_sha256": sha256_file(sif),
            "apptainer_version": version,
            "image_smoke_output": smoke.stdout.strip(),
            "pull_command": command,
            "pull_log": str(log_path),
        }
        metadata_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        records.append(record)
        print(json.dumps({"target_id": target_id, "sif_sha256": record["sif_sha256"]}, sort_keys=True))

    audit_path = image_dir / "staged_images.jsonl"
    with audit_path.open("a", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps({"staged_count": len(records), "audit": str(audit_path)}, indent=2))


if __name__ == "__main__":
    main()
