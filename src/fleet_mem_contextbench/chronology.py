"""Strict task-time ordering used to construct historical candidate pools."""

from __future__ import annotations

from datetime import datetime

from .data import Task


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def source_precedes_target(source: Task, target: Task) -> tuple[bool | None, str | None]:
    source_time = parse_timestamp(source.created_at)
    target_time = parse_timestamp(target.created_at)
    if source_time is None or target_time is None:
        return None, "MISSING_OR_INVALID_TIMESTAMP"
    try:
        ordered = source_time < target_time
    except TypeError:
        return None, "INCOMPARABLE_TIMEZONES"
    return (True, None) if ordered else (False, "SOURCE_NOT_STRICTLY_EARLIER")


def temporal_distance_days(source: Task, target: Task) -> float | None:
    source_time = parse_timestamp(source.created_at)
    target_time = parse_timestamp(target.created_at)
    if source_time is None or target_time is None:
        return None
    try:
        return (target_time - source_time).total_seconds() / 86400
    except TypeError:
        return None
