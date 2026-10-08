"""Paired arm exposure and executable target runner interfaces."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from .build import CONTEXTBENCH_COMMIT
from .governors.base import Decision, Governor
from .governors.deterministic import ShareAllPolicy, fixed_read
from .manifest import ARMS


class TargetSolver(Protocol):
    def solve(self, target: dict[str, Any], exposed_memories: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]: ...


class CanonicalEvaluator(Protocol):
    def evaluate(self, target_id: str, predictions_dir: Path, run_id: str) -> dict[str, Any]: ...


@dataclass
class Exposure:
    arm_id: str
    shared_memory_ids: list[str]
    exposed_memory_ids: list[str]
    write_actions: dict[str, str]
    read_actions: dict[str, str]
    write_decision_details: dict[str, dict[str, Any]]
    read_decision_details: dict[str, dict[str, Any]]
    read_abstention_rate: float
    write_admission_rate: float
    memory_tokens_exposed: int
    memory_token_count_method: str
    governor_latency_ms: float
    governor_cost: float
    exposed_memories: list[dict[str, Any]]


def compute_exposure(
    target: dict[str, Any], pool: dict[str, Any], arm_id: str, governor: Governor,
    token_counter: Any | None = None, related_source_ids: set[str] | None = None,
) -> Exposure:
    candidates = pool["candidate_pool"]
    memories = [row["memory"] for row in candidates]
    if arm_id == "A_NO_MEMORY":
        shared, write_actions, writes, reads = [], {}, [], []
    elif arm_id in {"B_SHARE_ALL_FIXED_READ", "D_SHARE_ALL_GOVERNED_READ"}:
        shared = memories
        write_actions = {memory["memory_id"]: "SHARE" for memory in memories}
        writes = [Decision("SHARE", confidence=1.0, rationale="Share-All control") for _ in memories]
        read_policy = "FIXED" if arm_id.startswith("B_") else "GOVERNED"
        reads = fixed_read(target, shared) if read_policy == "FIXED" else list(governor.decide_read(target, shared))
    elif arm_id in {"C_GOVERNED_WRITE_FIXED_READ", "E_GOVERNED_WRITE_GOVERNED_READ"}:
        write_actions = {}
        writes = []
        for memory in memories:
            decision = governor.decide_write(memory)
            decision.validate("write")
            write_actions[memory["memory_id"]] = decision.action
            writes.append(decision)
        shared = [memory for memory in memories if write_actions[memory["memory_id"]] == "SHARE"]
        read_policy = "FIXED" if arm_id.startswith("C_") else "GOVERNED"
        reads = fixed_read(target, shared) if read_policy == "FIXED" else list(governor.decide_read(target, shared))
    elif arm_id == "F_ORACLE_RELATED_MEMORY_CEILING":
        if related_source_ids is None:
            raise ValueError("oracle ceiling requires hidden known-related source IDs")
        shared = [memory for memory in memories if memory["source_task_id"] in related_source_ids]
        write_actions = {memory["memory_id"]: "SHARE" for memory in shared}
        writes = [Decision("SHARE", confidence=1.0, rationale="oracle relation ceiling") for _ in shared]
        reads = [Decision("EXPOSE", confidence=1.0, rationale="oracle known-related ceiling") for _ in shared]
    else:
        raise ValueError(f"unknown arm: {arm_id}")
    if len(reads) != len(shared):
        raise ValueError(f"{arm_id}: read policy did not return one decision per shared candidate")
    for decision in reads:
        decision.validate("read")
    exposed = [memory for memory, decision in zip(shared, reads) if decision.action == "EXPOSE"]
    abstentions = sum(decision.action == "WITHHOLD" for decision in reads)
    token_count = token_counter or (lambda value: max(1, len(json.dumps(value, ensure_ascii=False)) // 4))
    if arm_id == "F_ORACLE_RELATED_MEMORY_CEILING":
        exposed = [_concise_oracle_memory(memory) for memory in exposed]
    write_details = {
        memory_id: _decision_record(writes[index])
        for index, memory_id in enumerate(write_actions)
    } if writes else {}
    read_details = {
        memory["memory_id"]: _decision_record(decision)
        for memory, decision in zip(shared, reads)
    }
    return Exposure(
        arm_id=arm_id,
        shared_memory_ids=sorted(memory["memory_id"] for memory in shared),
        exposed_memory_ids=[memory["memory_id"] for memory in exposed],
        write_actions=write_actions,
        read_actions={memory["memory_id"]: decision.action for memory, decision in zip(shared, reads)},
        write_decision_details=write_details,
        read_decision_details=read_details,
        read_abstention_rate=abstentions / len(reads) if reads else 1.0,
        write_admission_rate=sum(action == "SHARE" for action in write_actions.values()) / len(write_actions) if write_actions else 0.0,
        memory_tokens_exposed=sum(token_count(memory) for memory in exposed),
        memory_token_count_method=("CUSTOM_TOKEN_COUNTER" if token_counter else "JSON_CHARACTER_COUNT_DIVIDED_BY_FOUR_ESTIMATE"),
        governor_latency_ms=sum(decision.latency_ms or 0 for decision in writes + list(reads)),
        governor_cost=sum(decision.cost or 0 for decision in writes + list(reads)),
        exposed_memories=exposed,
    )


def exposure_gate(exposures: Sequence[Exposure]) -> dict[str, Any]:
    by_arm = {row.arm_id: row for row in exposures}
    comparisons = {}
    for left, right in (
        ("B_SHARE_ALL_FIXED_READ", "C_GOVERNED_WRITE_FIXED_READ"),
        ("D_SHARE_ALL_GOVERNED_READ", "E_GOVERNED_WRITE_GOVERNED_READ"),
    ):
        if left not in by_arm or right not in by_arm:
            continue
        a, b = by_arm[left], by_arm[right]
        comparisons[f"{left}_vs_{right}"] = {
            "shared_pool_differs": set(a.shared_memory_ids) != set(b.shared_memory_ids),
            "target_exposure_differs": set(a.exposed_memory_ids) != set(b.exposed_memory_ids),
            "left_shared_count": len(a.shared_memory_ids), "right_shared_count": len(b.shared_memory_ids),
            "left_exposed_count": len(a.exposed_memory_ids), "right_exposed_count": len(b.exposed_memory_ids),
            "symmetric_difference_exposed": sorted(set(a.exposed_memory_ids) ^ set(b.exposed_memory_ids)),
        }
    return comparisons


class CommandSolver:
    """Run a fixed JSON-in/JSON-out solver command once for one arm/target."""

    def __init__(self, command: str, timeout_seconds: int = 3600):
        self.command = shlex.split(command)
        self.timeout_seconds = timeout_seconds

    def solve(self, target: dict[str, Any], exposed_memories: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        request = {"target": target, "memories": exposed_memories, "output_dir": str(output_dir)}
        started = time.monotonic()
        result = subprocess.run(
            self.command, input=json.dumps(request), text=True, capture_output=True,
            timeout=self.timeout_seconds, check=False,
        )
        latency = time.monotonic() - started
        if result.returncode:
            raise RuntimeError(f"solver failed ({result.returncode}): {result.stderr[-2000:]}")
        response = json.loads(result.stdout)
        response.setdefault("agent_latency_seconds", latency)
        response.setdefault("solver_stderr", result.stderr[-1000:])
        return response


class SWEContextBenchOfficialEvaluator:
    """Run upstream evaluation.sh in an isolated workspace; keep its scorer unchanged."""

    def __init__(self, contextbench_root: str | Path, timeout_seconds: int = 86400):
        self.contextbench_root = Path(contextbench_root).resolve(strict=True)
        self.timeout_seconds = timeout_seconds
        if not (self.contextbench_root / "evaluation.sh").is_file() or not (self.contextbench_root / "cases").is_dir():
            raise ValueError("contextbench_root must be the pinned SWE-ContextBench checkout")
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=self.contextbench_root, text=True, stderr=subprocess.PIPE,
            ).strip()
            dirty = subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=self.contextbench_root, text=True, stderr=subprocess.PIPE,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("contextbench_root must be an inspectable Git checkout") from exc
        if commit != CONTEXTBENCH_COMMIT or dirty:
            raise ValueError(
                f"expected clean SWE-ContextBench commit {CONTEXTBENCH_COMMIT}; found {commit}"
                + (" with working-tree changes" if dirty else "")
            )

    def preflight(self) -> None:
        """Fail before a solver run if the unchanged upstream Docker grader cannot start."""
        if shutil.which("docker") is None:
            raise RuntimeError("SWE-ContextBench evaluation.sh requires Docker; docker executable is unavailable")
        result = subprocess.run(["docker", "info"], text=True, capture_output=True, timeout=30, check=False)
        if result.returncode:
            raise RuntimeError(f"Docker daemon preflight failed: {result.stderr[-1000:]}")

    def evaluate(self, target_id: str, predictions_dir: Path, run_id: str) -> dict[str, Any]:
        started = time.monotonic()
        saved_root = predictions_dir.parent / "canonical_evaluator"
        saved_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="fmc-eval-", dir=predictions_dir.parent) as temp_name:
            work = Path(temp_name)
            (work / "cases").symlink_to(self.contextbench_root / "cases", target_is_directory=True)
            env = os.environ.copy()
            previous_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = str(self.contextbench_root) + (os.pathsep + previous_pythonpath if previous_pythonpath else "")
            command = [
                "bash", str(self.contextbench_root / "evaluation.sh"),
                run_id, "lite", str(predictions_dir.resolve()),
            ]
            result = subprocess.run(
                command, cwd=work, env=env, text=True, capture_output=True,
                timeout=self.timeout_seconds, check=False,
            )
            report_path = work / f"{run_id}.json"
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
            shutil.copy2(report_path, saved_root / report_path.name) if report_path.exists() else None
            (saved_root / f"{run_id}.stdout.txt").write_text(result.stdout, encoding="utf-8")
            (saved_root / f"{run_id}.stderr.txt").write_text(result.stderr, encoding="utf-8")
            logs = work / "logs" / "run_evaluation" / run_id
            if logs.is_dir():
                shutil.copytree(logs, saved_root / "logs" / run_id, dirs_exist_ok=True)
        task_report = report.get(target_id, {})
        tests = task_report.get("tests_status", {})
        fail = tests.get("FAIL_TO_PASS", {})
        preserve = tests.get("PASS_TO_PASS", {})
        fail_passed = len(fail.get("success", []))
        fail_total = fail_passed + len(fail.get("failure", []))
        preserve_passed = len(preserve.get("success", []))
        preserve_total = preserve_passed + len(preserve.get("failure", []))
        return {
            "evaluator": "SWE-ContextBench evaluation.sh lite",
            "exit_code": result.returncode, "latency_seconds": time.monotonic() - started,
            "stdout_tail": result.stdout[-4000:], "stderr_tail": result.stderr[-4000:],
            "canonical_grade_available": result.returncode == 0 and target_id in report,
            "resolved": task_report.get("resolved"),
            "patch_applied": task_report.get("patch_applied"),
            "fail_to_pass_passed": fail_passed, "fail_to_pass_total": fail_total,
            "pass_to_pass_passed": preserve_passed, "pass_to_pass_total": preserve_total,
            "official_report_path": str(saved_root / report_path.name) if report_path.exists() else None,
        }


def run_paired_target(
    target: dict[str, Any], pool: dict[str, Any], governor: Governor,
    solver: TargetSolver, evaluator: CanonicalEvaluator, output_root: str | Path,
    arms: Sequence[str] = tuple(row["arm_id"] for row in ARMS[:5]),
    related_source_ids: set[str] | None = None,
    token_counter: Any | None = None,
) -> list[dict[str, Any]]:
    root = Path(output_root)
    results: list[dict[str, Any]] = []
    for arm_id in arms:
        exposure = compute_exposure(
            target, pool, arm_id, governor, token_counter=token_counter,
            related_source_ids=related_source_ids,
        )
        run_dir = root / target["target_id"] / arm_id
        predictions_dir = run_dir / "predictions"
        prediction = solver.solve(target, exposure.exposed_memories, run_dir)
        patch = prediction.get("patch")
        if not isinstance(patch, str):
            raise ValueError("solver response must contain a patch string")
        predictions_dir.mkdir(parents=True, exist_ok=True)
        (predictions_dir / f"{target['target_id']}_preds.json").write_text(json.dumps({
            target["target_id"]: {
                "model_name_or_path": prediction.get("model_name_or_path", "configured_solver"),
                "instance_id": target["target_id"], "model_patch": patch,
            }
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        grade = evaluator.evaluate(target["target_id"], predictions_dir, f"{target['target_id']}-{arm_id.lower()}")
        result = {
            "target_id": target["target_id"], "arm_id": arm_id,
            "governor": governor.name, "candidate_pool_size": pool["candidate_count"],
            "shared_memory_ids": exposure.shared_memory_ids,
            "exposed_memory_ids": exposure.exposed_memory_ids,
            "write_actions": exposure.write_actions, "read_actions": exposure.read_actions,
            "write_decision_details": exposure.write_decision_details,
            "read_decision_details": exposure.read_decision_details,
            "read_abstention_rate": exposure.read_abstention_rate,
            "write_admission_rate": exposure.write_admission_rate,
            "memory_tokens_exposed": exposure.memory_tokens_exposed,
            "memory_token_count_method": exposure.memory_token_count_method,
            "resolved": grade.get("resolved"), "pass_at_1": grade.get("resolved"),
            "fail_to_pass_passed": grade.get("fail_to_pass_passed"),
            "fail_to_pass_total": grade.get("fail_to_pass_total"),
            "pass_to_pass_passed": grade.get("pass_to_pass_passed"),
            "pass_to_pass_total": grade.get("pass_to_pass_total"),
            "tokens": prediction.get("tokens"), "steps": prediction.get("steps"),
            "tool_calls": prediction.get("tool_calls"),
            "agent_latency_seconds": prediction.get("agent_latency_seconds"),
            "cost": prediction.get("cost"),
            "governor_latency_ms": exposure.governor_latency_ms,
            "governor_cost": exposure.governor_cost,
            "solver_metrics": {key: prediction.get(key) for key in (
                "tokens", "steps", "tool_calls", "agent_latency_seconds", "cost",
            )},
            "grade": grade,
        }
        (run_dir / "run_record.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        results.append(result)
    return results


def _decision_record(decision: Decision) -> dict[str, Any]:
    return {
        "action": decision.action, "confidence": decision.confidence,
        "probabilities": decision.probabilities, "rationale": decision.rationale,
        "latency_ms": decision.latency_ms, "cost": decision.cost,
    }


def _concise_oracle_memory(memory: dict[str, Any]) -> dict[str, Any]:
    """Expose a short relation-oracle card while preserving its source provenance."""
    return {
        "memory_id": memory["memory_id"], "source_task_id": memory["source_task_id"],
        "repository": memory["repository"], "source_outcome": memory["source_outcome"],
        "created_at": memory["created_at"], "claim": str(memory["claim"])[:240],
        "memory_type": memory["memory_type"], "scope": memory["scope"],
        "preconditions": "Check the current code and tests before reuse.",
        "evidence": list(memory["evidence"][:1]),
        "evidence_locations": list(memory["evidence_locations"][:3]),
        "files_or_symbols": list(memory["files_or_symbols"][:3]),
        "provenance_hash": memory["provenance_hash"], "source_mode": memory["source_mode"],
        "oracle_concise": True,
    }


def transfer_vs_no_memory(treatment: dict[str, Any], baseline: dict[str, Any]) -> dict[str, bool | None]:
    """Compare a treatment's executable result with the paired no-memory result."""
    treatment_grade, baseline_grade = treatment.get("grade", {}), baseline.get("grade", {})
    treated_resolved = treatment_grade.get("resolved")
    baseline_resolved = baseline_grade.get("resolved")
    if not treatment_grade.get("canonical_grade_available") or not baseline_grade.get("canonical_grade_available"):
        return {key: None for key in (
            "positive_transfer", "negative_transfer", "preserved_success", "persistent_failure",
        )}
    f2p_delta = int(treatment_grade.get("fail_to_pass_passed", 0)) - int(baseline_grade.get("fail_to_pass_passed", 0))
    p2p_delta = int(treatment_grade.get("pass_to_pass_passed", 0)) - int(baseline_grade.get("pass_to_pass_passed", 0))
    negative = bool((baseline_resolved and not treated_resolved) or f2p_delta < 0 or p2p_delta < 0)
    positive = bool(not negative and ((treated_resolved and not baseline_resolved) or f2p_delta > 0))
    preserved = bool(baseline_resolved and treated_resolved and p2p_delta == 0 and f2p_delta >= 0)
    persistent = bool(not baseline_resolved and not treated_resolved and f2p_delta <= 0)
    return {
        "positive_transfer": positive, "negative_transfer": negative,
        "preserved_success": preserved, "persistent_failure": persistent,
    }
