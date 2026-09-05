"""Optional Waveframe Guard admissibility adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


AdmissibilityEvaluator = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class GuardIntegrationUnavailableError(RuntimeError):
    """Raised when optional Guard-backed admissibility replay is unavailable."""


def load_guard_admissibility_evaluator() -> AdmissibilityEvaluator:
    """Load the supported Guard evaluator only when replay explicitly needs it."""
    try:
        from waveframe_guard import evaluate_admissibility
    except ImportError:
        raise GuardIntegrationUnavailableError(
            "Admissibility replay requires an injected evaluator or the optional "
            "Waveframe Guard integration. Install governance-ledger[guard] to use "
            "the release-tested Guard integration."
        ) from None

    if not callable(evaluate_admissibility):
        raise GuardIntegrationUnavailableError(
            "The installed Waveframe Guard package does not expose the supported "
            "admissibility evaluator. Use an injected evaluator or a released, "
            "dependency-compatible Guard integration."
        )
    return evaluate_admissibility
