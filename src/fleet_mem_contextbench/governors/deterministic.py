"""Fixed rules baselines; no target relationship labels are accepted."""

from __future__ import annotations

import re
from typing import Any, Sequence

from .base import Decision


class DeterministicGovernor:
    name = "deterministic_conservative_binary_v2"

    def decide_write(self, candidate: dict[str, Any]) -> Decision:
        outcome = candidate.get("source_outcome", {}).get("status", "unknown")
        evidence = candidate.get("evidence", [])
        provenance_ok = bool(candidate.get("provenance_hash")) and bool(evidence)
        kind = candidate.get("memory_type")
        generality = candidate.get("generality")
        risk = candidate.get("negative_transfer_risk")
        if not provenance_ok:
            action, reason = "DO_NOT_SHARE", "missing source provenance or evidence"
        elif kind == "EPISODIC_EXAMPLE":
            action, reason = "DO_NOT_SHARE", "episodic example is not promoted by this fixed baseline"
        elif outcome != "verified_pass":
            action, reason = "DO_NOT_SHARE", "source outcome is not canonically verified as a pass"
        elif generality is not None and generality >= 0.6 and (risk is None or risk <= 0.5):
            action, reason = "SHARE", "evidence-backed generalizable lesson passed fixed thresholds"
        else:
            action, reason = "DO_NOT_SHARE", "candidate lacks the fixed generality threshold"
        result = Decision(action, confidence=1.0, rationale=reason)
        result.validate("write")
        return result

    def decide_read(self, target: dict[str, Any], pool: Sequence[dict[str, Any]]) -> Sequence[Decision]:
        target_words = _words(str(target.get("problem_statement", "")))
        scored: list[tuple[float, int]] = []
        for entry in pool:
            memory = entry.get("memory", entry)
            text = f"{memory.get('claim', '')} {' '.join(memory.get('files_or_symbols', []))}"
            words = _words(text)
            score = len(target_words & words) / max(1, len(target_words | words))
            scored.append((score, len(scored)))
        best = max((score for score, _ in scored), default=0.0)
        decisions = []
        for score, _ in scored:
            if score == best and best >= 0.04:
                action = "EXPOSE"
            else:
                action = "WITHHOLD"
            result = Decision(action, confidence=min(1.0, score * 10), rationale="fixed lexical overlap rule")
            result.validate("read")
            decisions.append(result)
        return decisions


class ShareAllPolicy:
    """Reference write baseline: every source card is promoted."""

    name = "share_all"

    def decide_write(self, candidate: dict[str, Any]) -> Decision:
        return Decision("SHARE", confidence=1.0, rationale="Share-All control")


def fixed_read(target: dict[str, Any], pool: Sequence[dict[str, Any]], limit: int = 3) -> list[Decision]:
    """Expose the three newest available memories in every fixed-read arm."""
    selected = set(range(max(0, len(pool) - limit), len(pool)))
    return [
        Decision("EXPOSE" if index in selected else "WITHHOLD", confidence=1.0 if index in selected else 0.0,
                 rationale="fixed recency top-k control")
        for index, _ in enumerate(pool)
    ]


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9_]{3,}", text.lower()) if word not in {"the", "and", "for", "with", "from", "this", "that", "issue", "task"}}
