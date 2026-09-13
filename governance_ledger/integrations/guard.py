"""Optional Waveframe Guard admissibility adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


AdmissibilityEvaluator = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class GuardIntegrationUnavailableError(RuntimeError):
    """Raised when optional Guard-backed admissibility replay is unavailable."""

    code = "LEDGER_GUARD_UNAVAILABLE"


class GuardReplayUnsupportedError(GuardIntegrationUnavailableError):
    """Guard is installed, but raw legacy replay is not a supported integration."""

    code = "LEDGER_GUARD_REPLAY_UNSUPPORTED"


def load_guard_admissibility_evaluator() -> AdmissibilityEvaluator:
    """Report the automatic replay compatibility boundary without executing code.

    Guard 0.19's callable evaluate_admissibility is a retirement stub. Native
    execution and saved logical replay belong to Guard's public SDK/store API.
    Applications can still explicitly inject their own replay evaluator.
    """
    try:
        import waveframe_guard  # noqa: F401; deliberately lazy optional import
    except ImportError:
        raise GuardIntegrationUnavailableError(
            "Waveframe Guard is not installed. Raw contract/execution-state replay "
            "requires an explicitly injected evaluator. The governance-ledger[guard] "
            "extra enables native SDK execution and saved logical replay; installing "
            "it does not restore the retired legacy replay API."
        ) from None

    raise GuardReplayUnsupportedError(
        "Waveframe Guard is installed, but automatic raw contract/execution-state "
        "replay is unsupported with Guard 0.19: evaluate_admissibility is retired. "
        "Use replay_admissibility(evaluator=...) with an explicit evaluator, or "
        "Guard's supported SDK/store replay(run_id) for saved native execution. "
        "Installing governance-ledger[guard] does not restore the retired API."
    ) from None
