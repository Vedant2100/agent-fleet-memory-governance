"""Small ContextBench-specific write/read governance interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


WRITE_ACTIONS = {"SHARE", "DO_NOT_SHARE"}
READ_ACTIONS = {"EXPOSE", "WITHHOLD"}


@dataclass(frozen=True)
class Decision:
    action: str
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    rationale: str = ""
    latency_ms: float | None = None
    cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def validate(self, stage: str) -> None:
        allowed = WRITE_ACTIONS if stage == "write" else READ_ACTIONS
        if self.action not in allowed:
            raise ValueError(f"{stage} action must be one of {sorted(allowed)}")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if self.probabilities is not None:
            if set(self.probabilities) - allowed or any(not 0 <= p <= 1 for p in self.probabilities.values()):
                raise ValueError("invalid decision probability map")
        for field_name, value in (("input_tokens", self.input_tokens), ("output_tokens", self.output_tokens)):
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be nonnegative")


class Governor(Protocol):
    name: str

    def decide_write(self, candidate: dict[str, Any]) -> Decision: ...

    def decide_read(self, target: dict[str, Any], pool: Sequence[dict[str, Any]]) -> Sequence[Decision]: ...


SourceTimeWriteGovernor = Governor
"""Write decisions receive exactly one source-only candidate and no target."""
