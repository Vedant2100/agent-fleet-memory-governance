from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fleet_mem_contextbench.chronology import source_precedes_target
from fleet_mem_contextbench.build import _source_memory_candidates
from fleet_mem_contextbench.data import Task, deduplicate_tasks
from fleet_mem_contextbench.governors.adapters import (
    CallableGovernorAdapter, DeliberativeLLMAdapter, JevSystemOneAdapter,
)
from fleet_mem_contextbench.governors.base import Decision
from fleet_mem_contextbench.governors.deterministic import DeterministicGovernor
from fleet_mem_contextbench.leakage import audit_pair
from fleet_mem_contextbench.memory_schema import memory_from_provided_experience, memory_from_trajectory
from fleet_mem_contextbench.paired import compute_exposure, exposure_gate
from fleet_mem_contextbench.pools import build_candidate_pool, plausible_distractor_count
from fleet_mem_contextbench.relations import relations_from_rows
from fleet_mem_contextbench.validators import validate_candidate_pool, validate_manifest


def task(task_id, created_at, problem, patch="", repo="org/repo", raw=None):
    row = {
        "instance_id": task_id, "repo": repo, "created_at": created_at,
        "base_commit": "a" * 40, "environment_setup_commit": "a" * 40,
        "problem_statement": problem, "hints_text": "", "patch": patch,
        "test_patch": "", "FAIL_TO_PASS": ["test::one"], "PASS_TO_PASS": [],
    }
    if raw:
        row.update(raw)
    return Task.from_row(row)


class ChronologyTests(unittest.TestCase):
    def test_strict_order_rejects_equal_or_later_time(self):
        source = task("org__repo-1", "2020-01-01T00:00:00Z", "source")
        equal = task("org__repo-2", "2020-01-01T00:00:00Z", "target")
        later_source = task("org__repo-3", "2020-01-02T00:00:00Z", "later")
        self.assertEqual(source_precedes_target(source, equal), (False, "SOURCE_NOT_STRICTLY_EARLIER"))
        self.assertEqual(source_precedes_target(later_source, equal), (False, "SOURCE_NOT_STRICTLY_EARLIER"))

    def test_missing_timestamp_is_not_assumed_earlier(self):
        source = task("org__repo-1", None, "source")
        target = task("org__repo-2", "2020-01-02T00:00:00Z", "target")
        self.assertEqual(source_precedes_target(source, target), (None, "MISSING_OR_INVALID_TIMESTAMP"))


