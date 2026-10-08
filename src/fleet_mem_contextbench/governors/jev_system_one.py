"""Source-only and target-time System-One/Jev decisions.

The package is imported lazily so deterministic and local-LLM tests do not
require the optional TypeSafe SDK.
"""

from __future__ import annotations

import os
import shlex
import stat
from pathlib import Path
from typing import Any, Sequence

from .base import Decision
from .adapters import _assert_no_target


JEV_MODEL = "jev-1.13.0"
SDK_VERSION = "0.7.2"
WRITE_CRITERIA = {
    "SHARE": (
        "The source evidence supports a useful, bounded repository memory that can be "
        "safely shared with later coding workers; its scope and preconditions are clear."
    ),
    "DO_NOT_SHARE": (
        "The information is specific to this repair, weakly supported, stale, too broad, "
        "unclear in scope, redundant, or carries material negative-transfer risk."
    ),
}
READ_CRITERIA = {
    "EXPOSE": "The source memory has a concrete scope/evidence match and can help this task.",
    "WITHHOLD": "It is irrelevant, unsupported, stale, redundant, conflicting, or risks misleading this task.",
}


def load_jev_api_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if key:
        return key
    config_path = Path(os.environ.get(
        "FLEET_MEM_JEV_CONFIG",
        Path.home() / ".config/fleet-mem-contextbench/jev.env",
    ))
    if config_path.is_symlink() or not config_path.is_file():
        raise RuntimeError(
            "Jev credential unavailable. Configure a fresh key with "
            "scripts/configure_jev_credentials.py in a private terminal."
        )
    mode = stat.S_IMODE(config_path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(f"Jev config permissions must be 600: {config_path}")
    assignments = []
    for line in config_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("TYPESAFE_API_KEY="):
            values = shlex.split(line.split("=", 1)[1], comments=False)
            if len(values) != 1:
                raise RuntimeError("Malformed Jev credential config")
            assignments.append(values[0])
    if len(assignments) != 1 or not assignments[0]:
        raise RuntimeError("Jev config must contain exactly one nonempty key")
    return assignments[0]


class JevSystemOneGovernor:
    """Typed binary Jev governor; write calls never receive target information."""

    name = "jev_system_one"

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 90):
        try:
            from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient, __version__
        except ImportError as exc:
            raise RuntimeError("Install the optional Jev dependency: typesafe-sdk==0.7.2") from exc
        if __version__ != SDK_VERSION:
            raise RuntimeError(f"Expected typesafe-sdk {SDK_VERSION}; found {__version__}")
        self._Choice = Choice
        self._RetryPolicy = RetryPolicy
        self._client = TypeSafeClient(
            api_key=api_key or load_jev_api_key(), model=JEV_MODEL,
            retry=RetryPolicy(max_retries=0), timeout=timeout_seconds,
        )

    def decide_write(self, candidate: dict[str, Any]) -> Decision:
        _assert_no_target(candidate)
        prompt = {
            "source_memory": _source_card(candidate),
            "instruction": (
                "Make a one-time organizational write decision using only this source experience. "
                "Do not infer any future task or future usefulness. Prefer a narrow, evidence-backed "
                "memory that later workers can verify."
            ),
        }
        return self._ask(prompt, "write_admission", WRITE_CRITERIA, "write")

    def decide_read(self, target: dict[str, Any], pool: Sequence[dict[str, Any]]) -> list[Decision]:
        decisions = []
        public_target = {
            "repository": target.get("repository"),
            "problem_statement": target.get("problem_statement"),
            "base_commit": target.get("base_commit"),
        }
        for memory in pool:
            _assert_no_target(memory)
            prompt = {
                "target_task": public_target,
                "candidate_memory": _source_card(memory),
                "instruction": (
                    "For this target task only, choose whether to expose the complete memory. "
                    "Judge scope, evidence, redundancy, and plausible negative transfer."
                ),
            }
            decisions.append(self._ask(prompt, "target_exposure", READ_CRITERIA, "read"))
        return decisions

    def _ask(
        self, state: dict[str, Any], question_name: str, criteria: dict[str, str], stage: str,
    ) -> Decision:
        from time import perf_counter

        question = self._Choice(
            instructions=(
                "Choose the single best categorical action. Evaluate the supplied evidence only. "
                "Do not add an action outside the listed choices."
            ),
            criteria=criteria,
        )
        started = perf_counter()
        response = self._client.system_one(
            state=state,
            questions={question_name: question},
            model=JEV_MODEL,
            retry=self._RetryPolicy(max_retries=0),
            timeout=90,
        )
        latency_ms = (perf_counter() - started) * 1000
        if response.model != JEV_MODEL:
            raise RuntimeError(f"Expected {JEV_MODEL}; received {response.model}")
        answer = response.choices.get(question_name)
        if answer is None:
            raise RuntimeError(f"Jev omitted structured choice {question_name}")
        action = str(answer.choice)
        usage = response.usage
        decision = Decision(
            action=action,
            confidence=_optional_float(getattr(answer, "confidence", None)),
            rationale=str(getattr(answer, "rationale", "") or ""),
            latency_ms=latency_ms,
            cost=_usage_cost(usage),
            input_tokens=_optional_int(getattr(usage, "input_tokens", None)),
            output_tokens=_optional_int(getattr(usage, "output_tokens", None)),
        )
        decision.validate(stage)
        return decision


def _source_card(memory: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "memory_id", "source_task_id", "repository", "source_outcome", "created_at", "claim",
        "memory_type", "scope", "preconditions", "evidence", "evidence_locations",
        "files_or_symbols", "generality", "negative_transfer_risk", "provenance_hash",
    )
    return {key: memory[key] for key in allowed if key in memory}


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _usage_cost(usage: Any) -> float | None:
    for name in ("cost", "estimated_cost", "estimated_cost_usd"):
        value = _optional_float(getattr(usage, name, None))
        if value is not None:
            return value
    return None
