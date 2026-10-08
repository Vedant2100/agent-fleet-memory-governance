#!/usr/bin/env python3
"""Exercise mini-SWE-agent 2.4.6's upstream terminal-submission parser."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from minisweagent.environments.singularity import SingularityEnvironment
from minisweagent.exceptions import Submitted


KNOWN_DIFF = """diff --git a/fixture.txt b/fixture.txt
index 7898192..f2ad6c7 100644
--- a/fixture.txt
+++ b/fixture.txt
@@ -1 +1 @@
-before
+after
"""
SUBMIT_COMMAND = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt"


def audit() -> dict[str, object]:
    version = importlib.metadata.version("mini-swe-agent")
    if version != "2.4.6":
        raise RuntimeError(f"Expected mini-swe-agent 2.4.6, found {version}")

    with tempfile.TemporaryDirectory(prefix="fleet-mswe-submit-") as temporary:
        workdir = Path(temporary)
        patch_path = workdir / "patch.txt"
        patch_path.write_text(KNOWN_DIFF, encoding="utf-8")

        inspected = subprocess.run(
            ["cat", "patch.txt"], cwd=workdir, check=True, capture_output=True, text=True
        ).stdout
        if inspected != KNOWN_DIFF:
            raise AssertionError("The inspected patch.txt differs from the known fixture")

        completed = subprocess.run(
            ["bash", "-lc", SUBMIT_COMMAND],
            cwd=workdir,
            check=False,
            capture_output=True,
            text=True,
        )
        upstream_output = {
            "output": completed.stdout,
            "returncode": completed.returncode,
            "exception_info": "",
        }

        try:
            SingularityEnvironment._check_finished(None, upstream_output)
        except Submitted as submitted:
            captured = submitted.messages[0]["extra"]["submission"]
        else:
            raise AssertionError("Upstream parser did not recognize the submitted fixture")

        if captured != KNOWN_DIFF:
            raise AssertionError("Captured submission differs from the known unified diff")

        return {
            "audit": "mini-swe-agent upstream submission contract",
            "mini_swe_agent_version": version,
            "environment_class": "minisweagent.environments.singularity.SingularityEnvironment",
            "parser_method": "SingularityEnvironment._check_finished",
            "patch_file": "patch.txt",
            "patch_sha256": hashlib.sha256(KNOWN_DIFF.encode()).hexdigest(),
            "patch_bytes": len(KNOWN_DIFF.encode()),
            "inspection_matched_fixture": inspected == KNOWN_DIFF,
            "submission_command": SUBMIT_COMMAND,
            "stdout_returncode": completed.returncode,
            "stdout_first_line": completed.stdout.splitlines()[0] if completed.stdout else "",
            "captured_submission_sha256": hashlib.sha256(captured.encode()).hexdigest(),
            "captured_submission_matches_fixture": captured == KNOWN_DIFF,
            "model_calls": 0,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/burned-pilot/mini_submission_contract.json"),
    )
    args = parser.parse_args()
    result = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
