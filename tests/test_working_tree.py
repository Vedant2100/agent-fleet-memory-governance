from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fleet_mem_contextbench.working_tree import collect_working_tree, snapshot_working_tree
from fleet_mem_contextbench.apptainer_evaluator import semantic_noop_patch
from run_sweedit_burned import _prediction_patch


class WorkingTreeCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "fixture@example.test")
        self._git("config", "user.name", "Fixture")
        (self.repo / "src.py").write_text("value = 1\n", encoding="utf-8")
        self._git("add", "src.py")
        self._git("commit", "-qm", "baseline")

    def tearDown(self):
        self.temp.cleanup()

    def test_captures_exact_tracked_source_diff_without_submission_marker(self):
        initial = snapshot_working_tree(self.repo)
        self.assertTrue(initial["initial_tree_clean"])
        (self.repo / "src.py").write_text("value = 2\n", encoding="utf-8")
        expected = self._git_bytes(
            "diff", "--binary", "--no-ext-diff", "--full-index",
            initial["initial_repository_commit"], "--",
        )
        metadata = collect_working_tree(
            self.repo, initial, self.repo / "prediction.patch", self.repo / "status.json",
            worker_declared_submission={"finish_tool_calls": 0, "messages": []},
            termination_reason="iteration_limit",
        )
        captured = (self.repo / "prediction.patch").read_bytes()
        self.assertEqual(captured, expected)
        self.assertEqual(metadata["tracked_source_files"], ["src.py"])
        self.assertTrue(metadata["tracked_source_files_changed"])
        self.assertEqual(metadata["authoritative_diff_sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(metadata["worker_declared_submission"]["finish_tool_calls"], 0)

    def test_collects_relevant_untracked_source_as_a_patch(self):
        initial = snapshot_working_tree(self.repo)
        (self.repo / "new_test.py").write_text("assert True\n", encoding="utf-8")
        metadata = collect_working_tree(
            self.repo, initial, self.repo / "prediction.patch", self.repo / "status.json",
            worker_declared_submission={"finish_tool_calls": 0, "messages": []},
            termination_reason="agent_exited_without_finish",
        )
        patch = (self.repo / "prediction.patch").read_bytes()
        self.assertIn(b"new_test.py", patch)
        self.assertEqual(metadata["relevant_untracked_files_created"], ["new_test.py"])
        self.assertTrue(metadata["source_code_changed"])

    def test_staged_new_source_is_still_reported_as_created_untracked_source(self):
        initial = snapshot_working_tree(self.repo)
        (self.repo / "new_test.py").write_text("assert True\n", encoding="utf-8")
        self._git("add", "new_test.py")
        metadata = collect_working_tree(
            self.repo, initial, self.repo / "prediction.patch", self.repo / "status.json",
            worker_declared_submission={"finish_tool_calls": 0, "messages": []},
            termination_reason="finish_tool",
        )
        self.assertEqual(metadata["tracked_source_files"], [])
        self.assertEqual(metadata["relevant_untracked_files_created"], ["new_test.py"])
        self.assertIn(b"new_test.py", (self.repo / "prediction.patch").read_bytes())

    def test_empty_authoritative_diff_becomes_canonical_noop_prediction(self):
        initial = snapshot_working_tree(self.repo)
        metadata = collect_working_tree(
            self.repo, initial, self.repo / "prediction.patch", self.repo / "status.json",
            worker_declared_submission={"finish_tool_calls": 0, "messages": []},
            termination_reason="iteration_limit",
        )
        prediction = _prediction_patch({
            "repository_state_recovered": metadata["repository_state_recovered"],
            "patch_path": str(self.repo / "prediction.patch"),
        })
        self.assertEqual(prediction, semantic_noop_patch())
        self.assertEqual((self.repo / "prediction.patch").read_bytes(), b"")
        self.assertFalse(metadata["source_code_changed"])

    def test_runaway_diff_exceeding_threshold_triggers_collector_error(self):
        initial = snapshot_working_tree(self.repo)
        # Create a large source file > 1MB
        (self.repo / "large.py").write_text("x = 1\n" * 250_000, encoding="utf-8")
        metadata = collect_working_tree(
            self.repo, initial, self.repo / "prediction.patch", self.repo / "status.json",
            worker_declared_submission={"finish_tool_calls": 0, "messages": []},
            termination_reason="iteration_limit",
        )
        self.assertIsNotNone(metadata["collector_error"])
        self.assertIn("exceeds safety threshold", metadata["collector_error"])
        self.assertEqual((self.repo / "prediction.patch").read_bytes(), b"")


    def _git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def _git_bytes(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, capture_output=True,
        ).stdout


if __name__ == "__main__":
    unittest.main()
