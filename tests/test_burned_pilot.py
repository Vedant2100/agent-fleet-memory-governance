from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fleet_mem_contextbench.data import Task
from fleet_mem_contextbench.governors.base import Decision
from fleet_mem_contextbench.memory_schema import memory_from_provided_experience
from fleet_mem_contextbench.pilot_runtime import analysis_target_ids
from fleet_mem_contextbench.pools import build_candidate_pool
from fleet_mem_contextbench.apptainer_adapter import ApptainerDockerAdapter
from fleet_mem_contextbench.treatments import (
    deterministic_retrieval, freeze_size_matched_random, freeze_source_decisions,
    treatment_exposure, unique_source_memories,
)
from fleet_mem_contextbench.worker import (
    _model_usage_calls, _ollama_proxy_base_url, _openai_usage,
    _sum_observed_tokens, build_task_prompt,
)
from run_burned_experiment import _group_run_records, _journal_pairs


def make_task(index: int) -> Task:
    return Task.from_row({
        "instance_id": f"org__repo-{index}",
        "repo": "org/repo",
        "created_at": f"2020-01-{index:02d}T00:00:00Z",
        "base_commit": f"{index:040x}",
        "environment_setup_commit": f"{index:040x}",
        "problem_statement": f"router issue behavior number {index}",
        "hints_text": "",
        "patch": f"diff --git a/router{index}.py b/router{index}.py\n+++ b/router{index}.py\n+def route_{index}():\n",
        "test_patch": "",
        "FAIL_TO_PASS": [],
        "PASS_TO_PASS": [],
    })


def make_pool(source_tasks: list[Task], target: Task) -> dict:
    memories = {task.task_id: memory_from_provided_experience(task) for task in source_tasks}
    return build_candidate_pool(target, source_tasks, memories)


class CountingGovernor:
    name = "counting_source_governor"

    def __init__(self):
        self.seen: list[str] = []

    def decide_write(self, candidate):
        self.seen.append(candidate["memory_id"])
        action = "SHARE" if len(self.seen) % 2 == 0 else "DO_NOT_SHARE"
        return Decision(action, confidence=0.8, rationale="test source-only decision", latency_ms=2.0)

    def decide_read(self, target, pool):
        return [Decision("EXPOSE", confidence=1.0) for _ in pool]


