"""All-prior same-repository candidate construction, independent of relation labels."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .chronology import source_precedes_target, temporal_distance_days
from .data import Task
from .memory_schema import MemoryCandidate


_STOP = {
    "a", "an", "the", "and", "or", "but", "if", "while", "because", "as", "until",
    "of", "to", "in", "on", "at", "by", "for", "from", "with", "without", "into",
    "about", "above", "below", "under", "over", "between", "is", "are", "was", "were",
    "be", "been", "being", "this", "that", "these", "those", "it", "its", "i", "we",
    "our", "you", "your", "they", "them", "their", "he", "she", "his", "her", "not",
    "no", "nor", "then", "than", "when", "where", "which", "who", "what", "how", "why",
    "can", "could", "would", "should", "will", "may", "might", "must", "do", "does", "did",
    "have", "has", "had", "also", "just", "only", "other", "more", "most", "very", "such",
    "here", "there", "each", "all", "any", "both", "few", "many", "some", "same", "different",
    "new", "old", "one", "two", "first", "second", "last", "next", "now", "then", "still",
    "issue", "feature", "bug", "error", "request", "please", "thanks", "title", "number",
    "above", "below", "description", "summary", "problem", "steps", "example", "examples",
    "expected", "actual", "works", "working", "happens", "happen", "change", "changed", "changes",
    "function", "method", "class", "object", "file", "line", "code", "test", "tests", "testing",
    "system", "version", "user", "users", "because", "currently", "current", "see", "get", "got",
    "make", "made", "set", "return", "returns", "value", "values", "type", "types", "result",
    "results", "output", "shown", "shows", "give", "gives", "given", "call", "called", "using",
    "used", "use", "needed", "need", "want", "wanted", "allow", "allows", "support", "supports",
    "python", "django", "sympy", "matplotlib", "scikit", "sklearn", "github", "pull", "request",
}
_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_PATH = re.compile(r"(?:[\w.-]+/)+[\w.-]+")
_SYMBOL_STOP = {
    "none", "true", "false", "self", "cls", "init", "repr", "str", "int", "bool", "list",
    "dict", "tuple", "set", "object", "function", "class", "type", "bytes", "float", "complex",
    "python", "django", "sympy", "matplotlib", "scikit", "sklearn", "traceback", "exception",
    "valueerror", "typeerror", "attributeerror", "runtimeerror", "users", "user", "issue", "request",
    "model", "figure", "numpy", "import", "from", "print", "get", "post", "response",
}


def build_candidate_pool(
    target: Task,
    experiences: list[Task],
    memories: dict[str, MemoryCandidate],
) -> dict[str, Any]:
    """Include every strict-prior same-repository experience; labels are not accepted."""
    entries: list[dict[str, Any]] = []
    target_terms = _terms(target.problem_statement)
    target_symbols = _technical_symbols(target.problem_statement)
    target_paths = set(_PATH.findall(target.problem_statement))
    for source in experiences:
        if source.repo != target.repo:
            continue
        precedes, _ = source_precedes_target(source, target)
        if precedes is not True:
            continue
        memory = memories.get(source.task_id)
        if memory is None:
            raise ValueError(f"missing memory candidate for eligible source {source.task_id}")
        source_terms = _terms(source.problem_statement)
        shared_terms = sorted(target_terms & source_terms)
        source_symbols = _technical_symbols(source.problem_statement)
        shared_symbols = sorted(target_symbols & source_symbols)
        source_paths = _source_paths(source, memory)
        shared_paths = sorted(target_paths & source_paths)
        distance = temporal_distance_days(source, target)
        reasons = ["ALL_STRICTLY_EARLIER_SAME_REPOSITORY_HISTORY"]
        if len(shared_terms) >= 2:
            reasons.append("ISSUE_TEXT_OVERLAP")
        if shared_symbols:
            reasons.append("ISSUE_SYMBOL_MATCH")
        if shared_paths:
            reasons.append("ISSUE_PATH_MATCH")
        if distance is not None and 0 <= distance <= 365:
            reasons.append("WITHIN_ONE_YEAR_OF_TARGET")
        entries.append({
            "memory": memory.to_dict(),
            "entry_reasons": reasons,
            "public_similarity": {
                "shared_issue_terms": shared_terms[:12],
                "shared_symbols_in_issue_text": shared_symbols[:8],
                "shared_paths_in_issue_text": shared_paths[:8],
                "temporal_distance_days": round(distance, 3) if distance is not None else None,
            },
        })
    entries.sort(key=lambda item: (
        item["memory"]["created_at"] or "", item["memory"]["source_task_id"], item["memory"]["memory_id"]
    ))
    return {
        "target": target.public_target(),
        "candidate_pool": entries,
        "candidate_count": len(entries),
        "pool_hash": candidate_pool_hash(entries),
    }


def plausible_distractor_count(pool: dict[str, Any], known_source_ids: set[str]) -> int:
    """Count non-linked candidates with issue/path/symbol evidence of plausibility.

    Repository membership and chronology alone are not enough: a nearby but
    lexically unrelated task is not counted as a hard negative.
    """
    return sum(
        entry["memory"]["source_task_id"] not in known_source_ids
        and any(reason in entry["entry_reasons"] for reason in (
            "ISSUE_TEXT_OVERLAP", "ISSUE_SYMBOL_MATCH", "ISSUE_PATH_MATCH",
        ))
        for entry in pool["candidate_pool"]
    )


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9_]{3,}", text.lower())
    return {word for word, count in Counter(words).items() if word not in _STOP and count <= 8}


def _technical_symbols(text: str) -> set[str]:
    return {
        word for word in _SYMBOL.findall(text)
        if len(word) >= 5
        and ("_" in word or (word[0].isupper() and any(char.islower() for char in word[1:])))
        and word.lower() not in _SYMBOL_STOP
    }


def _source_paths(source: Task, memory: MemoryCandidate) -> set[str]:
    return set(memory.evidence_locations) | set(_PATH.findall(source.problem_statement))


def candidate_pool_hash(entries: list[dict[str, Any]]) -> str:
    import hashlib
    import json

    packed = json.dumps(entries, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()
