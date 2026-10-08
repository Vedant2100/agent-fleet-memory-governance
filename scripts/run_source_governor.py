#!/usr/bin/env python3
"""Make and freeze one source-only write decision per unique candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fleet_mem_contextbench.governors.base import Decision
from fleet_mem_contextbench.governors.jev_system_one import JEV_MODEL, JevSystemOneGovernor
from fleet_mem_contextbench.governors.ollama_json import OllamaJSONGovernor
from fleet_mem_contextbench.pilot_runtime import analysis_target_ids, load_frozen_pilot, sha256_file
from fleet_mem_contextbench.treatments import (
    freeze_size_matched_random, validate_source_decisions,
)
from fleet_mem_contextbench.worker import preflight_ollama


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "artifacts/burned-pilot/plan.json"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())


def load_frozen_inputs(plan_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    plan, _, memories = load_frozen_pilot(plan_path)
    return plan, memories


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN_PATH)
    parser.add_argument("--governor", choices=("jev", "llm"), required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/burned-pilot/governors")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen2.5:32b")
    args = parser.parse_args()

    if not os.environ.get("SLURM_JOB_ID"):
        raise RuntimeError("Source-time decisions must run in the preregistered Slurm allocation")
    if args.governor == "llm" and os.environ.get("OLLAMA_NO_CLOUD") != "1":
        raise RuntimeError("local deliberative governor requires OLLAMA_NO_CLOUD=1")

    plan, memories = load_frozen_inputs(args.plan)
    if args.governor == "jev":
        _require_prequalification(args.plan)
    else:
        _require_write_exposure_gate(args.plan, args.output_dir)
    output = args.output_dir.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    journal = output / f"{args.governor}_write_journal.jsonl"
    decisions_path = output / f"{args.governor}_write_decisions.jsonl"
    summary_path = output / f"{args.governor}_write_summary.json"
    lock = output / f".{args.governor}_write.lock"
    if any(path.exists() for path in (journal, decisions_path, summary_path, lock)):
        raise RuntimeError(
            f"{args.governor} source-write run already has artifacts; refusing to repeat any candidate call"
        )
    if args.governor == "jev":
        governor = JevSystemOneGovernor()
        runtime = {"provider": "TypeSafe System One", "model": JEV_MODEL, "retry_policy": "zero retries"}
    else:
        runtime = ollama_preflight(args.ollama_base_url, args.model)
        governor = OllamaJSONGovernor(model=args.model, base_url=args.ollama_base_url)

    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(descriptor, f"pid={os.getpid()}\nstarted={datetime.now(timezone.utc).isoformat()}\n".encode())
    os.fsync(descriptor)
    os.close(descriptor)

    rows: list[dict[str, Any]] = []
    source_order = sorted(
        memories.items(),
        key=lambda pair: (pair[1].get("created_at") or "", pair[1]["source_task_id"], pair[0]),
    )
    try:
        for index, (memory_id, memory) in enumerate(source_order, start=1):
            candidate_hash = sha256_text(canonical(memory))
            append_jsonl(journal, {
                "event": "CALL_STARTED",
                "ordinal": index,
                "memory_id": memory_id,
                "candidate_sha256": candidate_hash,
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            try:
                decision = governor.decide_write(memory)
                if not isinstance(decision, Decision):
                    raise TypeError("governor returned a non-Decision object")
                decision.validate("write")
            except Exception as exc:
                append_jsonl(journal, {
                    "event": "CALL_FAILED",
                    "ordinal": index,
                    "memory_id": memory_id,
                    "candidate_sha256": candidate_hash,
                    "error_type": type(exc).__name__,
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                })
                raise RuntimeError(
                    f"{args.governor} failed on candidate {index}/{len(memories)}; no retry was attempted"
                ) from exc
            row = {
                "memory_id": memory_id,
                "source_task_id": memory["source_task_id"],
                "candidate_sha256": candidate_hash,
                "action": decision.action,
                "confidence": decision.confidence,
                "probabilities": decision.probabilities,
                "rationale": decision.rationale,
                "latency_ms": decision.latency_ms,
                "cost": decision.cost,
                "input_tokens": decision.input_tokens,
                "output_tokens": decision.output_tokens,
                "governor": governor.name,
            }
            append_jsonl(journal, {
                "event": "DECISION_RECORDED",
                "ordinal": index,
                "memory_id": memory_id,
                "candidate_sha256": candidate_hash,
                "action": decision.action,
                "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            rows.append(row)
            print(json.dumps({"governor": args.governor, "candidate": index, "total": len(memories), "action": decision.action}))

        validate_source_decisions(memories, rows)
        _write_jsonl_exclusive(decisions_path, rows)
        summary = {
            "schema_version": 1,
            "stage": "SOURCE_TIME_WRITE_GOVERNANCE",
            "status": "COMPLETE",
            "governor": args.governor,
            "governor_name": governor.name,
            "plan_sha256": sha256_file(args.plan),
            "source_union_sha256": plan["unique_source_memory_union_sha256"],
            "source_candidate_count": len(memories),
            "call_count": len(rows),
            "action_counts": {action: sum(row["action"] == action for row in rows) for action in ("SHARE", "DO_NOT_SHARE")},
            "share_rate": sum(row["action"] == "SHARE" for row in rows) / len(rows),
            "input_tokens": _sum_known(rows, "input_tokens"),
            "output_tokens": _sum_known(rows, "output_tokens"),
            "latency_ms_sum": _sum_known(rows, "latency_ms"),
            "cost_sum": _sum_known(rows, "cost"),
            "runtime": runtime,
            "decisions_sha256": sha256_file(decisions_path),
            "journal_sha256": sha256_file(journal),
            "decision_time_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_json_exclusive(summary_path, summary)
        if args.governor == "jev":
            random_rows = freeze_size_matched_random(memories, rows, seed=42)
            random_path = output / "random_matched_write_decisions.jsonl"
            _write_jsonl_exclusive(random_path, random_rows)
            summary["random_match"] = {
                "admitted_count": sum(row["action"] == "SHARE" for row in random_rows),
                "seed": 42,
                "decisions_sha256": sha256_file(random_path),
            }
            _replace_json(summary_path, summary)
        print(json.dumps({"status": "COMPLETE", "summary": str(summary_path), **summary["action_counts"]}, indent=2))
        return 0
    finally:
        lock.unlink(missing_ok=True)


def ollama_preflight(base_url: str, model: str) -> dict[str, Any]:
    return {"provider": "local Ollama", "network_scope": "127.0.0.1 only", **preflight_ollama(base_url, model)}


def _require_prequalification(plan_path: Path) -> None:
    plan_hash = sha256_file(plan_path)
    controls_path = ROOT / "artifacts/burned-pilot/controls_summary.json"
    qualification_path = ROOT / "artifacts/burned-pilot/qualification.json"
    primary_ids = analysis_target_ids(json.loads(plan_path.read_text(encoding="utf-8")))
    controls = json.loads(controls_path.read_text(encoding="utf-8"))
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    if (
        controls.get("plan_sha256") != plan_hash
        or controls.get("all_controls_passed") is not True
        or controls.get("target_count") != len(primary_ids)
        or controls.get("target_ids") != primary_ids
        or controls.get("control_count") != 2 * len(primary_ids)
        or qualification.get("plan_sha256") != plan_hash
        or qualification.get("status") != "PASS"
    ):
        raise RuntimeError("Jev write decisions require passing canonical controls and worker qualification")


def _require_write_exposure_gate(plan_path: Path, output_dir: Path) -> None:
    gate_path = ROOT / "artifacts/burned-pilot/exposure_write_gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    required = json.loads(plan_path.read_text(encoding="utf-8"))["stop_rules"][
        "minimum_shareall_vs_jev_exposure_discordance_targets"
    ]
    required_read = json.loads(plan_path.read_text(encoding="utf-8"))["stop_rules"][
        "minimum_jev_read_eligible_targets"
    ]
    if (
        gate.get("status") != "PASS_WRITE_EXPOSURE_GATE"
        or gate.get("plan_sha256") != sha256_file(plan_path)
        or gate.get("jev_decisions_sha256") != sha256_file(output_dir / "jev_write_decisions.jsonl")
        or gate.get("random_decisions_sha256") != sha256_file(output_dir / "random_matched_write_decisions.jsonl")
        or gate.get("targets_with_shareall_vs_jev_exposure_difference", 0) < required
        or gate.get("targets_with_jev_read_eligibility", 0) < required_read
    ):
        raise RuntimeError("deliberative LLM write arm requires a passing frozen Jev exposure gate")


def _sum_known(rows: list[dict[str, Any]], key: str) -> int | float | None:
    values = [row.get(key) for row in rows]
    return sum(values) if values and all(isinstance(value, (int, float)) for value in values) else (0 if not values else None)


def _write_jsonl_exclusive(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _write_json_exclusive(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _replace_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
