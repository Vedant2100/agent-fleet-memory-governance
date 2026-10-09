#!/usr/bin/env python3
"""Run the frozen paired signal test with GPT-6 Luna after user-authorized bypass."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_sweedit_burned as pilot
from fleet_mem_contextbench.pilot_runtime import sha256_file


def main() -> int:
    settings = pilot.load_worker_settings(pilot.DEFAULT_WORKER_CONFIG)
    if settings["requested_model"] != "gpt-6-luna" or settings["reasoning_effort"] != "xhigh":
        raise RuntimeError("Luna signal run requires the frozen GPT-6 Luna xhigh worker config")

    # Amendment 07 authorizes the signal test after the earlier qualification stop.
    pilot._validate_qualification_freeze = lambda: None
    original_summary = pilot._signal_summary

    def summarize(*values):
        summary = original_summary(*values)
        summary.update({
            "development_amendment": "PILOT_DEVELOPMENT_AMENDMENT_07",
            "execution_adapter": str(Path(__file__).relative_to(ROOT)),
            "execution_adapter_sha256": sha256_file(Path(__file__).resolve()),
            "qualification_gate_bypass_authorized": True,
            "qualification_gate_bypass_reason": (
                "Development Amendment 07 authorizes the frozen signal test; "
                "the user selected GPT-6 Luna after API access was confirmed."
            ),
        })
        return summary

    pilot._signal_summary = summarize
    return pilot.main()


if __name__ == "__main__":
    raise SystemExit(main())
