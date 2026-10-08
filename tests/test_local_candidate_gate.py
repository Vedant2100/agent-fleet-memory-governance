import unittest

from scripts.run_local_candidate import (
    apply_worker_mechanics_gate,
    oracle_gate_passes,
    worker_mechanics_gate,
)


def record(*, valid=True, canonical=True, applied=True, patch_bytes=120, resolved=False):
    return {
        "worker": {"valid_submission": valid, "patch_bytes": patch_bytes},
        "grade": {
            "canonical_grade_available": canonical,
            "patch_applied": applied,
            "resolved": resolved,
        },
    }


class DevelopmentGateTests(unittest.TestCase):
    def test_oracle_gate_requires_two_executable_discordances(self):
        self.assertFalse(oracle_gate_passes(True, 0))
        self.assertFalse(oracle_gate_passes(True, 1))
        self.assertTrue(oracle_gate_passes(True, 2))
        self.assertFalse(oracle_gate_passes(False, 10))

    def test_partial_applicable_patches_pass_without_full_resolution(self):
        summary = {"records": [record(), record(), record(valid=False, patch_bytes=0)]}
        gate = worker_mechanics_gate(summary)
        self.assertEqual(gate["status"], "PASS")
        self.assertEqual(gate["mechanically_valid_applicable_grades"], 2)
        self.assertEqual(gate["minimum_resolved_tasks"], 0)

    def test_one_applicable_patch_is_insufficient(self):
        summary = {"records": [record(), record(valid=False), record(applied=False)]}
        self.assertEqual(worker_mechanics_gate(summary)["status"], "STOP_WORKER_MECHANICS_FAILED")

    def test_original_resolution_gate_result_is_preserved(self):
        summary = {
            "status": "STOP_WORKER_QUALIFICATION_FAILED",
            "resolved_count": 0,
            "records": [record(), record(), record(valid=False)],
        }
        updated = apply_worker_mechanics_gate(summary)
        self.assertEqual(updated["status"], "PASS")
        self.assertEqual(updated["unamended_full_resolution_gate"]["status"], "STOP_WORKER_QUALIFICATION_FAILED")


if __name__ == "__main__":
    unittest.main()
