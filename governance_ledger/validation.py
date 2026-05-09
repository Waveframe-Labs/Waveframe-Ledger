"""Deterministic authoring validation for governance policy text."""

from __future__ import annotations

import re
from typing import Any

from governance_ledger.extract import _normalize_text
from governance_ledger.patterns import (
    AMBIGUOUS_AUTHORITY_PATTERNS,
    GOVERNANCE_SIGNAL_PATTERN,
    ROLE_PATTERNS,
    SEPARATION_PATTERNS,
    THRESHOLD_PATTERNS,
    UNSUPPORTED_CONSTRAINT_PATTERNS,
)


def validate_authoring(text: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Surface unsupported, ambiguous, or unextracted governance language."""
    normalized_text = _normalize_text(text)
    warnings: list[dict[str, str]] = []

    for pattern in UNSUPPORTED_CONSTRAINT_PATTERNS:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            _append_unique_warning(
                warnings,
                {
                    "type": "unsupported_constraint",
                    "severity": "warning",
                    "text": match.group(0),
                },
            )

    for pattern in AMBIGUOUS_AUTHORITY_PATTERNS:
        for match in re.finditer(pattern, normalized_text, flags=re.IGNORECASE):
            _append_unique_warning(
                warnings,
                {
                    "type": "ambiguous_authority",
                    "severity": "error",
                    "text": match.group(0),
                },
            )

    covered_spans = _covered_spans(normalized_text)
    warned_spans = _warning_spans(normalized_text)
    for sentence in _governance_sentences(normalized_text):
        if _has_overlap(sentence["span"], covered_spans) or _has_overlap(sentence["span"], warned_spans):
            continue
        _append_unique_warning(
            warnings,
            {
                "type": "extraction_gap",
                "severity": "warning",
                "text": sentence["text"],
            },
        )

    return {"warnings": warnings}


def _covered_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in [*ROLE_PATTERNS, *SEPARATION_PATTERNS, *THRESHOLD_PATTERNS]:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            spans.append(match.span())
    return spans


def _warning_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for pattern in [*UNSUPPORTED_CONSTRAINT_PATTERNS, *AMBIGUOUS_AUTHORITY_PATTERNS]:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            spans.append(match.span())
    return spans


def _governance_sentences(text: str) -> list[dict[str, Any]]:
    sentences: list[dict[str, Any]] = []
    for match in re.finditer(r"[^.!?]+[.!?]?", text):
        sentence = match.group(0).strip()
        if sentence and re.search(GOVERNANCE_SIGNAL_PATTERN, sentence, flags=re.IGNORECASE):
            sentences.append({"text": sentence, "span": match.span()})
    return sentences


def _has_overlap(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < covered_end and end > covered_start for covered_start, covered_end in spans)


def _append_unique_warning(warnings: list[dict[str, str]], warning: dict[str, str]) -> None:
    if warning not in warnings:
        warnings.append(warning)
