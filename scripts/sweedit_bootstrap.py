"""Run upstream SWE-Edit with an authoritative working-tree collector."""

from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import runpy
import signal
import subprocess
from pathlib import Path
from typing import Any


WORKDIR = Path(os.environ["WORKDIR"])
PROMPT_FILE = Path("/tmp/fmc-task-prompt.txt")
RESPONSE_LOG = Path("/tmp/fmc-api-responses.jsonl")
PATCH_FILE = Path("/tmp/fmc-submission.patch")
STATUS_FILE = Path("/tmp/fmc-worker-status.json")
COLLECTOR_FILE = Path("/tmp/fmc-working-tree.py")


def _load_collector():
    spec = importlib.util.spec_from_file_location("fmc_working_tree", COLLECTOR_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("authoritative working-tree collector is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_status(status: dict[str, Any]) -> None:
    STATUS_FILE.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _install_telemetry(declared: dict[str, Any]) -> None:
    from sweedit.core.llm import LLM
    from sweedit.tools.finish import Finish

    original_call = LLM.call

    async def capture_response(self, *args, **kwargs):
        response = await original_call(self, *args, **kwargs)
        usage = response.usage.model_dump() if getattr(response, "usage", None) else None
        record = {
            "model": response.model,
            "response_id": response.id,
            "created_at": response.created_at,
            "usage": usage,
        }
        with RESPONSE_LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return response

    LLM.call = capture_response
    original_finish = Finish.execute

    async def capture_finish(self, params):
        declared["finish_tool_calls"] += 1
        declared["messages"].append(str(params.message))
        return await original_finish(self, params)

    Finish.execute = capture_finish


def _isolate_api_credentials() -> None:
    import sweedit.core.agenthub as hub
    import sweedit.core.agenthub.swebench_agent as agent_module
    from sweedit.core.api_pool import _api_pool
    from sweedit.tools.execute_bash import ExecuteBashSWEBench

    original_agent = hub.SwebenchAgent

    class CredentialIsolatedBaseline(original_agent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.llm._api_config.pop("OPENAI_API_KEY", None)
            for config in _api_pool._pool:
                config.pop("OPENAI_API_KEY", None)
            for name in tuple(os.environ):
                if name == "OPENAI_API_KEY" or name.startswith("OPENAI_API_KEY_"):
                    os.environ.pop(name, None)
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.prctl(4, 0, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "Could not isolate API credentials from worker tools")

    hub.SwebenchAgent = CredentialIsolatedBaseline
    agent_module.SwebenchAgent = CredentialIsolatedBaseline
    ExecuteBashSWEBench.conda_prefix = (
        "if [ -f /opt/miniconda3/etc/profile.d/conda.sh ]; then "
        ". /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed; "
        "elif [ -x /opt/conda/bin/python ]; then export PATH=/opt/conda/bin:$PATH; "
        "fi"
    )


def _capture_on_signal(signum, _frame):
    raise SystemExit(128 + signum)


def main() -> None:
    collector = _load_collector()
    initial = collector.snapshot_working_tree(WORKDIR)
    declared = {"finish_tool_calls": 0, "messages": []}
    state: dict[str, Any] = {
        "schema_version": 2,
        **initial,
        "worker_declared_submission": declared,
        "termination_reason": "worker_running",
        "repository_state_recovered": False,
        "collector_error": None,
    }
    _write_status(state)
    if not initial["initial_tree_clean"]:
        raise RuntimeError(f"target worktree is not clean at worker start: {initial['initial_status_porcelain'][:8]}")

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, _capture_on_signal)
    reason = "bootstrap_initialization"
    try:
        _install_telemetry(declared)
        _isolate_api_credentials()
        os.environ["TASK_PROMPT"] = PROMPT_FILE.read_text(encoding="utf-8")
        RESPONSE_LOG.touch(mode=0o600, exist_ok=True)
        PATCH_FILE.touch(mode=0o600, exist_ok=True)
        reason = "agent_returned"
        runpy.run_path("/agent/evaluation/swebench-verified/run_agent.py", run_name="__main__")
        if declared["finish_tool_calls"]:
            reason = "finish_tool"
    except SystemExit as exc:
        reason = f"signal_or_system_exit:{exc.code}"
        raise
    except BaseException as exc:
        reason = f"agent_exception:{type(exc).__name__}"
        raise
    finally:
        try:
            collector.collect_working_tree(
                WORKDIR,
                initial,
                PATCH_FILE,
                STATUS_FILE,
                worker_declared_submission=declared,
                termination_reason=reason,
            )
        except BaseException as exc:
            state.update({
                "worker_declared_submission": declared,
                "termination_reason": reason,
                "repository_state_recovered": False,
                "collector_error": f"{type(exc).__name__}: {exc}",
            })
            _write_status(state)
            raise


if __name__ == "__main__":
    main()
