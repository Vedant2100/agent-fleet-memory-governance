from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from shutil import copyfile

from scripts.prepare_muse_oracle_worker import HASHED_INPUTS, prepare_worker


class MuseOraclePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "configs").mkdir()
        (self.root / "artifacts/burned-pilot").mkdir(parents=True)
        copyfile("configs/sweedit_worker_sol.json", self.root / "configs/sweedit_worker_sol.json")
        self.plan = {"qualification": {"target_ids": ["one", "two", "three"]}}
        (self.root / "artifacts/burned-pilot/plan.json").write_text(json.dumps(self.plan))
        self.paths: dict[str, Path] = {}
        for key, relative in HASHED_INPUTS.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(key, encoding="utf-8")
            self.paths[key] = path
        self.qualification = self.root / "qualification.json"
        self.worker_config = self.root / "worker.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _passing_qualification(self) -> dict[str, object]:
        base = json.loads((self.root / "configs/sweedit_worker_sol.json").read_text())
        base["model"]["requested_model"] = "muse-glimmer:30b"
        base["model"]["reasoning_effort"] = "xhigh"
        config_bytes = (json.dumps(base, indent=2) + "\n").encode()
        return {
            "status": "PASS",
            "target_ids": self.plan["qualification"]["target_ids"],
            "requested_model": "muse-glimmer:30b",
            "reasoning_effort": "xhigh",
            "worker_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
            **{
                key: hashlib.sha256(path.read_bytes()).hexdigest()
                for key, path in self.paths.items()
            },
        }

    def test_failed_qualification_never_materializes_worker_config(self) -> None:
        self.qualification.write_text(json.dumps({"status": "STOP_WORKER_QUALIFICATION_FAILED"}))
        status, _ = prepare_worker(self.root, self.qualification, self.worker_config, "muse-glimmer:30b")
        self.assertEqual(status, 3)
        self.assertFalse(self.worker_config.exists())

    def test_matching_pass_materializes_exact_frozen_worker_config(self) -> None:
        self.qualification.write_text(json.dumps(self._passing_qualification()))
        status, _ = prepare_worker(self.root, self.qualification, self.worker_config, "muse-glimmer:30b")
        self.assertEqual(status, 0)
        expected = json.loads((self.root / "configs/sweedit_worker_sol.json").read_text())
        expected["model"]["requested_model"] = "muse-glimmer:30b"
        expected["model"]["reasoning_effort"] = "xhigh"
        self.assertEqual(json.loads(self.worker_config.read_text()), expected)

    def test_stale_adapter_hash_blocks_oracle_worker(self) -> None:
        record = self._passing_qualification()
        record["worker_adapter_sha256"] = "stale"
        self.qualification.write_text(json.dumps(record))
        status, _ = prepare_worker(self.root, self.qualification, self.worker_config, "muse-glimmer:30b")
        self.assertEqual(status, 1)
        self.assertFalse(self.worker_config.exists())


if __name__ == "__main__":
    unittest.main()
