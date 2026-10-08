#!/usr/bin/env python3
"""Model-free end-to-end tests for authoritative SWE-Edit patch collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Keep the read-only upstream ContextBench checkout free of imported bytecode.
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fleet_mem_contextbench.apptainer_evaluator import (  # noqa: E402
    SWEContextBenchApptainerEvaluator,
    semantic_noop_patch,
)
from run_sweedit_burned import _prediction_patch  # noqa: E402


TARGET_ID = "sympy__sympy-19235"
EDIT_PATH = "sympy/core/basic.py"
EDIT_MARKER = "# fmc-authoritative-output-boundary-fixture"


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sif = (args.sif_dir / f"{TARGET_ID}.sif").resolve(strict=True)
    evaluator = SWEContextBenchApptainerEvaluator(
        args.contextbench_root, args.targets_parquet, args.sif_dir, args.job_tmp,
    )
    evaluator.preflight([TARGET_ID])
    rows = [
        _run_fixture("known_edit_no_marker", True, sif, args.apptainer, output, evaluator),
        _run_fixture("empty_tree_no_marker", False, sif, args.apptainer, output, evaluator),
    ]
    summary = {
        "schema_version": 1,
        "validation": "AUTHORITATIVE_OUTPUT_BOUNDARY_MODEL_FREE",
        "target_id": TARGET_ID,
        "target_sif": str(sif),
        "target_sif_sha256": _sha256_file(sif),
        "fixtures": rows,
        "both_fixtures_passed": all(row["passed"] for row in rows),
    }
    summary_path = output / "output_boundary_validation.json"
    _write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["both_fixtures_passed"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contextbench-root", type=Path, required=True)
    parser.add_argument("--targets-parquet", type=Path, required=True)
    parser.add_argument("--sif-dir", type=Path, default=ROOT / "artifacts/burned-pilot/images")
    parser.add_argument("--job-tmp", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apptainer", default="/usr/bin/apptainer")
    return parser.parse_args()


def _run_fixture(name, edit_source, sif, apptainer, output, evaluator):
    fixture_dir = output / name
    fixture_dir.mkdir(mode=0o700)
    (fixture_dir / "working_tree.py").write_bytes(
        (ROOT / "src/fleet_mem_contextbench/working_tree.py").read_bytes()
    )
    _write_capture_script(fixture_dir / "capture.py")
    result = subprocess.run(
        [
            apptainer, "exec", "--cleanenv", "--containall", "--no-home", "--fakeroot",
            "--writable-tmpfs", "--pwd", "/tmp", "--bind", f"{fixture_dir}:/tmp/fmc-boundary:rw",
            str(sif), "python3", "/tmp/fmc-boundary/capture.py",
            "edit" if edit_source else "empty", EDIT_PATH, EDIT_MARKER,
        ],
        check=False, capture_output=True, text=True, timeout=180,
    )
    (fixture_dir / "container.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (fixture_dir / "container.stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"{name}: Apptainer fixture exited {result.returncode}: {result.stderr[-1200:]}")

    metadata = json.loads((fixture_dir / "worker_status.json").read_text(encoding="utf-8"))
    captured = (fixture_dir / "prediction.patch").read_bytes()
    expected = (fixture_dir / "expected.diff").read_bytes()
    if captured != expected:
        raise AssertionError(f"{name}: collector diff differs from expected repository diff")

    worker = {
        "repository_state_recovered": metadata.get("repository_state_recovered"),
        "patch_path": str(fixture_dir / "prediction.patch"),
    }
    prediction = _prediction_patch(worker)
    if edit_source and prediction.encode() != expected:
        raise AssertionError("known-edit prediction was not the exact captured repository diff")
    if not edit_source and prediction != semantic_noop_patch():
        raise AssertionError("empty tree did not route through the frozen semantic no-op")

    grade = evaluator.evaluate(
        TARGET_ID,
        prediction,
        run_id=f"output-boundary-{name}",
        output_dir=fixture_dir / "evaluation",
    )
    received_sha = hashlib.sha256(prediction.encode("utf-8")).hexdigest()
    passed = (
        metadata.get("repository_state_recovered") is True
        and grade.get("canonical_grade_available") is True
        and grade.get("patch_applied") is True
        and grade.get("model_patch_sha256") == received_sha
    )
    if edit_source:
        passed = passed and metadata.get("tracked_source_files_changed") is True
        passed = passed and metadata.get("tracked_source_files") == [EDIT_PATH]
        passed = passed and EDIT_MARKER.encode() in captured
    else:
        passed = passed and not captured
        passed = passed and metadata.get("tracked_source_files_changed") is False
        passed = passed and not metadata.get("git_status_porcelain")
    if not passed:
        raise AssertionError(f"{name}: authoritative collection/evaluator assertion failed")

    return {
        "fixture": name,
        "worker_declared_submission": metadata["worker_declared_submission"],
        "git_status_porcelain": metadata["git_status_porcelain"],
        "tracked_source_files_changed": metadata["tracked_source_files_changed"],
        "authoritative_diff_bytes": len(captured),
        "authoritative_diff_sha256": hashlib.sha256(captured).hexdigest(),
        "evaluator_received_patch_sha256": received_sha,
        "canonical_grade_available": grade["canonical_grade_available"],
        "patch_applied": grade["patch_applied"],
        "resolved": grade["resolved"],
        "fail_to_pass": [grade["fail_to_pass_passed"], grade["fail_to_pass_total"]],
        "pass_to_pass": [grade["pass_to_pass_passed"], grade["pass_to_pass_total"]],
        "passed": passed,
    }


def _write_capture_script(path: Path) -> None:
    path.write_text(
        "\n".join([
            "import json, subprocess, sys",
            "from pathlib import Path",
            "sys.path.insert(0, '/tmp/fmc-boundary')",
            "from working_tree import collect_working_tree, snapshot_working_tree",
            "mode, relpath, marker = sys.argv[1:]",
            "repo = Path('/testbed')",
            "initial = snapshot_working_tree(repo)",
            "if not initial['initial_tree_clean']:",
            "    raise RuntimeError(f'fixture checkout not clean: {initial[\"initial_status_porcelain\"]}')",
            "if mode == 'edit':",
            "    target = repo / relpath",
            "    subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', f'HEAD:{relpath}'], check=True)",
            "    with target.open('a', encoding='utf-8') as stream:",
            "        stream.write('\\n' + marker + '\\n')",
            "expected = subprocess.run(",
            "    ['git', '-C', str(repo), 'diff', '--binary', '--no-ext-diff', '--full-index', initial['initial_repository_commit'], '--'],",
            "    check=True, capture_output=True).stdout",
            "Path('/tmp/fmc-boundary/expected.diff').write_bytes(expected)",
            "collect_working_tree(",
            "    repo, initial, '/tmp/fmc-boundary/prediction.patch', '/tmp/fmc-boundary/worker_status.json',",
            "    worker_declared_submission={'finish_tool_calls': 0, 'messages': []},",
            "    termination_reason='fixture_terminated_without_submission_marker',",
            ")",
            "print(json.dumps({'mode': mode, 'initial_commit': initial['initial_repository_commit']}))",
        ]) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
