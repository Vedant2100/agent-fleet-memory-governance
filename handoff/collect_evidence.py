#!/usr/bin/env python3
"""Collect an immutable, checked Fleet-Mem evidence snapshot after a Slurm job ends.

This reads the experiment checkout. It writes only under --output-root.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ARMS = (
    "B_SHARE_ALL", "C_RANDOM_MATCHED", "D_JEV_WRITE", "E_JEV_WRITE_READ",
)
SIGNAL = "artifacts/development/luna_oracle_signal_289648_test_filtered_regrade.json"
TREATMENTS = "results/development/paper-treatments-luna/attempt-0003/treatment_results.jsonl"
TREATMENT_SUMMARY = "results/development/paper-treatments-luna/attempt-0003/summary.json"
FROZEN = (
    SIGNAL,
    "artifacts/development/luna_oracle_signal_289648.json",
    "results/development/paper-treatments-luna/attempt-0002/governors/jev_write_decisions.jsonl",
    "results/development/paper-treatments-luna/attempt-0002/governors/random_matched_write_decisions.jsonl",
    "results/development/paper-treatments-luna/attempt-0002/governors/jev_read_decisions.jsonl",
    "results/development/paper-treatments-luna/attempt-0002/gates/exposure_write_gate.json",
)
RAW_DIRS = (
    "results/development/oracle-signal-luna-289648",
    "results/development/oracle-signal-luna-289648-test-filtered-regrade",
    "results/development/paper-treatments-luna/attempt-0001",
    "results/development/paper-treatments-luna/attempt-0002",
    "results/development/paper-treatments-luna/attempt-0003",
    "artifacts/smoke/manifests",
    "artifacts/smoke/hidden",
    "artifacts/smoke/pools",
    "artifacts/burned-pilot/worker_qualification_289222",
)
RAW_FILES = ("artifacts/smoke/summary.json",)
SOURCE_DIRS = ("src", "scripts", "configs", "docs", "artifacts/development")
SOURCE_FILES = ("README.md", "pyproject.toml", ".gitignore")
SOURCE_DEVELOPMENT_FILES = {
    "build_luna_six_arm_table.py", "luna_oracle_signal.sbatch",
    "luna_paper_treatments.sbatch", "regrade_luna_289648_test_filtered.py",
    "regrade_luna_289648_test_filtered.sbatch", "run_luna_oracle_signal.py",
    "run_luna_paper_treatments.py", "timeout_override.py",
}
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git", "cache", "caches"}
SKIP_SUFFIXES = {".sif", ".img", ".pt", ".safetensors", ".ckpt", ".pyc"}
SENSITIVE_NAMES = {".env", "rclone.conf", "hosts.yml", "credentials.json", "token.json"}
SECRET_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"gh[opusr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
)
TEXT_SUFFIXES = {".json", ".jsonl", ".log", ".txt", ".patch", ".diff",
                 ".sh", ".py", ".sbatch", ".md", ".yaml", ".yml",
                 ".toml", ".csv", ".out", ".err"}


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def slurm_state(job_id: int) -> str:
    result = subprocess.run(
        ["sacct", "-j", str(job_id), "-X", "-n", "-P", "--format=JobIDRaw,State"],
        text=True, capture_output=True, check=False, timeout=30,
    )
    for line in result.stdout.splitlines():
        parts = line.split("|", 1)
        if len(parts) == 2 and parts[0] == str(job_id):
            return parts[1].split()[0]
    return "UNKNOWN"


def checked_grade(source: Path, grade: dict, result_path: str | None,
                  expected_sha: str | None, issues: list[str], label: str) -> None:
    if grade.get("canonical_grade_available") is not True:
        issues.append(f"{label}: canonical grade unavailable")
    if grade.get("patch_applied") is not True:
        issues.append(f"{label}: patch not applied")
    if not result_path:
        issues.append(f"{label}: canonical result path absent")
        return
    path = Path(result_path)
    if not path.is_absolute():
        path = source / path
    if not path.is_file():
        issues.append(f"{label}: canonical result file missing")
    elif expected_sha and digest(path) != expected_sha:
        issues.append(f"{label}: canonical result checksum mismatch")
    elif path.is_file():
        result = json.loads(path.read_text(encoding="utf-8"))
        fields = ("canonical_grade_available", "patch_applied", "resolved",
                  "fail_to_pass_passed", "fail_to_pass_total",
                  "pass_to_pass_passed", "pass_to_pass_total")
        if any(result.get(field) != grade.get(field) for field in fields):
            issues.append(f"{label}: frozen grade disagrees with canonical result")


def inspect_signal(source: Path, signal: dict, issues: list[str]) -> list[str]:
    target_ids = [row["target_id"] for row in signal["records"]]
    if len(signal["records"]) != 10 or signal.get("complete_paired_executable_grades") is not True:
        issues.append("A/F signal table is not complete")
    if signal.get("decision") != "ORACLE_SIGNAL_PRESENT":
        issues.append("A/F signal decision is not ORACLE_SIGNAL_PRESENT")
    for row in signal["records"]:
        for key, arm in (("no_memory", "A_NO_MEMORY"),
                         ("oracle_related", "F_ORACLE_RELATED_CEILING")):
            grade = row[key]
            result_path = grade.get("canonical_result_path")
            if not result_path and grade.get("grade_source") == "frozen_raw_run_289648":
                result_path = (f"results/development/oracle-signal-luna-289648/"
                               f"{row['target_id']}/{arm}/evaluation/canonical_result.json")
            checked_grade(source, grade, result_path,
                          grade.get("canonical_result_sha256"), issues,
                          f"{row['target_id']}/{key}")
    return target_ids


def inspect_treatments(source: Path, treatment: list[dict], target_ids: list[str],
                       issues: list[str]) -> list[tuple[str, str]]:
    expected = {(target, arm) for target in target_ids for arm in ARMS}
    observed = [(row["target_id"], row["arm_id"]) for row in treatment]
    if len(observed) != len(set(observed)):
        issues.append("duplicate treatment target/arm grade")
    missing = sorted(expected - set(observed))
    extra = sorted(set(observed) - expected)
    if missing:
        issues.append(f"missing {len(missing)} treatment grades")
    if extra:
        issues.append(f"unexpected {len(extra)} treatment grades")
    for row in treatment:
        label = f"{row['target_id']}/{row['arm_id']}"
        result_path = (source / "results/development/paper-treatments-luna/attempt-0003"
                       / "workers" / row["target_id"] / row["arm_id"]
                       / "evaluation/canonical_result.json")
        checked_grade(source, row["grade"], str(result_path),
                      row.get("canonical_result_sha256"), issues, label)
    return missing


def inspect_summary(source: Path, issues: list[str]) -> str | None:
    summary_path = source / TREATMENT_SUMMARY
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
    if not summary or summary.get("status") != "COMPLETE" or summary.get("result_count") != 40:
        issues.append("final treatment summary is absent or not COMPLETE with 40 grades")
    table_path = summary_path.parent / "six_arm_paper_table.json"
    if not table_path.is_file():
        issues.append("six-arm paper table is absent")
    elif json.loads(table_path.read_text(encoding="utf-8")).get("status") != "COMPLETE_SIX_ARM_TABLE":
        issues.append("six-arm paper table is not complete")
    return digest(summary_path) if summary_path.is_file() else None


def inspect(source: Path, job_id: int, pinned: dict,
            treatment_path: Path | None = None) -> dict:
    issues: list[str] = []
    signal = json.loads((source / SIGNAL).read_text(encoding="utf-8"))
    treatment_path = treatment_path or source / TREATMENTS
    treatment = rows(treatment_path)
    target_ids = inspect_signal(source, signal, issues)
    missing = inspect_treatments(source, treatment, target_ids, issues)
    summary_sha = inspect_summary(source, issues)

    state = slurm_state(job_id)
    if state != "COMPLETED":
        issues.append(f"Slurm job state is {state}")
    for item in pinned.get("artifacts", []):
        path = source / item["source_path"]
        if not path.is_file() or digest(path) != item["sha256"]:
            issues.append(f"frozen artifact changed or missing: {item['role']}")

    arm_counts = {}
    for arm in ARMS:
        matches = [row for row in treatment if row["arm_id"] == arm]
        arm_counts[arm] = {
            "graded": len(matches),
            "applied": sum(row["grade"].get("patch_applied") is True for row in matches),
            "resolved": sum(row["grade"].get("resolved") is True for row in matches),
        }
    return {
        "status": "COLLECTED_COMPLETE" if not issues else "PARTIAL",
        "issues": issues, "slurm_job_id": job_id, "slurm_state": state,
        "target_ids": target_ids, "treatment_grade_count": len(treatment),
        "missing_target_arms": missing, "arm_counts": arm_counts,
        "baseline_signal_sha256": digest(source / SIGNAL),
        "treatment_results_sha256": digest(treatment_path),
        "treatment_summary_sha256": summary_sha,
    }


def files_under(root: Path):
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(current) / name
            if path.is_symlink() or path.suffix in SKIP_SUFFIXES or path.name in SENSITIVE_NAMES:
                continue
            yield path


def runtime_candidates(source: Path, issues: list[str],
                       provisional_rows: list[dict] | None = None,
                       treatment_snapshot: Path | None = None):
    for rel in FROZEN:
        path = source / rel
        if not path.is_file():
            issues.append(f"archive input missing: {rel}")
        else:
            yield path, f"runtime/{rel}"
    for rel in RAW_FILES:
        path = source / rel
        if path.is_file():
            yield path, f"runtime/{rel}"
        else:
            issues.append(f"archive input missing: {rel}")
    for rel in RAW_DIRS:
        if provisional_rows is not None and rel.endswith("attempt-0003"):
            continue
        root = source / rel
        if not root.is_dir():
            issues.append(f"archive input missing: {rel}")
            continue
        for path in files_under(root):
            yield path, f"runtime/{path.relative_to(source)}"
    if provisional_rows is not None:
        if treatment_snapshot is not None:
            yield treatment_snapshot, f"runtime/{TREATMENTS}"
        exposure_path = source / "results/development/paper-treatments-luna/attempt-0003/treatment_exposures.jsonl"
        if exposure_path.is_file():
            yield exposure_path, f"runtime/{exposure_path.relative_to(source)}"
        for row in provisional_rows:
            folder = (source / "results/development/paper-treatments-luna/attempt-0003/workers"
                      / row["target_id"] / row["arm_id"])
            if not folder.is_dir():
                issues.append(f"completed worker output missing: {row['target_id']}/{row['arm_id']}")
                continue
            for path in files_under(folder):
                yield path, f"runtime/{path.relative_to(source)}"
    for folder in ("artifacts/burned-pilot", "artifacts/development"):
        root = source / folder
        for entry in sorted(os.scandir(root), key=lambda value: value.name):
            if not entry.is_file(follow_symlinks=False):
                continue
            name = entry.name
            include = (folder.endswith("burned-pilot") and name.endswith((".json", ".jsonl")))
            include |= (folder.endswith("development") and name.endswith(".json"))
            include |= (folder.endswith("development") and name.endswith((".out", ".err", ".log"))
                        and any(job in name for job in ("289648", "289879", "289894", "289897", "289898")))
            if include:
                path = Path(entry.path)
                yield path, f"runtime/{path.relative_to(source)}"


def source_candidates(repo: Path):
    for rel in SOURCE_FILES:
        path = repo / rel
        if path.is_file():
            yield path, f"source/{rel}"
    for rel in SOURCE_DIRS:
        root = repo / rel
        for path in files_under(root):
            if rel == "artifacts/development" and path.name not in SOURCE_DEVELOPMENT_FILES:
                continue
            yield path, f"source/{path.relative_to(repo)}"


def archive_inputs(source: Path, repo: Path, issues: list[str],
                   provisional_rows: list[dict] | None = None,
                   treatment_snapshot: Path | None = None):
    yielded: set[str] = set()
    for path, name in runtime_candidates(source, issues, provisional_rows, treatment_snapshot):
        if name not in yielded:
            yielded.add(name)
            yield path, name
    for path, name in source_candidates(repo):
        if name not in yielded:
            yielded.add(name)
            yield path, name


def command_version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, text=True, capture_output=True,
                                check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (result.stdout or result.stderr).splitlines()[0] if result.returncode == 0 else None


def environment(source: Path, code_sha: str) -> dict:
    packages = sorted((dist.metadata.get("Name", "unknown"), dist.version)
                      for dist in importlib.metadata.distributions())
    return {
        "python": sys.version, "platform": platform.platform(),
        "experiment_code_commit": code_sha,
        "contextbench_commit": "12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b",
        "sweedit_commit": "60ca6730714670a91bd6a48a53356be85e145248",
        "apptainer": command_version(["apptainer", "--version"]),
        "slurm": command_version(["srun", "--version"]),
        "worker_config": json.loads((source / "configs/sweedit_worker.json").read_text()),
        "governor_models": {"jev": "jev-1.13.0", "llm_write_G": "unrun"},
        "collector_host_python_packages": packages,
    }


def write_member(archive: zipfile.ZipFile, path: Path, name: str) -> dict:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    h = hashlib.sha256()
    size = 0
    previous = b""
    with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as output:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            if path.suffix in TEXT_SUFFIXES:
                joined = previous + chunk
                if any(pattern.search(joined) for pattern in SECRET_PATTERNS):
                    raise RuntimeError(f"possible credential in archive input: {name}")
                previous = joined[-128:]
            output.write(chunk)
            h.update(chunk)
            size += len(chunk)
    return {"path": name, "size_bytes": size, "sha256": h.hexdigest()}


def readme(snapshot: dict, code_sha: str) -> str:
    issues = "\n".join(f"- {issue}" for issue in snapshot["issues"]) or "- None"
    label = "PROVISIONAL — incomplete snapshot" if snapshot.get("provisional") else snapshot["status"]
    timing = ("captured while the Slurm job was still running" if snapshot["slurm_state"] == "RUNNING"
              else f"collected after Slurm job {snapshot['slurm_job_id']} ended")
    return f"""# Fleet-Mem evidence bundle

