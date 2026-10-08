"""Development-only timeout extension for complete SymPy diagnostic grades.

The pinned SWE-ContextBench checkout stays untouched. This wrapper changes only
the timeout argument passed to its existing test runner and preserves the
original 1,800-second results in their existing output directories.
"""

from __future__ import annotations


def extend_sympy_test_timeout(run_evaluation_module, seconds: int = 3600) -> None:
    original = run_evaluation_module.run_specific_tests_in_container

    def run_with_extended_sympy_timeout(*args, **kwargs):
        if "sympy" in str(kwargs.get("instance_id", "")).lower():
            kwargs["timeout"] = max(int(kwargs.get("timeout", 0)), seconds)
        return original(*args, **kwargs)

    run_evaluation_module.run_specific_tests_in_container = run_with_extended_sympy_timeout