class PoolAndFirewallTests(unittest.TestCase):
    def test_pool_is_deterministic_and_has_no_hidden_relation_fields(self):
        source_a = task("org__repo-1", "2020-01-01T00:00:00Z", "router parser behavior", "diff --git a/lib/router.py b/lib/router.py\n+++ b/lib/router.py\n+def parse_route():\n")
        source_b = task("org__repo-2", "2020-01-15T00:00:00Z", "router parser edge case", "diff --git a/lib/router.py b/lib/router.py\n+++ b/lib/router.py\n+def parse_edge():\n")
        target = task("org__repo-3", "2020-02-01T00:00:00Z", "SECRET_TARGET_ONLY router parser")
        memories = {item.task_id: memory_from_provided_experience(item) for item in (source_a, source_b)}
        first = build_candidate_pool(target, [source_b, source_a], memories)
        second = build_candidate_pool(target, [source_a, source_b], memories)
        self.assertEqual(first["pool_hash"], second["pool_hash"])
        self.assertEqual(len(first["candidate_pool"]), 2)
        self.assertNotIn("SECRET_TARGET_ONLY", json_text([entry["memory"] for entry in first["candidate_pool"]]))
        self.assertEqual(validate_candidate_pool(first), [])
        tampered = json.loads(json.dumps(first))
        tampered["pool_hash"] = "0" * 64
        self.assertIn("pool_hash does not match canonical candidate serialization", validate_candidate_pool(tampered))
        tampered = json.loads(json.dumps(first))
        tampered["candidate_pool"][0]["memory"]["created_at"] = "2020-02-01T00:00:00Z"
        self.assertTrue(any("not strictly earlier" in error for error in validate_candidate_pool(tampered)))

    def test_strict_cutoff_and_repo_boundary(self):
        source = task("org__repo-1", "2020-01-01T00:00:00Z", "source")
        equal = task("org__repo-2", "2020-02-01T00:00:00Z", "same time")
        target = task("org__repo-3", "2020-02-01T00:00:00Z", "target")
        other_repo = task("other__repo-1", "2020-01-01T00:00:00Z", "other", repo="other/repo")
        memories = {item.task_id: memory_from_provided_experience(item) for item in (source, other_repo)}
        pool = build_candidate_pool(target, [source, equal, other_repo], memories)
        self.assertEqual([row["memory"]["source_task_id"] for row in pool["candidate_pool"]], [source.task_id])

    def test_generic_issue_template_words_do_not_create_hard_negative_signal(self):
        source = task("org__repo-1", "2020-01-01T00:00:00Z", "The issue for the example is described above.")
        target = task("org__repo-2", "2020-02-01T00:00:00Z", "The issue for another example is described above.")
        pool = build_candidate_pool(target, [source], {source.task_id: memory_from_provided_experience(source)})
        self.assertFalse(any(reason.startswith("ISSUE_") for reason in pool["candidate_pool"][0]["entry_reasons"]))
        self.assertEqual(plausible_distractor_count(pool, set()), 0)

    def test_write_adapter_rejects_target_side_fields(self):
        adapter = CallableGovernorAdapter("stub", lambda _: Decision("DO_NOT_SHARE"), lambda _t, p: [Decision("WITHHOLD") for _ in p])
        with self.assertRaises(ValueError):
            adapter.decide_write({"source_task_id": "source", "target_id": "target"})

    def test_trajectory_evidence_must_be_exact_source_substring(self):
        source = task("org__repo-1", "2020-01-01T00:00:00Z", "source problem")
        record = {
            "source_task_id": source.task_id, "repository": source.repo,
            "trajectory_text": "Observed pytest failure in tests/test_router.py",
            "claim": "Run the focused router test after editing route parsing.",
            "memory_type": "TESTING_WORKFLOW",
            "evidence": ["pytest failure in tests/test_router.py"],
        }
        memory = memory_from_trajectory(source, record)
        self.assertEqual(memory.source_mode, "FRESH_WORKER_TRAJECTORY")
        record["evidence"] = ["not actually in the trace"]
        with self.assertRaises(ValueError):
            memory_from_trajectory(source, record)
        record["evidence"] = ["pytest failure in tests/test_router.py"]
        record["source_outcome"] = {"status": "verified_pass", "evidence_status": "agent_reported_pass"}
        with self.assertRaises(ValueError):
            memory_from_trajectory(source, record)

    def test_build_supports_distinct_provided_and_fresh_trajectory_modes(self):
        source = task("org__repo-1", "2020-01-01T00:00:00Z", "source problem")
        provided = _source_memory_candidates({source.task_id: source}, None)[source.task_id]
        self.assertEqual(provided.source_mode, "PROVIDED_EXPERIENCE_SMOKE")
        record = {
            "source_task_id": source.task_id, "repository": source.repo,
            "trajectory_text": "Observed focused test failure in tests/test_router.py",
            "claim": "Run the focused router test after edits.", "memory_type": "TESTING_WORKFLOW",
            "evidence": ["focused test failure in tests/test_router.py"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            fresh = _source_memory_candidates({source.task_id: source}, path)[source.task_id]
        self.assertEqual(fresh.source_mode, "FRESH_WORKER_TRAJECTORY")

    def test_pair_audit_records_chronology_and_hidden_patch_fields(self):
        source = task("org__repo-1", "2020-01-01T00:00:00Z", "old parser behavior", "diff --git a/parser.py b/parser.py\n+++ b/parser.py\n+def parse_old():\n")
        target = task("org__repo-2", "2020-02-01T00:00:00Z", "new behavior", "diff --git a/other.py b/other.py\n+++ b/other.py\n+def unrelated():\n")
        row = audit_pair(source, target, None, 3, True, None, True)
        self.assertTrue(row["source_before_target"])
        self.assertIsNone(row["same_pr"])
        self.assertIsNone(row["source_in_target_git_ancestry"])
        self.assertIn("target_contains_solution_hint", row)
        self.assertEqual(row["source_count_for_target"], 3)


class ManifestTests(unittest.TestCase):
    def test_relation_rows_preserve_multiple_published_pr_mappings(self):
        base = {
            "related_instance_id": "target", "related_issue_url": "https://example/issues/2",
            "experience_instance_id": "source", "experience_pr_url": "https://example/pull/1",
            "experience_issue_url": "https://example/issues/1",
        }
        rows = [
            {**base, "related_pr_url": "https://example/pull/2"},
            {**base, "related_pr_url": "https://example/pull/3"},
        ]
        relation = relations_from_rows(rows)[("target", "source")]
        hidden = relation.hidden_record()
        self.assertFalse(relation.same_pr)
        self.assertEqual(hidden["mapping_row_count"], 2)
        self.assertEqual(hidden["distinct_mapping_count"], 2)
        self.assertEqual(hidden["target_pr_urls"], ["https://example/pull/2", "https://example/pull/3"])

    def test_jev_and_deliberative_adapters_preserve_confidence_and_cost(self):
        jev = JevSystemOneAdapter(
            lambda _candidate: {"action": "SHARE", "confidence": 0.8, "cost": 0.002},
            lambda _target, pool: [{"action": "EXPOSE", "confidence": 0.6} for _ in pool],
        )
        self.assertEqual(jev.decide_write({"source_task_id": "source"}).action, "SHARE")
        llm = DeliberativeLLMAdapter(lambda request: (
            {"action": "DO_NOT_SHARE", "confidence": 0.7, "probabilities": {"SHARE": 0.2, "DO_NOT_SHARE": 0.8}}
            if request["stage"] == "write" else
            {"decisions": [{"action": "WITHHOLD", "confidence": 0.9} for _ in request["pool"]], "latency_ms": 20, "cost": 0.001}
        ))
        write = llm.decide_write({"source_task_id": "source"})
        read = llm.decide_read({"target_id": "target", "problem_statement": "target"}, [{"memory_id": "m"}])[0]
        self.assertEqual(write.probabilities["SHARE"], 0.2)
        self.assertEqual(read.cost, 0.001)
        self.assertEqual(read.latency_ms, 20)

    def test_manifest_validation_requires_executable_task_metadata(self):
        valid = {
            "target_id": "org__repo-2", "repository": "org/repo",
            "target_created_at": "2020-02-01T00:00:00Z", "base_commit": "b" * 40,
            "canonical_evaluator": "upstream", "candidate_pool_size": 2,
            "fail_to_pass_count": 1, "pass_to_pass_count": 0,
            "environment_validation_status": "NOT_RUN",
        }
        self.assertEqual(validate_manifest(valid), [])
        del valid["base_commit"]
        self.assertIn("manifest missing base_commit", validate_manifest(valid))

    def test_conflicting_duplicate_task_ids_fail_closed(self):
        first = task("org__repo-1", "2020-01-01T00:00:00Z", "source")
        conflicting = task("org__repo-1", "2020-01-02T00:00:00Z", "different")
        with self.assertRaises(ValueError):
            deduplicate_tasks([first, conflicting], "experience")

    def test_relation_labels_cannot_enter_pool(self):
        pool = {
            "target": {"target_id": "target", "repository": "org/repo", "target_created_at": "2020-02-01T00:00:00Z", "base_commit": "b", "problem_statement": "target"},
            "candidate_pool": [{"memory": {"memory_id": "m", "source_task_id": "source", "repository": "org/repo", "known_related": True}, "entry_reasons": [], "public_similarity": {}}],
            "candidate_count": 1, "pool_hash": "a" * 64,
        }
        self.assertTrue(any("hidden fields" in error for error in validate_candidate_pool(pool)))


class ExposureTests(unittest.TestCase):
    def test_share_all_and_governed_create_actual_exposure_difference(self):
        sources = [
            task(f"org__repo-{i}", f"2020-01-{i:02}T00:00:00Z", f"router issue {i}", "diff --git a/router.py b/router.py\n+++ b/router.py\n+def route_case():\n")
            for i in (1, 2, 3)
        ]
        target = task("org__repo-9", "2020-02-01T00:00:00Z", "router route handling")
        memories = {item.task_id: memory_from_provided_experience(item) for item in sources}
        pool = build_candidate_pool(target, sources, memories)
        governor = DeterministicGovernor()
        exposures = [
            compute_exposure(target.public_target(), pool, arm, governor)
            for arm in ("B_SHARE_ALL_FIXED_READ", "C_GOVERNED_WRITE_FIXED_READ")
        ]
        gate = exposure_gate(exposures)
        row = gate["B_SHARE_ALL_FIXED_READ_vs_C_GOVERNED_WRITE_FIXED_READ"]
        self.assertTrue(row["shared_pool_differs"])
        self.assertTrue(row["target_exposure_differs"])
        measured = compute_exposure(target.public_target(), pool, "B_SHARE_ALL_FIXED_READ", governor, token_counter=lambda _: 7)
        self.assertEqual(measured.memory_tokens_exposed, 21)
        self.assertEqual(measured.memory_token_count_method, "CUSTOM_TOKEN_COUNTER")

    def test_hard_negative_count_needs_issue_or_path_signal(self):
        pool = {"candidate_pool": [
            {"memory": {"source_task_id": "nearby"}, "entry_reasons": ["WITHIN_ONE_YEAR_OF_TARGET"]},
            {"memory": {"source_task_id": "similar"}, "entry_reasons": ["ISSUE_PATH_MATCH"]},
            {"memory": {"source_task_id": "linked"}, "entry_reasons": ["ISSUE_TEXT_OVERLAP"]},
        ]}
        self.assertEqual(plausible_distractor_count(pool, {"linked"}), 1)

    def test_oracle_ceiling_exposes_concise_related_card(self):
        source = task("org__repo-1", "2020-01-01T00:00:00Z", "router parser behavior", "diff --git a/router.py b/router.py\n+++ b/router.py\n+def parse_route():\n")
        target = task("org__repo-9", "2020-02-01T00:00:00Z", "router route handling")
        pool = build_candidate_pool(target, [source], {source.task_id: memory_from_provided_experience(source)})
        exposure = compute_exposure(target.public_target(), pool, "F_ORACLE_RELATED_MEMORY_CEILING", DeterministicGovernor(), related_source_ids={source.task_id})
        self.assertEqual(len(exposure.exposed_memories), 1)
        self.assertTrue(exposure.exposed_memories[0]["oracle_concise"])
        self.assertEqual(exposure.read_decision_details[exposure.exposed_memory_ids[0]]["action"], "EXPOSE")


def json_text(value):
    import json
    return json.dumps(value)


if __name__ == "__main__":
    unittest.main()