Status: {label}. Snapshot {timing}; job state was {snapshot['slurm_state']}.
Experiment code commit: {code_sha}.
Core treatments: A_NO_MEMORY, B_SHARE_ALL, C_RANDOM_MATCHED, D_JEV_WRITE, E_JEV_WRITE_READ, F_ORACLE_RELATED_CEILING.
The earlier G_LLM_WRITE arm is unrun and outside this amended A–F core handoff.
The ten-target A/F signal gate was frozen with 3/10 executable discordances. A/F grades include the supplemental test-file-filtered regrade of already-generated worker patches.
Treatment grades collected: {snapshot['treatment_grade_count']}/40. Read runtime/results/development/paper-treatments-luna/attempt-0003/treatment_results.jsonl for per-task outcomes.

Contents: runtime/ contains raw workers, predictions, API response metadata, canonical grades and logs, baseline failures, target/source manifests, governor decisions, and failed attempts. source/ contains repository code, prompts, configurations, protocol, and analysis scripts. The frozen experiment code commit is recorded above and in environment.json. archive-member-inventory.json records per-file checksums.

Interpretation: these are development pilot outcomes, not a confirmatory effect estimate. Report unresolved patches as legitimate outcomes; inspect FAIL_TO_PASS and PASS_TO_PASS counts and exposure differences. The API exposes the requested worker model alias gpt-6-luna, not an underlying checkpoint build identifier.

