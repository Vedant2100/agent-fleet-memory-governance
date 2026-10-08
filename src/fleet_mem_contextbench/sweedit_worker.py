"""Small adapter for the pinned SWE-Edit Baseline inside ContextBench SIFs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from .treatments import render_worker_memory


SWE_EDIT_COMMIT = "60ca6730714670a91bd6a48a53356be85e145248"
AGENT_TIMEOUT_SECONDS = 1800
DEFAULT_WORKER_CONFIG = Path(__file__).resolve().parents[2] / "configs/sweedit_worker.json"


def run_sweedit_worker(
    target: dict[str, Any],
    memories: list[dict[str, Any]],
    *,
    sif_path: str | Path,
    output_dir: str | Path,
    sweedit_root: str | Path,
    sweedit_env: str | Path,
    python_prefix: str | Path,
    worker_config: str | Path = DEFAULT_WORKER_CONFIG,
    apptainer_bin: str = "/usr/bin/apptainer",
) -> dict[str, Any]:
    """Run a fresh SWE-Edit task process and collect its submitted git diff."""
    api_key = _validate_worker_request(target)
    runtime = _validate_worker_runtime(
        target, sif_path, sweedit_root, sweedit_env, python_prefix,
        worker_config, apptainer_bin,
    )
    files = _prepare_worker_files(target, memories, output_dir)
    command = _build_apptainer_command(target, runtime, files, apptainer_bin)
    return _launch_and_collect(command, target, runtime, files, api_key)


def _validate_worker_request(target: dict[str, Any]) -> str:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("SWE-Edit pilot worker must run in its authorized Slurm allocation")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is unavailable to the Slurm worker launcher")
    public_fields = {
        "target_id", "repository", "target_created_at", "base_commit",
        "environment_setup_commit", "problem_statement",
    }
    if set(target) - public_fields:
        raise ValueError("worker target contains fields outside the public task interface")
    if not str(target.get("problem_statement", "")).strip():
        raise ValueError("worker target has an empty public problem statement")
    return api_key


def load_worker_settings(worker_config: str | Path = DEFAULT_WORKER_CONFIG) -> dict[str, Any]:
    """Load the frozen worker config so model comparisons vary one field only."""
    config_path = Path(worker_config).resolve(strict=True)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    model = config.get("model", {})
    budget = config.get("tool_budget", {})
    if config.get("scaffold_commit") != SWE_EDIT_COMMIT:
        raise RuntimeError("worker config does not pin the validated SWE-Edit revision")
    if config.get("agent_type") != "baseline" or config.get("agent_class") != "SwebenchAgent":
        raise RuntimeError("worker config differs from the validated SWE-Edit agent")
    if model.get("provider") != "OpenAI Responses API":
        raise RuntimeError("worker config must use the validated OpenAI Responses API path")
    if budget.get("max_iterations") != 100 or budget.get("task_timeout_seconds") != AGENT_TIMEOUT_SECONDS:
        raise RuntimeError("worker config differs from the validated worker budget")
    if not str(model.get("requested_model", "")).strip() or not str(model.get("reasoning_effort", "")).strip():
        raise RuntimeError("worker config must specify model and reasoning effort")
    return {
        "path": config_path,
        "sha256": _sha256(config_path.read_bytes()),
        "requested_model": model["requested_model"],
        "reasoning_effort": model["reasoning_effort"],
        "config": config,
    }


def _validate_worker_runtime(target, sif_path, sweedit_root, sweedit_env, python_prefix, worker_config, apptainer_bin):
    root = Path(sweedit_root).resolve(strict=True)
    environment = Path(sweedit_env).resolve(strict=True)
    interpreter_root = Path(python_prefix).resolve(strict=True)
    image = Path(sif_path).resolve(strict=True)
    for path in (root, environment, interpreter_root):
        _check_bind_path(path)
    commit = _command(["git", "rev-parse", "HEAD"], cwd=root).strip()
    dirty = _command(["git", "status", "--porcelain"], cwd=root).strip()
    if commit != SWE_EDIT_COMMIT or dirty:
        raise RuntimeError(f"SWE-Edit checkout must be clean at {SWE_EDIT_COMMIT}; found {commit}")
    settings = load_worker_settings(worker_config)
    if not _worker_config_matches(settings["config"], commit):
        raise RuntimeError("SWE-Edit worker implementation differs from its frozen config")
    expected_base = str(target.get("base_commit", ""))
    image_head = verify_target_sif_base(image, expected_base, apptainer_bin=apptainer_bin)
    return {
        "root": root, "environment": environment, "interpreter_root": interpreter_root,
        "image": image, "commit": commit, "image_head": image_head,
        "expected_base": expected_base,
        "worker_settings": settings,
    }


def _worker_config_matches(config: dict[str, Any], commit: str) -> bool:
    return (
        config.get("scaffold_commit") == commit
        and bool(config.get("model", {}).get("requested_model"))
        and bool(config.get("model", {}).get("reasoning_effort"))
        and config.get("tool_budget", {}).get("max_iterations") == 100
        and config.get("tool_budget", {}).get("task_timeout_seconds") == AGENT_TIMEOUT_SECONDS
    )


def _prepare_worker_files(target, memories, output_dir):
    output = Path(output_dir).resolve(strict=False)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    prompt = build_sweedit_prompt(target, memories)
    paths = {
        "output": output,
        "prompt": output / "task_prompt.txt",
        "patch": output / "prediction.patch",
        "responses": output / "api_responses.jsonl",
        "status": output / "worker_status.json",
        "trajectory": output / "trajectory",
        "bootstrap": Path(__file__).resolve().parents[2] / "scripts/sweedit_bootstrap.py",
        "collector": Path(__file__).resolve().with_name("working_tree.py"),
        "log": output / "worker.log",
    }
    for path_name in ("prompt", "patch", "responses", "status"):
        paths[path_name].touch(mode=0o600)
    paths["prompt"].write_text(prompt, encoding="utf-8")
    paths["prompt_sha256"] = _sha256(prompt.encode("utf-8"))
    paths["trajectory"].mkdir(mode=0o700)
    return paths


def _build_apptainer_command(target, runtime, files, apptainer_bin):
    command = [
        apptainer_bin, "exec", "--cleanenv", "--containall", "--pid", "--no-home",
        "--fakeroot", "--writable-tmpfs", "--pwd", "/tmp",
    ]
    binds = [
        (runtime["root"], "/agent", "ro"),
        (runtime["environment"], runtime["environment"], "ro"),
        (runtime["interpreter_root"], runtime["interpreter_root"], "ro"),
        (files["prompt"], "/tmp/fmc-task-prompt.txt", "ro"),
        (files["responses"], "/tmp/fmc-api-responses.jsonl", "rw"),
        (files["patch"], "/tmp/fmc-submission.patch", "rw"),
        (files["status"], "/tmp/fmc-worker-status.json", "rw"),
        (files["bootstrap"], "/tmp/fmc-sweedit-bootstrap.py", "ro"),
        (files["trajectory"], "/tmp/.traj/sweedit", "rw"),
        (files["collector"], "/tmp/fmc-working-tree.py", "ro"),
    ]
    for host_path, container_path, mode in binds:
        command.extend(["--bind", f"{host_path}:{container_path}:{mode}"])
    exposed_env = _agent_environment(target, runtime)
    for name, value in exposed_env.items():
        command.extend(["--env", f"{name}={value}"])
    command.extend([
        str(runtime["image"]), str(runtime["environment"] / "bin/python"),
        "/tmp/fmc-sweedit-bootstrap.py",
    ])
    return command


def _agent_environment(target, runtime):
    settings = runtime["worker_settings"]
    return {
        "API_TYPE": "OPENAI", "MODEL": settings["requested_model"],
        "REASONING_EFFORT": settings["reasoning_effort"], "AGENT_TYPE": "baseline",
        "INSTANCE_ID": target["target_id"], "WORKDIR": "/testbed",
        "SAVE_DIR": "/tmp/.traj/sweedit", "PYTHONPATH": "/agent/src",
        "PYTHONUNBUFFERED": "1",
    }


def _launch_and_collect(command, target, runtime, files, api_key):
    return_code, timed_out, elapsed = _run_worker_process(command, files, api_key)
    return _collect_worker_result(target, runtime, files, return_code, timed_out, elapsed)


def _run_worker_process(command, files, api_key):
    child_env = {
        name: value for name, value in os.environ.items()
        if name not in {"OPENAI_API_KEY", "APPTAINERENV_OPENAI_API_KEY"}
    }
    child_env["APPTAINERENV_OPENAI_API_KEY"] = api_key
    started = time.monotonic()
    timed_out = False
    try:
        with files["log"].open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=os.environ.get("SLURM_SUBMIT_DIR", str(files["output"])),
                env=child_env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                return_code = process.wait(timeout=AGENT_TIMEOUT_SECONDS + 45)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    return_code = process.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    return_code = process.wait()
    except ProcessLookupError:
        return_code = 124 if timed_out else 125
    except subprocess.TimeoutExpired:
        timed_out = True
        return_code = 124
    finally:
        _redact_log(files["log"])
    return return_code, timed_out, time.monotonic() - started


def _collect_worker_result(target, runtime, files, return_code, timed_out, elapsed):
    patch = files["patch"].read_bytes()
    responses = _read_jsonl(files["responses"])
    result = _response_metrics(responses)
    token_stats, tool_stats = _trajectory_stats(files["trajectory"], target["target_id"])
    finish_calls = int((tool_stats or {}).get("finish", 0))
    worker_status = _read_json(files["status"])
    declared = worker_status.get("worker_declared_submission", {})
    requested_model = runtime["worker_settings"]["requested_model"]
    model_ok = bool(result["returned_model_ids"]) and all(
        name.startswith(requested_model) for name in result["returned_model_ids"]
    )
    declared_finish = int(declared.get("finish_tool_calls", finish_calls)) > 0
    repository_recovered = worker_status.get("repository_state_recovered") is True
    authoritative_valid = repository_recovered and not worker_status.get("collector_error")
    valid = return_code == 0 and not timed_out and declared_finish and bool(patch) and model_ok and bool(worker_status)
    return _worker_record(
        runtime, files, result, token_stats, tool_stats, worker_status,
        return_code, timed_out, elapsed, patch, finish_calls, model_ok, valid,
        declared, authoritative_valid, repository_recovered,
    )


def _response_metrics(responses):
    return {
        "returned_model_ids": sorted({str(row.get("model", "")) for row in responses if row.get("model")}),
        "api_call_count": len(responses),
        "input_tokens": sum(int((row.get("usage") or {}).get("input_tokens", 0)) for row in responses),
        "output_tokens": sum(int((row.get("usage") or {}).get("output_tokens", 0)) for row in responses),
    }


def _worker_record(
    runtime, files, response, token_stats, tool_stats, status, return_code,
    timed_out, elapsed, patch, finish_calls, model_ok, valid, declared,
    authoritative_valid, repository_recovered,
):
    settings = runtime["worker_settings"]
    return {
        **response,
        "requested_model": settings["requested_model"],
        "requested_model_confirmed": model_ok,
        "reasoning_effort": settings["reasoning_effort"],
        "scaffold_repository": "https://github.com/microsoft/SWE-Edit",
        "scaffold_commit": runtime["commit"],
        "target_sif_path": str(runtime["image"]),
        "target_sif_repository_head": runtime["image_head"],
        "target_base_commit": runtime["expected_base"],
        "agent_type": "baseline", "agent_class": "SwebenchAgent",
        "max_iterations": 100,
        "max_iterations_source": "upstream SWE-Edit SwebenchAgent default",
        "task_timeout_seconds": AGENT_TIMEOUT_SECONDS,
        "agent_exit_code": return_code,
        "agent_timed_out": timed_out,
        "termination_reason": _termination_reason(return_code, timed_out, tool_stats, token_stats, status),
        "valid_submission": valid,
        "worker_declared_submission": declared,
        "authoritative_prediction_valid": authoritative_valid,
        "repository_state_recovered": repository_recovered,
        "initial_repository_commit": status.get("initial_repository_commit"),
        "initial_repository_tree": status.get("initial_repository_tree"),
        "git_status_porcelain": status.get("git_status_porcelain", []),
        "tracked_source_files_changed": status.get("tracked_source_files_changed"),
        "tracked_source_files": status.get("tracked_source_files", []),
        "relevant_untracked_files_created": status.get("relevant_untracked_files_created", []),
        "authoritative_diff_bytes": status.get("authoritative_diff_bytes", len(patch)),
        "authoritative_diff_sha256": status.get("authoritative_diff_sha256", _sha256(patch)),
        "collector_error": status.get("collector_error"),
        "bootstrap_termination_reason": status.get("termination_reason"),
        "finish_tool_calls": finish_calls,
        "patch_path": str(files["patch"]),
        "patch_bytes": len(patch), "patch_sha256": _sha256(patch),
        "prompt_path": str(files["prompt"]), "prompt_sha256": files["prompt_sha256"],
        "trajectory_token_stats": token_stats, "tool_call_stats": tool_stats,
        "elapsed_seconds": round(elapsed, 3), "output_dir": str(files["output"]),
        "worker_log": str(files["log"]),
        "api_response_log": str(files["responses"]), "worker_status": status,
    }


def build_sweedit_prompt(target: dict[str, Any], memories: list[dict[str, Any]]) -> str:
    """Assemble public issue text plus precisely the already-decided memory exposure."""
    memory_block = "\n\n".join(render_worker_memory(memory) for memory in memories)
    if memory_block:
        memory_block = (
            "\n\nShared source memories are fallible historical observations. "
            "Check them against the current repository and task before relying on them:\n"
            + memory_block
        )
    return (
        f"The codebase for {target.get('repository', 'the repository')} is located in /testbed.\n"
        "The Python development environment and dependencies are already fully set up for you in /testbed. "
        "Do not install external packages, run apt/pip, or clone external repositories.\n\n"
        f"Issue Description:\n{target['problem_statement']}\n"
        f"{memory_block}\n\n"
        "Instructions:\n"
        "1. Inspect the source code in /testbed to locate the root cause.\n"
        "2. Make the minimal necessary changes directly to the source files in /testbed to fix the issue.\n"
        "3. You MUST use the file editor (str_replace_editor) or bash commands to modify the code in /testbed. "
        "Do NOT merely provide an explanation or summary without modifying the codebase; an unmodified repository will be scored as a failure.\n"
        "4. Run relevant tests in /testbed to verify your changes if feasible.\n"
        "5. Once your changes are saved and verified, call the finish tool to complete the task."
    )


def verify_target_sif_base(
    sif_path: str | Path, expected_base: str, *, apptainer_bin: str = "/usr/bin/apptainer",
) -> str:
    if not expected_base:
        raise ValueError("ContextBench target has no registered base_commit")
    result = subprocess.run(
        [
            apptainer_bin, "exec", "--cleanenv", "--containall", "--no-home", "--fakeroot",
            "--pwd", "/testbed", str(Path(sif_path).resolve(strict=True)),
            "git", "-C", "/testbed", "rev-parse", "HEAD",
        ],
        check=True, capture_output=True, text=True, timeout=60,
    )
    actual = result.stdout.strip()
    if actual != expected_base:
        raise RuntimeError(
            f"target SIF repository HEAD differs from ContextBench base commit: "
            f"expected={expected_base!r}, image={actual!r}"
        )
    return actual


def _trajectory_stats(root: Path, task_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    task_dir = root / task_id
    token_path = task_dir / "token_stats.json"
    tool_path = task_dir / "tool_call_stats.json"
    return (
        _read_json(token_path) if token_path.is_file() else None,
        _read_json(tool_path) if tool_path.is_file() else None,
    )


def _termination_reason(
    return_code: int, timed_out: bool,
    tool_stats: dict[str, Any] | None, token_stats: dict[str, Any] | None,
    worker_status: dict[str, Any] | None,
) -> str:
    if timed_out:
        return "wall_clock_timeout"
    if not (worker_status or {}).get("repository_state_recovered"):
        return "repository_state_unrecovered"
    if int((tool_stats or {}).get("finish", 0)) > 0:
        return "finish_tool"
    bootstrap_reason = str((worker_status or {}).get("termination_reason", ""))
    if bootstrap_reason.startswith("signal_or_system_exit:"):
        return "worker_signal_or_system_exit"
    if return_code != 0:
        return "agent_process_failure"
    if int((token_stats or {}).get("num_rounds", 0)) >= 100:
        return "iteration_limit"
    return "agent_exited_without_finish"


def _check_bind_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    if ":" in str(path):
        raise ValueError(f"Apptainer bind paths containing ':' are unsupported: {path}")


def _command(argv: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _redact_log(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    cleaned = re.sub(r"(?i)sk-[a-z0-9_*=-]{6,}", "<redacted-key-fragment>", text)
    path.write_text(cleaned, encoding="utf-8")
    path.chmod(0o600)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
