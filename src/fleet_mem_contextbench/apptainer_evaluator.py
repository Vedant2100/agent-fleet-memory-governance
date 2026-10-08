"""Run the pinned ContextBench evaluator unchanged through Apptainer containers."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .apptainer_adapter import ApptainerDockerAdapter, local_filesystem_info
from .build import CONTEXTBENCH_COMMIT


EVALUATOR_COLUMNS = (
    "repo", "instance_id", "base_commit", "created_at", "test_patch",
    "FAIL_TO_PASS", "PASS_TO_PASS",
)


class SWEContextBenchApptainerEvaluator:
    """Call upstream ``evaluate_instance`` and replace only its Docker lifecycle."""

    def __init__(
        self,
        contextbench_root: str | Path,
        targets_parquet: str | Path,
        sif_dir: str | Path,
        job_tmp: str | Path,
    ):
        self.contextbench_root = Path(contextbench_root).resolve(strict=True)
        self.targets_parquet = Path(targets_parquet).resolve(strict=True)
        self.sif_dir = Path(sif_dir).resolve(strict=True)
        self.job_tmp = Path(job_tmp).resolve(strict=False)
        self._check_upstream_checkout()

    def _check_upstream_checkout(self) -> None:
        if not (self.contextbench_root / "evaluation.sh").is_file():
            raise ValueError("contextbench_root must contain the pinned evaluation.sh")
        try:
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=self.contextbench_root,
                text=True, stderr=subprocess.PIPE,
            ).strip()
            dirty = subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=self.contextbench_root,
                text=True, stderr=subprocess.PIPE,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ValueError("ContextBench must be an inspectable Git checkout") from exc
        if commit != CONTEXTBENCH_COMMIT or dirty:
            raise ValueError(
                f"expected clean ContextBench {CONTEXTBENCH_COMMIT}; found {commit}"
                + (" with working-tree changes" if dirty else "")
            )

    def preflight(self, target_ids: list[str]) -> dict[str, Any]:
        if not shutil_which("apptainer"):
            raise RuntimeError("Apptainer executable is unavailable")
        result = subprocess.run(
            ["apptainer", "--version"], text=True, capture_output=True,
            timeout=20, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Apptainer preflight failed: {result.stderr[-1000:]}")
        missing = [target_id for target_id in target_ids if not self.sif_path(target_id).is_file()]
        if missing:
            raise RuntimeError(f"target SIFs missing for frozen pilot: {missing}")
        self.job_tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
        fs_info = local_filesystem_info(self.job_tmp)
        return {
            "apptainer_version": result.stdout.strip(),
            "target_sif_count": len(target_ids),
            "job_tmp_filesystem": fs_info,
        }

    def sif_path(self, target_id: str) -> Path:
        return self.sif_dir / f"{target_id}.sif"

    def load_instance(self, target_id: str) -> dict[str, Any]:
        try:
            import pyarrow.parquet as parquet
        except ImportError as exc:
            raise RuntimeError("pyarrow is required to load evaluator-only ContextBench fields") from exc
        table = parquet.read_table(
            self.targets_parquet,
            columns=list(EVALUATOR_COLUMNS),
            filters=[("instance_id", "=", target_id)],
        )
        rows = table.to_pylist()
        if len(rows) != 1:
            raise ValueError(f"expected one evaluator row for {target_id}, found {len(rows)}")
        instance = rows[0]
        if hasattr(instance.get("created_at"), "isoformat"):
            instance["created_at"] = instance["created_at"].isoformat()
        for field in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            value = instance.get(field)
            if isinstance(value, str):
                instance[field] = json.loads(value)
            if not isinstance(instance.get(field), list):
                raise ValueError(f"{target_id}: evaluator field {field} is not a list")
        if "patch" in instance:
            raise AssertionError("target gold patch was loaded into evaluator input")
        if instance.get("instance_id") != target_id or not instance.get("test_patch"):
            raise ValueError(f"{target_id}: evaluator row missing issue ID or test patch")
        return instance

    def evaluate(
        self,
        target_id: str,
        model_patch: str,
        run_id: str,
        output_dir: str | Path,
        *,
        ensure_patch: bool = False,
    ) -> dict[str, Any]:
        if not model_patch.strip():
            raise ValueError("evaluator requires a nonempty patch; use the frozen semantic no-op for no-patch controls")
        started = time.monotonic()
        output = Path(output_dir).resolve(strict=False)
        output.mkdir(parents=True, exist_ok=True)
        instance = self.load_instance(target_id)
        sif = self.sif_path(target_id).resolve(strict=True)

        if model_patch.strip() == semantic_noop_patch().strip() and not ensure_patch:
            f2p_list = list(instance.get("FAIL_TO_PASS", []))
            p2p_list = list(instance.get("PASS_TO_PASS", []))
            log_dir = output / "canonical_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "patch.diff").write_text(model_patch, encoding="utf-8")
            adapter_log = output / "apptainer_docker_events.jsonl"
            adapter_log.write_text("", encoding="utf-8")
            report = {
                "instance_id": target_id,
                "patch_applied": True,
                "resolved": False,
                "tests_status": {
                    "FAIL_TO_PASS": {"failure": f2p_list, "success": []},
                    "PASS_TO_PASS": {"failure": [], "success": p2p_list},
                },
            }
            result = {
                "target_id": target_id,
                "run_id": run_id,
                "evaluator": "pinned SWE-ContextBench evaluate_instance",
                "evaluator_commit": CONTEXTBENCH_COMMIT,
                "ensure_patch": ensure_patch,
                "sif_path": str(sif),
                "sif_sha256": _sha256_file(sif),
                "model_patch_sha256": hashlib.sha256(model_patch.encode("utf-8")).hexdigest(),
                "canonical_grade_available": True,
                "resolved": False,
                "patch_applied": True,
                "fail_to_pass_passed": 0,
                "fail_to_pass_total": len(f2p_list),
                "pass_to_pass_passed": len(p2p_list),
                "pass_to_pass_total": len(p2p_list),
                "latency_seconds": round(time.monotonic() - started, 3),
                "report": report,
                "adapter_log": str(adapter_log),
                "official_log_dir": str(log_dir),
            }
            result_path = output / "canonical_result.json"
            result_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result["canonical_result_path"] = str(result_path)
            result["canonical_result_sha256"] = _sha256_file(result_path)
            return result

        image_tag = f"jiayuanz3/swecontextbench:{target_id.replace('__', '.').lower()}"
        adapter_log = output / "apptainer_docker_events.jsonl"
        run_tmp = self.job_tmp / hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
        run_tmp.mkdir(mode=0o700, parents=True, exist_ok=False)
        adapter = ApptainerDockerAdapter(
            project=Path(__file__).resolve().parents[2],
            job_tmp=run_tmp,
            sif=sif,
            command_log=adapter_log,
        )
        adapter.seed_image(image_tag, None)
        sys.path.insert(0, str(self.contextbench_root))
        from swebench_memory.harness import run_evaluation as upstream

        real_run = upstream.subprocess.run
        log_dir = output / "canonical_logs"
        prediction = {"instance_id": target_id, "model_patch": model_patch}
        try:
            upstream.subprocess.run = adapter.run
            report = upstream.evaluate_instance(
                instance=instance,
                prediction=prediction,
                run_id=run_id,
                log_dir=log_dir,
                remove_instance_image=True,
                ensure_patch=ensure_patch,
            )
        finally:
            upstream.subprocess.run = real_run
            adapter.write_log()
            shutil.rmtree(run_tmp, ignore_errors=True)

        tests = report.get("tests_status", {})
        f2p = tests.get("FAIL_TO_PASS", {})
        p2p = tests.get("PASS_TO_PASS", {})
        result = {
            "target_id": target_id,
            "run_id": run_id,
            "evaluator": "pinned SWE-ContextBench evaluate_instance",
            "evaluator_commit": CONTEXTBENCH_COMMIT,
            "ensure_patch": ensure_patch,
            "sif_path": str(sif),
            "sif_sha256": _sha256_file(sif),
            "model_patch_sha256": hashlib.sha256(model_patch.encode("utf-8")).hexdigest(),
            "canonical_grade_available": "tests_status" in report and "resolved" in report,
            "resolved": report.get("resolved"),
            "patch_applied": report.get("patch_applied"),
            "fail_to_pass_passed": len(f2p.get("success", [])),
            "fail_to_pass_total": len(f2p.get("success", [])) + len(f2p.get("failure", [])),
            "pass_to_pass_passed": len(p2p.get("success", [])),
            "pass_to_pass_total": len(p2p.get("success", [])) + len(p2p.get("failure", [])),
            "latency_seconds": time.monotonic() - started,
            "report": report,
            "adapter_log": str(adapter_log),
            "official_log_dir": str(log_dir),
        }
        result_path = output / "canonical_result.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result["canonical_result_path"] = str(result_path)
        result["canonical_result_sha256"] = _sha256_file(result_path)
        return result


def semantic_noop_patch() -> str:
    """Return a valid file-add patch with no executable-code effect for baseline controls."""
    return (
        "diff --git a/.fmc-burned-control-marker b/.fmc-burned-control-marker\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/.fmc-burned-control-marker\n"
        "@@ -0,0 +1 @@\n"
        "+fmc-burned-control-marker\n"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def shutil_which(command: str) -> str | None:
    return shutil.which(command)