class BurnedPilotTests(unittest.TestCase):
    def setUp(self):
        self.sources = [make_task(index) for index in (1, 2, 3, 4)]
        self.target = make_task(9)
        self.target.raw["created_at"] = "2020-02-01T00:00:00Z"
        self.target = Task.from_row(self.target.raw)
        self.pool = make_pool(self.sources, self.target)
        self.pools = {self.target.task_id: self.pool}
        self.memories = unique_source_memories(self.pools)

    def test_apptainer_adapter_parses_named_runs_with_or_without_interactive_flag(self):
        expected = (False, "reinstall", "image:tag", ["bash", "-c", "true"], [], None, [])
        self.assertEqual(
            ApptainerDockerAdapter._parse_run(
                ["--name", "reinstall", "image:tag", "bash", "-c", "true"]
            ),
            expected,
        )
        self.assertEqual(
            ApptainerDockerAdapter._parse_run(
                ["-i", "--name", "reinstall", "image:tag", "bash", "-c", "true"]
            ),
            expected,
        )

    def test_primary_targets_are_a_valid_frozen_subset(self):
        plan = {"target_ids": ["a", "b", "c"], "analysis_target_ids": ["a", "c"]}
        self.assertEqual(analysis_target_ids(plan), ["a", "c"])
        with self.assertRaisesRegex(RuntimeError, "subset"):
            analysis_target_ids({"target_ids": ["a", "b"], "analysis_target_ids": ["a", "a"]})
        with self.assertRaisesRegex(RuntimeError, "subset"):
            analysis_target_ids({"target_ids": ["a"], "analysis_target_ids": ["outside"]})

    def test_write_decisions_are_once_per_unique_source_memory(self):
        governor = CountingGovernor()
        rows = freeze_source_decisions(self.memories, governor)
        self.assertEqual(len(governor.seen), len(self.memories))
        self.assertEqual(len(governor.seen), len(set(governor.seen)))
        self.assertEqual({row["action"] for row in rows}, {"SHARE", "DO_NOT_SHARE"})
        self.assertNotIn("target_id", rows[0])

    def test_unique_source_memory_dedup_and_conflicts(self):
        second_pool = copy.deepcopy(self.pool)
        two_targets = {"t1": self.pool, "t2": second_pool}
        self.assertEqual(len(unique_source_memories(two_targets)), 4)
        second_pool["candidate_pool"][0]["memory"]["claim"] += " changed"
        with self.assertRaisesRegex(ValueError, "conflicting source-only content"):
            unique_source_memories({"t1": self.pool, "t2": second_pool})

    def test_nested_target_leakage_fails_before_governor_call(self):
        memories = copy.deepcopy(self.memories)
        first_id = next(iter(memories))
        memories[first_id]["scope"]["target_id"] = "future"
        with self.assertRaisesRegex(ValueError, "target/hidden fields"):
            freeze_source_decisions(memories, CountingGovernor())

    def test_random_admission_matches_governed_count_and_is_deterministic(self):
        governed = freeze_source_decisions(self.memories, CountingGovernor())
        first = freeze_size_matched_random(self.memories, governed, seed=42)
        second = freeze_size_matched_random(self.memories, governed, seed=42)
        expected = sum(row["action"] == "SHARE" for row in governed)
        self.assertEqual(sum(row["action"] == "SHARE" for row in first), expected)
        self.assertEqual(first, second)

    def test_retrieval_is_fixed_recency_order_and_not_target_similarity(self):
        retrieved = deterministic_retrieval(self.pool, limit=3)
        self.assertEqual(
            [row["memory"]["source_task_id"] for row in retrieved],
            ["org__repo-4", "org__repo-3", "org__repo-2"],
        )
        self.assertEqual(retrieved, deterministic_retrieval(self.pool, limit=3))

    def test_write_filter_does_not_backfill_past_fixed_retrieval_slots(self):
        oldest = next(row["memory"]["memory_id"] for row in self.pool["candidate_pool"]
                      if row["memory"]["source_task_id"] == "org__repo-1")
        exposure = treatment_exposure(
            target=self.target.public_target(), pool=self.pool, arm_id="D_JEV_WRITE",
            admitted_ids={oldest}, token_counter=lambda text: max(1, len(text) // 4),
        )
        self.assertEqual(exposure["retrieval_window_ids"], [
            row["memory"]["memory_id"] for row in deterministic_retrieval(self.pool)
        ])
        self.assertEqual(exposure["retrieved_memory_ids"], [])
        self.assertEqual(exposure["exposed_memory_ids"], [])

    def test_fixed_count_budget_and_context_estimates_are_recorded(self):
        all_ids = set(self.memories)
        exposure = treatment_exposure(
            target=self.target.public_target(), pool=self.pool, arm_id="B_SHARE_ALL",
            admitted_ids=all_ids, token_counter=lambda text: max(1, len(text) // 4),
            max_memories=3,
        )
        self.assertLessEqual(len(exposure["exposed_memory_ids"]), 3)
        self.assertGreater(exposure["memory_tokens_exposed"], 0)
        self.assertEqual(exposure["memory_count_budget"], 3)
        self.assertEqual(len(exposure["memory_card_sizes"]), 3)
        self.assertGreater(exposure["memory_serialized_bytes_exposed"], 0)

    def test_governed_read_can_only_withhold_or_expose_fixed_retrieval(self):
        all_ids = set(self.memories)
        governor = CountingGovernor()
        exposure = treatment_exposure(
            target=self.target.public_target(), pool=self.pool, arm_id="E_JEV_WRITE_READ",
            admitted_ids=all_ids, token_counter=lambda _text: 10, read_governor=governor,
        )
        self.assertEqual(exposure["retrieved_memory_ids"], exposure["exposed_memory_ids"])
        self.assertEqual(len(governor.seen), 0)

    def test_frozen_read_decisions_withhold_without_changing_retrieval(self):
        retrieved = deterministic_retrieval(self.pool, limit=3)
        ids = [row["memory"]["memory_id"] for row in retrieved]
        decisions = {
            ids[0]: Decision("WITHHOLD", confidence=0.9),
            ids[1]: Decision("EXPOSE", confidence=0.8),
            ids[2]: Decision("WITHHOLD", confidence=0.7),
        }
        exposure = treatment_exposure(
            target=self.target.public_target(), pool=self.pool, arm_id="E_JEV_WRITE_READ",
            admitted_ids=set(self.memories), frozen_read_decisions=decisions,
        )
        self.assertEqual(exposure["retrieved_memory_ids"], ids)
        self.assertEqual(exposure["exposed_memory_ids"], [ids[1]])
        self.assertEqual(exposure["read_abstention_rate"], 2 / 3)
        self.assertEqual(set(exposure["memory_token_counts_exposed"]), {ids[1]})
        self.assertEqual(set(exposure["exposed_memory_card_sizes"]), {ids[1]})

    def test_worker_prompt_receives_only_target_text_and_rendered_source_cards(self):
        prompt = build_task_prompt(self.target.problem_statement, [next(iter(self.memories.values()))])
        self.assertIn(self.target.problem_statement, prompt)
        self.assertIn("Prior source experiences", prompt)
        self.assertNotIn("target_patch", prompt)
        self.assertNotIn("relationship_type", prompt)

    def test_worker_command_contract_defers_terminal_sentinel(self):
        config = (Path(__file__).resolve().parents[1] / "configs/worker.yaml").read_text(encoding="utf-8")
        self.assertIn("one fenced block tagged `mswea_bash_command`", config)
        self.assertIn("Your first command must inspect the repository", config)
        self.assertIn("Do not run that command until after the requested code change exists", config)
        self.assertIn("Choose a command that advances repository inspection, implementation, or testing", config)

    def test_missing_usage_is_not_reported_as_zero_tokens(self):
        self.assertEqual(_sum_observed_tokens([3, 4]), 7)
        self.assertIsNone(_sum_observed_tokens([3, None]))
        self.assertIsNone(_sum_observed_tokens([]))

    def test_ollama_chat_proxy_uses_native_base_url(self):
        self.assertEqual(_ollama_proxy_base_url(12345), "http://127.0.0.1:12345")
        with self.assertRaises(ValueError):
            _ollama_proxy_base_url(0)

    def test_native_ollama_usage_is_counted_and_extracted(self):
        payload = json.dumps({"prompt_eval_count": 321, "eval_count": 17}).encode()
        self.assertEqual(
            _openai_usage(payload, "application/json"),
            {"prompt_tokens": 321, "completion_tokens": 17},
        )
        calls = [
            {"method": "POST", "path": "/api/chat"},
            {"method": "POST", "path": "/api/show"},
            {"method": "POST", "path": "/v1/chat/completions"},
        ]
        self.assertEqual(_model_usage_calls(calls), [calls[0], calls[2]])

    def test_treatment_journal_rejects_duplicate_or_out_of_order_calls(self):
        key = {"target_id": "t1", "arm_id": "A_NO_MEMORY"}
        completed, started = _journal_pairs([
            {"event": "RUN_STARTED", **key}, {"event": "RUN_COMPLETED", **key},
        ])
        self.assertEqual(completed, {("t1", "A_NO_MEMORY")})
        self.assertEqual(started, {("t1", "A_NO_MEMORY")})
        with self.assertRaisesRegex(RuntimeError, "duplicate or out-of-order"):
            _journal_pairs([{"event": "RUN_COMPLETED", **key}])
        with self.assertRaisesRegex(RuntimeError, "duplicate or out-of-order"):
            _journal_pairs([{"event": "RUN_STARTED", **key}, {"event": "RUN_STARTED", **key}])

    def test_treatment_result_group_rejects_duplicates(self):
        record = {"target_id": "t1", "arm_id": "A_NO_MEMORY"}
        self.assertIn("t1", _group_run_records([record]))
        with self.assertRaisesRegex(RuntimeError, "duplicate treatment result"):
            _group_run_records([record, record])


if __name__ == "__main__":
    unittest.main()
