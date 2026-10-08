"""Bindings for Jev/System-One and deliberative LLM implementations."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .base import Decision


WriteCall = Callable[[dict[str, Any]], Decision | dict[str, Any]]
ReadCall = Callable[[dict[str, Any], Sequence[dict[str, Any]]], Sequence[Decision | dict[str, Any]]]


class CallableGovernorAdapter:
    """Wrap controller functions without importing their runtime stack."""

    def __init__(self, name: str, write_call: WriteCall, read_call: ReadCall):
        self.name, self._write_call, self._read_call = name, write_call, read_call

    def decide_write(self, candidate: dict[str, Any]) -> Decision:
        _assert_no_target(candidate)
        result = _decision(self._write_call(candidate))
        result.validate("write")
        return result

    def decide_read(self, target: dict[str, Any], pool: Sequence[dict[str, Any]]) -> list[Decision]:
        _assert_no_hidden({"target": target, "pool": list(pool)})
        results = [_decision(row) for row in self._read_call(target, pool)]
        if len(results) != len(pool):
            raise ValueError("read governor must return one decision per candidate")
        for result in results:
            result.validate("read")
        return results


class JevSystemOneAdapter(CallableGovernorAdapter):
    """Jev/System-One baseline; bind the installed system's write/read methods."""

    def __init__(self, write_call: WriteCall, read_call: ReadCall):
        super().__init__("jev_system_one", write_call, read_call)


class DeliberativeLLMAdapter(CallableGovernorAdapter):
    """LLM governor baseline with a caller-supplied local or hosted transport."""

    def __init__(self, transport: Callable[[dict[str, Any]], dict[str, Any]]):
        def write_call(candidate: dict[str, Any]) -> dict[str, Any]:
            return transport({
                "stage": "write", "candidate": candidate,
                "allowed_actions": ["SHARE", "DO_NOT_SHARE"],
            })

        def read_call(target: dict[str, Any], pool: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
            response = transport({
                "stage": "read", "target": target, "pool": list(pool),
                "allowed_actions": ["EXPOSE", "WITHHOLD"],
            })
            decisions = response.get("decisions")
            if not isinstance(decisions, list):
                raise ValueError("LLM read response must contain a decisions array")
            if decisions and all(not isinstance(row, dict) or row.get("latency_ms") is None for row in decisions):
                total_latency = response.get("latency_ms")
                if isinstance(total_latency, (int, float)):
                    for row in decisions:
                        if isinstance(row, dict):
                            row["latency_ms"] = total_latency / len(decisions)
            if decisions and all(not isinstance(row, dict) or row.get("cost") is None for row in decisions):
                total_cost = response.get("cost")
                if isinstance(total_cost, (int, float)):
                    for row in decisions:
                        if isinstance(row, dict):
                            row["cost"] = total_cost / len(decisions)
            return decisions

        super().__init__("deliberative_llm", write_call, read_call)


def _decision(value: Decision | dict[str, Any]) -> Decision:
    if isinstance(value, Decision):
        return value
    if not isinstance(value, dict):
        raise TypeError("governor output must be a Decision or object")
    return Decision(
        action=str(value.get("action", "")), confidence=value.get("confidence"),
        probabilities=value.get("probabilities"), rationale=str(value.get("rationale", "")),
        latency_ms=value.get("latency_ms"), cost=value.get("cost"),
        input_tokens=value.get("input_tokens"), output_tokens=value.get("output_tokens"),
    )


def _assert_no_target(candidate: dict[str, Any]) -> None:
    forbidden = {
        "target", "target_id", "target_patch", "target_test_patch", "target_created_at",
        "relationship_type", "known_related", "gold_patch", "hidden_tests", "target_outcome",
    }
    def visit(value: Any) -> set[str]:
        if isinstance(value, dict):
            leaked = forbidden.intersection(value)
            for child in value.values():
                leaked |= visit(child)
            return leaked
        if isinstance(value, list):
            return set().union(*(visit(child) for child in value)) if value else set()
        return set()

    leaked = visit(candidate)
    if leaked:
        raise ValueError(f"write governor received target-side fields: {sorted(leaked)}")


def _assert_no_hidden(value: Any) -> None:
    forbidden = {"relationship_type", "known_related", "target_patch", "target_test_patch", "gold_patch", "hidden_tests"}
    if isinstance(value, dict):
        leaked = forbidden.intersection(value)
        if leaked:
            raise ValueError(f"governor input contains hidden fields: {sorted(leaked)}")
        for item in value.values():
            _assert_no_hidden(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_hidden(item)
