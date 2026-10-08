from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fleet_mem_contextbench.sweedit_worker import (
    _agent_environment, _collect_worker_result, build_sweedit_prompt, load_worker_settings,
)
from run_sweedit_burned import (
    _pair_order, _signal_pairs_complete, _validate_sol_diagnostic_request,
    _validate_sol_django_resume_request,
)
from run_local_candidate import oracle_gate_passes


class SweEditWorkerTests(unittest.TestCase):
    def test_prompt_contains_only_task_and_source_memory_view(self):
        target = {
            "target_id": "org__repo-2",
            "repository": "org/repo",
            "problem_statement": "Fix parser behavior.",
            "target_patch": "SECRET_GOLD_PATCH",
            "relationship_type": "SECRET_RELATION",
        }
        memory = {
            "source_task_id": "org__repo-1",
            "claim": "The parser handles escaped delimiters in this helper.",
            "memory_type": "EPISODIC_EXAMPLE",
            "scope": {"repository": "org/repo"},
            "preconditions": "Verify against current code.",
            "evidence": ["source issue only"],
            "evidence_locations": ["src/parser.py"],
            "files_or_symbols": ["src/parser.py"],
            "generality": None,
            "negative_transfer_risk": None,
            "known_related": "SECRET_LABEL",
        }
        prompt = build_sweedit_prompt(target, [memory])
        self.assertIn("Fix parser behavior.", prompt)
        self.assertIn("escaped delimiters", prompt)
        self.assertIn("/testbed", prompt)
        self.assertIn("modify the code in /testbed", prompt)
        self.assertNotIn("SECRET_GOLD_PATCH", prompt)
        self.assertNotIn("SECRET_RELATION", prompt)
        self.assertNotIn("SECRET_LABEL", prompt)
        self.assertNotIn("target_patch", prompt)

    def test_signal_pair_order_is_stable_and_contains_both_arms(self):
        for target_id in ("a", "sympy__sympy-21309", "django__django-34176"):
            order = _pair_order(20261006, target_id)
            self.assertEqual(set(order), {"A_NO_MEMORY", "F_ORACLE_RELATED_CEILING"})
            self.assertEqual(order, _pair_order(20261006, target_id))

    def test_authoritative_empty_prediction_counts_as_a_canonically_graded_pair(self):
        empty_no_marker_arm = {
            "worker": {
                "valid_submission": False,
                "authoritative_prediction_valid": True,
                "repository_state_recovered": True,
            },
            "grade": {"canonical_grade_available": True, "patch_applied": True},
        }
        row = {"no_memory": empty_no_marker_arm, "oracle_related": empty_no_marker_arm}
        self.assertTrue(_signal_pairs_complete([row]))
        empty_no_marker_arm["worker"]["repository_state_recovered"] = False
        self.assertFalse(_signal_pairs_complete([row]))

    def test_recovered_empty_tree_is_authoritative_even_without_model_response(self):
        import hashlib
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "patch": root / "prediction.patch",
                "responses": root / "responses.jsonl",
                "trajectory": root / "trajectory",
                "status": root / "worker_status.json",
                "output": root,
                "prompt": root / "prompt.txt",
                "prompt_sha256": "prompt-hash",
                "log": root / "worker.log",
            }
            files["patch"].write_bytes(b"")
            files["responses"].write_text("", encoding="utf-8")
            files["trajectory"].mkdir()
            status = {
                "repository_state_recovered": True,
                "worker_declared_submission": {"finish_tool_calls": 0, "messages": []},
                "termination_reason": "agent_exception:RuntimeError",
                "authoritative_diff_bytes": 0,
                "authoritative_diff_sha256": hashlib.sha256(b"").hexdigest(),
                "git_status_porcelain": [],
                "collector_error": None,
            }
            files["status"].write_text(json.dumps(status), encoding="utf-8")
            result = _collect_worker_result(
                {"target_id": "fixture"},
                {
                    "worker_settings": {
                        "requested_model": "qwen3-coder:30b", "reasoning_effort": "xhigh",
                    },
                    "commit": "scaffold-commit",
                    "image": Path("fixture.sif"),
                    "image_head": "target-commit",
                    "expected_base": "target-commit",
                },
                files, return_code=1, timed_out=False, elapsed=1.0,
            )
        self.assertFalse(result["requested_model_confirmed"])
        self.assertFalse(result["valid_submission"])
        self.assertTrue(result["repository_state_recovered"])
        self.assertTrue(result["authoritative_prediction_valid"])

    def test_oracle_signal_gate_requires_two_executable_discordances(self):
        self.assertFalse(oracle_gate_passes(True, 0))
        self.assertFalse(oracle_gate_passes(True, 1))
        self.assertTrue(oracle_gate_passes(True, 2))
        self.assertFalse(oracle_gate_passes(False, 10))

    def test_worker_config_preserves_upstream_budget_and_requested_model(self):
        config = json.loads((ROOT / "configs/sweedit_worker.json").read_text(encoding="utf-8"))
        self.assertEqual(config["tool_budget"]["max_iterations"], 100)
        self.assertEqual(config["model"]["requested_model"], "gpt-6-luna")
        self.assertEqual(config["model"]["reasoning_effort"], "xhigh")
        self.assertEqual(config["scaffold_commit"], "60ca6730714670a91bd6a48a53356be85e145248")

    def test_sol_diagnostic_config_changes_only_requested_model(self):
        luna = load_worker_settings(ROOT / "configs/sweedit_worker.json")
        sol = load_worker_settings(ROOT / "configs/sweedit_worker_sol.json")
        expected_sol = json.loads(json.dumps(luna["config"]))
        expected_sol["model"]["requested_model"] = "gpt-5.6-sol"
        self.assertEqual(sol["config"], expected_sol)
        self.assertEqual(sol["reasoning_effort"], luna["reasoning_effort"])
        target = {"target_id": "django__django-34176"}
        env = _agent_environment(target, {"worker_settings": sol})
        self.assertEqual(env["MODEL"], "gpt-5.6-sol")
        self.assertEqual(env["REASONING_EFFORT"], "xhigh")

    def test_sol_diagnostic_is_bound_to_exact_two_frozen_targets(self):
        from argparse import Namespace

        args = Namespace(
            target_ids=["sympy__sympy-21309", "django__django-34176"],
            worker_config=ROOT / "configs/sweedit_worker_sol.json",
        )
        self.assertEqual(
            _validate_sol_diagnostic_request(args),
            ["sympy__sympy-21309", "django__django-34176"],
        )
        args.target_ids.append("sympy__sympy-16953")
        with self.assertRaises(RuntimeError):
            _validate_sol_diagnostic_request(args)

    def test_only_interrupted_django_diagnostic_can_be_restarted(self):
        from argparse import Namespace

        args = Namespace(
            target_ids=["django__django-34176"],
            worker_config=ROOT / "configs/sweedit_worker_sol.json",
        )
        self.assertEqual(_validate_sol_django_resume_request(args), "django__django-34176")
        args.target_ids = ["sympy__sympy-21309"]
        with self.assertRaises(RuntimeError):
            _validate_sol_django_resume_request(args)


if __name__ == "__main__":
    unittest.main()
