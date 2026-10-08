#!/usr/bin/env python3
"""Prompt privately for the API key, run only the frozen two-task Sol diagnostic."""

from __future__ import annotations

import getpass
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTEXTBENCH = Path("/home/csgrad/vbork001/.cache/fleet-mem-contextbench/SWEContextBench")
TARGETS = Path("/home/csgrad/vbork001/.cache/fleet-mem-contextbench/data/SWEContextBench_Related_Lite.parquet")
TASK_IDS = "sympy__sympy-21309 django__django-34176"
SUMMARY = ROOT / "artifacts/development/sol_two_task_diagnostic.json"
RESUME_SUMMARY = ROOT / "artifacts/development/sol_django_resume_289270.json"
SBATCH_SCRIPT = ROOT / "scripts/run_sweedit_pilot.sbatch"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume-cancelled-django", action="store_true",
        help="restart only the unfinished Django task from cancelled job 289270",
    )
    args = parser.parse_args()
    resume_django = args.resume_cancelled_django
    summary_path = RESUME_SUMMARY if resume_django else SUMMARY
    secret_file: Path | None = None
    job_id: str | None = None
    try:
        _preflight(summary_path, resume_django)
        if not sys.stdin.isatty():
            raise RuntimeError("Run this command from a terminal so the API key can be entered without echo.")
        key = getpass.getpass("OpenAI API key (input hidden): ")
        if not key or key != key.strip() or any(ch in key for ch in "\r\n\x00"):
            raise RuntimeError("The key must be nonempty and contain no surrounding whitespace or line breaks.")
        secret_file = _write_private_env_file(key)
        del key
        run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        job_id = _submit(secret_file, resume_django, run_tag)
        scope = "only the unfinished frozen Django target" if resume_django else "the frozen Sol diagnostic pair"
        print(f"Submitted {scope} as Slurm job {job_id}.", flush=True)
        state, exit_code = _wait_for_job(job_id)
        if state != "COMPLETED" or exit_code != "0:0":
            print(f"Slurm job ended with state={state}, exit_code={exit_code}.", file=sys.stderr)
            return 2
        if not summary_path.is_file():
            raise RuntimeError("Slurm completed but did not create the diagnostic summary.")
        result = json.loads(summary_path.read_text(encoding="utf-8"))
        print(json.dumps({
            "summary": str(summary_path),
            "status": result.get("status"),
            "requested_model": result.get("requested_model"),
            "reasoning_effort": result.get("reasoning_effort"),
            "canonical_grade_count": result.get("canonical_grade_count"),
            "resolved_count": result.get("resolved_count"),
        }, indent=2))
        expected_status = "DIAGNOSTIC_RESTART_COMPLETE" if resume_django else "DIAGNOSTIC_COMPLETE"
        return 0 if result.get("status") == expected_status else 2
    except KeyboardInterrupt:
        if job_id:
            subprocess.run(["scancel", job_id], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Interrupted; the diagnostic job was cancelled if it had been submitted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Sol diagnostic submission stopped: {exc}", file=sys.stderr)
        return 2
    finally:
        if secret_file is not None:
            secret_file.unlink(missing_ok=True)


def _preflight(summary_path: Path, resume_django: bool) -> None:
    task_ids = ["django__django-34176"] if resume_django else TASK_IDS.split()
    required = [
        CONTEXTBENCH, TARGETS, SBATCH_SCRIPT,
        ROOT / "configs/sweedit_worker_sol.json",
        ROOT / "artifacts/burned-pilot/plan.json",
        *(ROOT / "artifacts/burned-pilot/images" / f"{task_id}.sif" for task_id in task_ids),
        Path("/home/csgrad/vbork001/benchmarks/SWE-Edit"),
        Path("/home/csgrad/vbork001/.venv-sweedit-run/bin/python"),
        Path("/home/csgrad/vbork001/miniconda3/bin/python"),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Required frozen worker inputs are unavailable: " + ", ".join(missing))
    if summary_path.exists():
        raise RuntimeError(f"Refusing to overwrite the existing diagnostic summary: {summary_path}")
    if not shutil_which("sbatch") or not shutil_which("sacct"):
        raise RuntimeError("This script needs sbatch and sacct on PATH.")


def _write_private_env_file(key: str) -> Path:
    directory = Path.home() / ".cache/fleet-mem-contextbench/credentials"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    if directory.stat().st_uid != os.getuid():
        raise RuntimeError("Credential directory is not owned by the current user.")
    descriptor, name = tempfile.mkstemp(prefix="sol-diagnostic-", suffix=".env", dir=directory)
    path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("export OPENAI_API_KEY=" + shlex.quote(key) + "\n")
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _submit(secret_file: Path, resume_django: bool, run_tag: str) -> str:
    task_ids = "django__django-34176" if resume_django else TASK_IDS
    stage = "diagnostic_resume" if resume_django else "diagnostic"
    summary = RESUME_SUMMARY if resume_django else SUMMARY
    run_root = ROOT / "results/development" / (
        f"sol-diagnostic-django-resume-{run_tag}" if resume_django else "sol-diagnostic-%j"
    )
    exported = {
        "FMC_PROJECT_ROOT": str(ROOT),
        "FMC_SWEEDIT_STAGE": stage,
        "FMC_OPENAI_ENV_FILE": str(secret_file),
        "FMC_CONTEXTBENCH_ROOT": str(CONTEXTBENCH),
        "FMC_TARGETS_PARQUET": str(TARGETS),
        "FMC_WORKER_CONFIG": str(ROOT / "configs/sweedit_worker_sol.json"),
        "FMC_TARGET_IDS": task_ids,
        "FMC_RUN_ROOT": str(run_root),
        "FMC_SUMMARY": str(summary),
        "FMC_PYTHON": "/home/csgrad/vbork001/miniconda3/bin/python",
        "FMC_SWEEDIT_ROOT": "/home/csgrad/vbork001/benchmarks/SWE-Edit",
        "FMC_SWEEDIT_ENV": "/home/csgrad/vbork001/.venv-sweedit-run",
        "FMC_PYTHON_PREFIX": "/home/csgrad/vbork001/miniconda3",
    }
    if any("," in value for value in exported.values()):
        raise RuntimeError("Slurm export values cannot contain commas.")
    child_env = os.environ.copy()
    child_env.pop("OPENAI_API_KEY", None)
    child_env.pop("APPTAINERENV_OPENAI_API_KEY", None)
    child_env.pop("FMC_OPENAI_ENV_FILE", None)
    export_arg = "--export=ALL," + ",".join(f"{name}={value}" for name, value in exported.items())
    result = subprocess.run(
        ["sbatch", "--parsable", export_arg, str(SBATCH_SCRIPT)],
        cwd=ROOT, env=child_env, text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError("sbatch failed: " + (result.stderr.strip() or result.stdout.strip()))
    job_id = result.stdout.strip().split(";", 1)[0]
    if not job_id.isdigit():
        raise RuntimeError("sbatch returned an unrecognized job ID.")
    return job_id


def _wait_for_job(job_id: str) -> tuple[str, str]:
    last_status: tuple[str, str] | None = None
    started = time.monotonic()
    while time.monotonic() - started < 25 * 60 * 60:
        result = subprocess.run(
            ["sacct", "-X", "-n", "-P", "-j", job_id, "--format=JobIDRaw,State,ExitCode"],
            text=True, capture_output=True, check=False,
        )
        for line in result.stdout.splitlines():
            fields = line.split("|")
            if len(fields) < 3 or fields[0] != job_id:
                continue
            state, exit_code = fields[1].split()[0], fields[2]
            if state in {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED"}:
                return state, exit_code
            current = (state, exit_code)
            if current != last_status:
                print(f"Diagnostic job {job_id}: {state}.", flush=True)
                last_status = current
        time.sleep(20)
    subprocess.run(["scancel", job_id], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raise RuntimeError("Diagnostic exceeded the 24-hour Slurm time limit plus one-hour accounting grace period.")


def shutil_which(command: str) -> str | None:
    from shutil import which

    return which(command)


if __name__ == "__main__":
    for signum in (signal.SIGTERM,):
        signal.signal(signum, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    raise SystemExit(main())
