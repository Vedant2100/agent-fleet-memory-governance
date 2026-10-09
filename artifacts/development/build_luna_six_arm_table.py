#!/usr/bin/env python3
"""Combine the frozen Luna signal grades with the four paper treatment arms."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SIGNAL = ROOT / "artifacts/development/luna_oracle_signal_289648_test_filtered_regrade.json"
TREATMENTS = ROOT / "results/development/paper-treatments-luna/attempt-0003/treatment_results.jsonl"
OUT = TREATMENTS.parent
ARM_ORDER = (
    "A_NO_MEMORY", "B_SHARE_ALL", "C_RANDOM_MATCHED", "D_JEV_WRITE",
    "E_JEV_WRITE_READ", "F_ORACLE_RELATED_CEILING",
)
ARM_LABELS = {
    "A_NO_MEMORY": "No-Memory",
    "B_SHARE_ALL": "Share-All",
    "C_RANDOM_MATCHED": "Random-Matched",
    "D_JEV_WRITE": "Jev Write",
    "E_JEV_WRITE_READ": "Jev Write+Read",
    "F_ORACLE_RELATED_CEILING": "Oracle Ceiling",
}


def main() -> int:
    signal = json.loads(SIGNAL.read_text(encoding="utf-8"))
    target_ids = [row["target_id"] for row in signal["records"]]
    baseline = {row["target_id"]: row for row in signal["records"]}
    treatment_rows = [
        json.loads(line) for line in TREATMENTS.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    treatment_map = {}
    for row in treatment_rows:
        key = (row["target_id"], row["arm_id"])
        if key in treatment_map:
            raise RuntimeError(f"duplicate treatment grade: {key}")
        treatment_map[key] = _grade(row["grade"])

    expected = {(target_id, arm) for target_id in target_ids for arm in ARM_ORDER[1:5]}
    if set(treatment_map) != expected:
        missing = sorted(expected - set(treatment_map))
        extra = sorted(set(treatment_map) - expected)
        raise RuntimeError(f"treatment grade grid is incomplete: missing={missing}, extra={extra}")

    per_target = []
    for target_id in target_ids:
        source = baseline[target_id]
        arms = {
            "A_NO_MEMORY": _grade(source["no_memory"]),
            "B_SHARE_ALL": treatment_map[(target_id, "B_SHARE_ALL")],
            "C_RANDOM_MATCHED": treatment_map[(target_id, "C_RANDOM_MATCHED")],
            "D_JEV_WRITE": treatment_map[(target_id, "D_JEV_WRITE")],
            "E_JEV_WRITE_READ": treatment_map[(target_id, "E_JEV_WRITE_READ")],
            "F_ORACLE_RELATED_CEILING": _grade(source["oracle_related"]),
        }
        per_target.append({"target_id": target_id, "arms": arms})

    aggregates = {arm: _aggregate(arm, per_target) for arm in ARM_ORDER}
    result = {
        "schema_version": 1,
        "status": "COMPLETE_SIX_ARM_TABLE",
        "target_count": len(target_ids),
        "treatment_grade_count": len(treatment_rows),
        "signal_decision": signal["decision"],
        "signal_executable_discordant_targets": signal["executable_discordant_targets"],
        "signal_artifact": str(SIGNAL.relative_to(ROOT)),
        "treatment_artifact": str(TREATMENTS.relative_to(ROOT)),
        "arms": [{"arm_id": arm, "label": ARM_LABELS[arm], **aggregates[arm]} for arm in ARM_ORDER],
        "per_target": per_target,
    }
    json_path = OUT / "six_arm_paper_table.json"
    markdown_path = OUT / "six_arm_paper_table.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "targets": len(target_ids), "treatment_grades": len(treatment_rows), "json": str(json_path)}))
    return 0


def _grade(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_grade_available": value.get("canonical_grade_available"),
        "patch_applied": value.get("patch_applied"),
        "resolved": value.get("resolved"),
        "fail_to_pass_passed": value.get("fail_to_pass_passed"),
        "fail_to_pass_total": value.get("fail_to_pass_total"),
        "pass_to_pass_passed": value.get("pass_to_pass_passed"),
        "pass_to_pass_total": value.get("pass_to_pass_total"),
        "latency_seconds": value.get("latency_seconds"),
    }


def _aggregate(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    grades = [row["arms"][arm] for row in rows]
    return {
        "resolved_targets": sum(grade.get("resolved") is True for grade in grades),
        "patch_applied_targets": sum(grade.get("patch_applied") is True for grade in grades),
        "canonical_grade_targets": sum(grade.get("canonical_grade_available") is True for grade in grades),
        "fail_to_pass_passed": _sum_if_complete(grades, "fail_to_pass_passed"),
        "fail_to_pass_total": _sum_if_complete(grades, "fail_to_pass_total"),
        "pass_to_pass_passed": _sum_if_complete(grades, "pass_to_pass_passed"),
        "pass_to_pass_total": _sum_if_complete(grades, "pass_to_pass_total"),
    }


def _sum_if_complete(grades: list[dict[str, Any]], key: str) -> int | None:
    values = [grade.get(key) for grade in grades]
    return sum(values) if all(isinstance(value, int) for value in values) else None


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Luna six-arm paper table",
        "",
        f"Targets: {result['target_count']} · Treatment grades: {result['treatment_grade_count']} · Signal: {result['signal_decision']} ({result['signal_executable_discordant_targets']}/10)",
        "",
        "| Arm | Resolved | Applied | F2P passed / total | P2P passed / total |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in result["arms"]:
        lines.append(
            f"| {arm['label']} | {arm['resolved_targets']}/{result['target_count']} "
            f"| {arm['patch_applied_targets']}/{result['target_count']} "
            f"| {arm['fail_to_pass_passed']} / {arm['fail_to_pass_total']} "
            f"| {arm['pass_to_pass_passed']} / {arm['pass_to_pass_total']} |"
        )
    lines.extend(("", "## Per-target outcomes", "", "| Target | " + " | ".join(ARM_LABELS[arm] for arm in ARM_ORDER) + " |", "|---|" + "---:|" * len(ARM_ORDER)))
    for target in result["per_target"]:
        cells = []
        for arm in ARM_ORDER:
            grade = target["arms"][arm]
            status = "resolved" if grade.get("resolved") is True else "unresolved"
            f2p = f"{grade.get('fail_to_pass_passed')}/{grade.get('fail_to_pass_total')}"
            cells.append(f"{status}; F2P {f2p}")
        lines.append(f"| {target['target_id']} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
