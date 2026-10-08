"""Fixed mini-SWE-agent worker adapter for the burned ContextBench pilot."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .treatments import render_worker_memory


WORKER_MODEL = "qwen2.5-coder:32b"
OLLAMA_VERSION = "0.34.4"
MODEL_LOCK_PATH = Path(__file__).resolve().parents[2] / "configs/model_assets.lock.json"
WORKER_CONTEXT = 16384
MAX_STEPS = 12
MAX_GENERATION_TOKENS = 1024
WORKER_TIMEOUT_SECONDS = 900
PROMPT_ID = "contextbench-worker-command-interface-v3"


def preflight_ollama(base_url: str, model: str) -> dict[str, Any]:
    if not base_url.startswith("http://127.0.0.1:"):
        raise RuntimeError("model service must be local loopback")
    model_lock = json.loads(MODEL_LOCK_PATH.read_text(encoding="utf-8"))
    if model_lock.get("ollama_version") != OLLAMA_VERSION or model not in model_lock.get("models", {}):
        raise RuntimeError(f"model {model!r} is not in the frozen Ollama asset lock")
    with urllib.request.urlopen(base_url.rstrip("/") + "/api/version", timeout=10) as response:
        version = json.loads(response.read().decode("utf-8"))
    with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=20) as response:
        tags = json.loads(response.read().decode("utf-8"))
    observed = next((row for row in tags.get("models", []) if row.get("name") == model), None)
    expected_digest = model_lock["models"][model]["manifest_sha256"]
    observed_digest = str(observed.get("digest", "")).removeprefix("sha256:") if observed else ""
    if version.get("version") != OLLAMA_VERSION or observed_digest != expected_digest:
        raise RuntimeError(
            f"worker model runtime mismatch: version={version.get('version')!r}, "
            f"model_present={observed is not None}, frozen_digest_match={observed_digest == expected_digest}"
        )
    return {
        "ollama_version": version["version"], "model": model,
        "model_manifest_sha256": observed_digest,
        "model_size_bytes": observed.get("size"), "cloud_disabled": os.environ.get("OLLAMA_NO_CLOUD") == "1",
    }


class OllamaOpenAIProxy:
    """Loopback-only buffering proxy that records exact Ollama usage counts."""

    def __init__(self, log_path: Path, upstream_host: str = "127.0.0.1", upstream_port: int = 11434):
        if upstream_host != "127.0.0.1":
            raise ValueError("worker model proxy may only target local Ollama")
        self.log_path = log_path
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.records: list[dict[str, Any]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                self._forward()

            def do_POST(self):  # noqa: N802
                self._forward()

            def do_OPTIONS(self):  # noqa: N802
                self._forward()

            def log_message(self, fmt, *args):
                return

            def _forward(self):
                request_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                started = time.monotonic()
                request_hash = hashlib.sha256(request_body).hexdigest()
                connection = http.client.HTTPConnection(owner.upstream_host, owner.upstream_port, timeout=1200)
                try:
                    forwarded_headers = {
                        key: value for key, value in self.headers.items()
                        if key.casefold() not in {"host", "connection", "content-length", "transfer-encoding"}
                    }
                    connection.request(self.command, self.path, body=request_body or None, headers=forwarded_headers)
                    response = connection.getresponse()
                    response_body = response.read()
                    response_headers = response.getheaders()
                    self.send_response(response.status, response.reason)
                    for key, value in response_headers:
                        if key.casefold() not in {"connection", "transfer-encoding", "content-length", "date", "server"}:
                            self.send_header(key, value)
                    self.send_header("Content-Length", str(len(response_body)))
                    self.end_headers()
                    self.wfile.write(response_body)
                    usage = _openai_usage(response_body, response.getheader("Content-Type", ""))
                    owner.records.append({
                        "path": self.path,
                        "method": self.command,
                        "request_sha256": request_hash,
                        "request_bytes": len(request_body),
                        "status": response.status,
                        "latency_ms": (time.monotonic() - started) * 1000,
                        **usage,
                    })
                except Exception as exc:
                    body = f"local Ollama proxy failure: {type(exc).__name__}".encode("utf-8")
                    self.send_response(502)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    owner.records.append({
                        "path": self.path, "method": self.command,
                        "request_sha256": request_hash, "request_bytes": len(request_body),
                        "status": 502, "error_type": type(exc).__name__,
                        "latency_ms": (time.monotonic() - started) * 1000,
                    })
                finally:
                    connection.close()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.log_path.write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in self.records),
            encoding="utf-8",
        )


def solve_with_mini_swe_agent(
    target: dict[str, Any],
    memories: list[dict[str, Any]],
    *,
    sif_path: str | Path,
    output_dir: str | Path,
    repo_root: str | Path,
    worker_config: str | Path,
    mini_bin: str | Path,
    apptainer_bin: str = "/usr/bin/apptainer",
    ollama_base_url: str = "http://127.0.0.1:11434",
) -> dict[str, Any]:
    """Run one clean, memory-specific worker instance and preserve its patch/logs."""
    prompt = _validate_worker_request(target, memories, ollama_base_url)
    output, files = _create_worker_output(output_dir, prompt)
    run_config = _configure_worker_run(
        target, prompt, files, sif_path, repo_root, worker_config, mini_bin,
        apptainer_bin, ollama_base_url,
    )
    started = time.monotonic()
    process = _execute_mini(run_config, files["usage"])
    return _save_worker_result(target, prompt, run_config, process, files, time.monotonic() - started)


def _validate_worker_request(
    target: dict[str, Any], memories: list[dict[str, Any]], ollama_base_url: str,
) -> str:
    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("burned-pilot worker must run in its authorized Slurm job")
    if os.environ.get("OLLAMA_NO_CLOUD") != "1":
        raise RuntimeError("OLLAMA_NO_CLOUD=1 is required")
    if not ollama_base_url.startswith("http://127.0.0.1:"):
        raise RuntimeError("worker must use the job-local loopback Ollama service")
    public_fields = {
        "target_id", "repository", "target_created_at", "base_commit",
        "environment_setup_commit", "problem_statement",
    }
    if set(target) - public_fields or not str(target.get("problem_statement", "")).strip():
        raise ValueError("worker target must contain only the public ContextBench task fields")
    from .treatments import _assert_source_only
    for memory in memories:
        _assert_source_only(memory)
    return build_task_prompt(target["problem_statement"], memories)


def _create_worker_output(output_dir: str | Path, prompt: str) -> tuple[Path, dict[str, Path]]:
    output = Path(output_dir).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    files = {
        "trajectory": output / "trajectory.json",
        "patch": output / "prediction.patch",
        "stdout": output / "mini.stdout.log",
        "stderr": output / "mini.stderr.log",
        "prompt": output / "task_prompt.txt",
        "usage": output / "ollama_calls.jsonl",
    }
    files["prompt"].write_text(prompt, encoding="utf-8")
    return output, files


def _configure_worker_run(
    target: dict[str, Any], prompt: str, files: dict[str, Path], sif_path: str | Path,
    repo_root: str | Path, worker_config: str | Path, mini_bin: str | Path,
    apptainer_bin: str, ollama_base_url: str,
) -> dict[str, Any]:
    scratch = _job_local_scratch()
    output = files["trajectory"].parent
    global_config = output / "mini-global-config"
    global_config.mkdir(mode=0o700)
    sif = Path(sif_path).resolve(strict=True)
    config = Path(worker_config).resolve(strict=True)
    mini = Path(mini_bin).resolve(strict=True)
    project = Path(repo_root).resolve(strict=True)
    input_record = {"task_id": target["target_id"], "repository": target["repository"], "prompt": prompt}
    task_hash = hashlib.sha256(json.dumps(input_record, sort_keys=True).encode("utf-8")).hexdigest()
    env = _worker_environment(output, global_config, mini, scratch, ollama_base_url)
    command = _worker_command(mini, config, sif, files["trajectory"], prompt, apptainer_bin)
    return {"task_hash": task_hash, "command": command, "env": env, "project": project}


def _job_local_scratch() -> dict[str, str]:
    names = ("TMPDIR", "APPTAINER_TMPDIR", "APPTAINER_CACHEDIR")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"job-local scratch variables are missing: {missing}")
    return {name: os.environ[name] for name in names}


def _worker_environment(
    output: Path, global_config: Path, mini: Path, scratch: dict[str, str], ollama_base_url: str,
) -> dict[str, str]:
    mini_python = os.environ.get("FMC_MINI_PYTHON")
    if not mini_python or not Path(mini_python).is_file():
        raise RuntimeError("FMC_MINI_PYTHON must identify the pinned mini-SWE-agent interpreter")
    home = output / "home"
    home.mkdir(mode=0o700)
    return {
        "PATH": f"{mini.parent}:/usr/bin:/bin",
        "FMC_MINI_PYTHON": mini_python,
        "HOME": str(home),
        "TMPDIR": scratch["TMPDIR"], "TEMP": scratch["TMPDIR"], "TMP": scratch["TMPDIR"],
        "APPTAINER_TMPDIR": scratch["APPTAINER_TMPDIR"],
        "APPTAINER_CACHEDIR": scratch["APPTAINER_CACHEDIR"],
        "XDG_CACHE_HOME": str(Path(scratch["TMPDIR"]) / "xdg-cache"),
        "CUDA_CACHE_PATH": str(Path(scratch["TMPDIR"]) / "cuda-cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "MSWEA_GLOBAL_CONFIG_DIR": str(global_config),
        "MSWEA_CONFIGURED": "true", "MSWEA_SILENT_STARTUP": "1",
        "MSWEA_GLOBAL_COST_LIMIT": "0", "MSWEA_GLOBAL_CALL_LIMIT": "0",
        "OLLAMA_API_BASE": ollama_base_url, "OLLAMA_NO_CLOUD": "1",
        "PAGER": "cat", "TERM": "dumb",
    }


def _worker_command(
    mini: Path, config: Path, sif: Path, trajectory: Path, prompt: str, apptainer_bin: str,
) -> list[str]:
    apptainer_args = ["--containall", "--cleanenv", "--no-mount", "/etc/localtime", "--fakeroot"]
    return [
        str(mini), "--config", "mini.yaml", "--config", str(config),
        "--config", f"environment.image={sif}",
        "--config", f"environment.executable={apptainer_bin}",
        "--config", "environment.cwd=/testbed",
        "--config", f"environment.exec_args={json.dumps(apptainer_args)}",
        "--config", "model.model_kwargs.api_base=__LOCAL_PROXY__",
        "--config", f"model.model_kwargs.num_ctx={WORKER_CONTEXT}",
        "--model", f"ollama_chat/{WORKER_MODEL}", "--task", prompt,
        "--yolo", "--exit-immediately", "--cost-limit", "0",
        "--output", str(trajectory),
    ]


def _execute_mini(run_config: dict[str, Any], usage_path: Path) -> dict[str, Any]:
    proxy = OllamaOpenAIProxy(usage_path)
    with proxy:
        command = [
            item.replace("__LOCAL_PROXY__", _ollama_proxy_base_url(proxy.port))
            for item in run_config["command"]
        ]
        try:
            result = subprocess.run(
                command, cwd=run_config["project"], env=run_config["env"],
                capture_output=True, text=True, timeout=WORKER_TIMEOUT_SECONDS + 60,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": 124, "stdout": _decode_output(exc.stdout),
                "stderr": _decode_output(exc.stderr), "timeout": True,
            }
    return {
        "returncode": result.returncode, "stdout": result.stdout,
        "stderr": result.stderr, "timeout": False,
    }


def _ollama_proxy_base_url(port: int) -> str:
    """Return the native Ollama base URL; the ollama_chat provider appends /api/chat."""
    if not 1 <= port <= 65535:
        raise ValueError("proxy port must be a valid TCP port")
    return f"http://127.0.0.1:{port}"


def _save_worker_result(
    target: dict[str, Any], prompt: str, run_config: dict[str, Any],
    process: dict[str, Any], files: dict[str, Path], elapsed: float,
) -> dict[str, Any]:
    files["stdout"].write_text(process["stdout"], encoding="utf-8")
    files["stderr"].write_text(process["stderr"], encoding="utf-8")
    trajectory = _load_json(files["trajectory"])
    patch = _extract_patch(trajectory)
    files["patch"].write_text(patch, encoding="utf-8")
    calls = _load_jsonl(files["usage"])
    model_calls = _model_usage_calls(calls)
    prompt_tokens = [row.get("prompt_tokens") for row in model_calls]
    completion_tokens = [row.get("completion_tokens") for row in model_calls]
    agent_steps, tool_calls = _count_agent_activity(trajectory)
    result = {
        "task_id": target["target_id"], "worker": "mini-swe-agent 2.4.6",
        "model": WORKER_MODEL, "runtime": "Ollama 0.34.4 local; cloud disabled",
        "prompt_id": PROMPT_ID,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "target_and_memory_input_sha256": run_config["task_hash"],
        "temperature": 0.0, "seed": 42, "context_window_tokens": WORKER_CONTEXT,
        "max_steps": MAX_STEPS, "max_generation_tokens_per_call": MAX_GENERATION_TOKENS,
        "wall_time_limit_seconds": WORKER_TIMEOUT_SECONDS, "wall_seconds": elapsed,
        "returncode": process["returncode"], "timeout": process["timeout"],
        "mini_exit_status": trajectory.get("info", {}).get("exit_status"),
        "patch_bytes": len(patch.encode("utf-8")),
        "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        "model_stats": trajectory.get("info", {}).get("model_stats", {}),
        "ollama_http_request_count": len(calls), "ollama_model_call_count": len(model_calls),
        "worker_input_tokens": _sum_observed_tokens(prompt_tokens),
        "worker_output_tokens": _sum_observed_tokens(completion_tokens),
        "context_tokens_per_call": prompt_tokens,
        "agent_steps": agent_steps, "tool_calls": tool_calls,
        "ollama_calls_log": str(files["usage"]), "trajectory": str(files["trajectory"]),
        "patch_path": str(files["patch"]), "stdout_log": str(files["stdout"]),
        "stderr_log": str(files["stderr"]),
    }
    path = files["trajectory"].parent / "worker_result.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _extract_patch(trajectory: dict[str, Any]) -> str:
    submission = trajectory.get("info", {}).get("submission")
    if isinstance(submission, dict):
        return str(submission.get("patch", ""))
    return submission if isinstance(submission, str) else ""


def _model_usage_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in calls
        if row.get("method") == "POST"
        and row.get("path", "").split("?", 1)[0].endswith(("/chat/completions", "/api/chat"))
    ]


def _sum_observed_tokens(values: list[int | None]) -> int | None:
    if not values or any(not isinstance(value, int) for value in values):
        return None
    return sum(values)

def build_task_prompt(problem_statement: str, memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "## Task\n\n" + problem_statement + "\n\n## Prior source experiences\n\nNo shared memories are available for this task."
    cards = []
    for index, memory in enumerate(memories, start=1):
        cards.append(f"### Memory {index}\n" + render_worker_memory(memory))
    return (
        "## Task\n\n" + problem_statement +
        "\n\n## Prior source experiences\n\n"
        "These source-derived notes may or may not apply. Check their evidence and scope "
        "against current repository files before using them.\n\n" + "\n\n".join(cards)
    )


def _openai_usage(body: bytes, content_type: str) -> dict[str, Any]:
    if "json" not in content_type.casefold():
        return {"prompt_tokens": None, "completion_tokens": None}
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"prompt_tokens": None, "completion_tokens": None}
    usage = value.get("usage", {}) if isinstance(value, dict) else {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if prompt is None and isinstance(value, dict):
        prompt = value.get("prompt_eval_count")
    if completion is None and isinstance(value, dict):
        completion = value.get("eval_count")
    return {
        "prompt_tokens": prompt if isinstance(prompt, int) else None,
        "completion_tokens": completion if isinstance(completion, int) else None,
    }


def _decode_output(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _count_agent_activity(trajectory: dict[str, Any]) -> tuple[int | None, int | None]:
    messages = trajectory.get("messages")
    if not isinstance(messages, list):
        return None, None
    agent_steps = sum(
        1 for row in messages
        if isinstance(row, dict) and row.get("role") == "assistant"
    )
    actions = 0
    for row in messages:
        if not isinstance(row, dict):
            continue
        extra = row.get("extra", {})
        action_list = extra.get("actions", []) if isinstance(extra, dict) else []
        if isinstance(action_list, list):
            actions += len(action_list)
    return agent_steps, actions