Outstanding validation issues:
{issues}
"""


def next_version(root: Path, fingerprint: str) -> tuple[Path, bool]:
    versions = root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    existing = sorted(path for path in versions.iterdir() if path.is_dir())
    for path in existing:
        meta = path / "snapshot.json"
        if meta.is_file() and json.loads(meta.read_text()).get("input_fingerprint") == fingerprint:
            return path, True
    numbers = [int(match.group(1)) for path in existing
               if (match := re.match(r"v(\d+)-", path.name))]
    return versions / f"v{max(numbers, default=0) + 1}-{fingerprint[:12]}", False


def collect(source: Path, repo: Path, output: Path, job_id: int, code_sha: str,
            provisional: bool = False) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".collect.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pinned = json.loads((repo / "handoff/evidence-manifest.json").read_text())
        temporary = tempfile.TemporaryDirectory(prefix=".provisional-", dir=output) if provisional else None
        treatment_snapshot = None
        treatment_rows = None
        if provisional:
            raw = (source / TREATMENTS).read_bytes()
            last_newline = raw.rfind(b"\n")
            stable = raw[:last_newline + 1] if last_newline >= 0 else b""
            treatment_snapshot = Path(temporary.name) / "treatment_results.jsonl"
            treatment_snapshot.write_bytes(stable)
            treatment_rows = rows(treatment_snapshot)
        snapshot = inspect(source, job_id, pinned, treatment_snapshot)
        if snapshot["slurm_state"] in {"RUNNING", "PENDING", "COMPLETING", "CONFIGURING"}:
            if not provisional:
                raise RuntimeError(f"refusing to collect while job {job_id} is {snapshot['slurm_state']}")
        archive_files = list(archive_inputs(source, repo, snapshot["issues"],
                                            treatment_rows, treatment_snapshot))
        snapshot["status"] = "COLLECTED_COMPLETE" if not snapshot["issues"] else "PARTIAL"
        snapshot["provisional"] = snapshot["status"] != "COLLECTED_COMPLETE"
        fingerprint = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
        version, duplicate = next_version(output, fingerprint)
        if duplicate:
            print(json.dumps({"status": "ALREADY_COLLECTED", "version_dir": str(version)}))
            return version
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=output))
        snapshot["input_fingerprint"] = fingerprint
        snapshot["collected_at_utc"] = datetime.now(timezone.utc).isoformat()
        (staging / "snapshot.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        zip_name = f"fleet-mem-aamas-2027-{version.name}.zip"
        zip_path = staging / zip_name
        inventory = []
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            for path, name in archive_files:
                inventory.append(write_member(archive, path, name))
            archive.writestr("README.md", readme(snapshot, code_sha))
            archive.writestr("environment.json", json.dumps(environment(source, code_sha),
                                                           indent=2, sort_keys=True) + "\n")
            archive.writestr("archive-member-inventory.json",
                             json.dumps(inventory, indent=2, sort_keys=True) + "\n")
        with zipfile.ZipFile(zip_path) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise RuntimeError(f"ZIP checksum verification failed: {corrupt}")
        status = snapshot["status"]
        (staging / "snapshot.json").write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
        manifest = {
            "schema_version": 1, "status": status, "publication_status": "LOCAL_VERIFIED",
            "provisional": snapshot["provisional"],
            "experiment_commit": code_sha, "slurm_job_id": job_id,
            "slurm_state": snapshot["slurm_state"], "treatment_grades": snapshot["treatment_grade_count"],
            "required_treatment_grades": 40, "baseline_signal_sha256": snapshot["baseline_signal_sha256"],
            "treatment_results_sha256": snapshot["treatment_results_sha256"],
            "arm_counts": snapshot["arm_counts"], "missing_target_arms": snapshot["missing_target_arms"],
            "issues": snapshot["issues"], "outside_core_unrun_arm": "G_LLM_WRITE",
            "archive": {"filename": zip_name, "size_bytes": zip_path.stat().st_size,
                        "sha256": digest(zip_path), "md5": digest(zip_path, "md5"),
                        "drive_url": None},
            "drive_manifest_url": None, "ready_comment_posted": False,
            "affected_experiments": [f"luna_paper_treatments_{job_id}"],
        }
        (staging / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        staging.rename(version)
        print(json.dumps({"status": status, "version_dir": str(version),
                          "zip_sha256": manifest["archive"]["sha256"]}))
        if temporary is not None:
            temporary.cleanup()
        return version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--handoff-repo", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--experiment-commit", required=True)
    parser.add_argument("--provisional", action="store_true",
                        help="snapshot only finished grades while the Slurm job is still active")
    args = parser.parse_args()
    collect(args.source_root.resolve(), args.handoff_repo.resolve(),
            args.output_root.resolve(), args.job_id, args.experiment_commit,
            provisional=args.provisional)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
