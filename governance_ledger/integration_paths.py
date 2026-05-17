"""Opt-in helpers for resolving local integration checkouts during development."""

from __future__ import annotations

import os
import sys
from pathlib import Path

LOCAL_INTEGRATIONS_ENV = "GOVERNANCE_LEDGER_USE_LOCAL_INTEGRATIONS"


def ensure_integration_paths(*, compiler: bool = False, guard: bool = False) -> None:
    """Prefer local integration sources only when explicitly enabled for dev work."""
    if os.environ.get(LOCAL_INTEGRATIONS_ENV) != "1":
        return

    for path in reversed(_candidate_paths(compiler=compiler, guard=guard)):
        if path.exists():
            path_text = str(path)
            if path_text not in sys.path:
                sys.path.insert(0, path_text)


def _candidate_paths(*, compiler: bool, guard: bool) -> list[Path]:
    package_root = Path(__file__).resolve().parents[1]
    workspace_root = package_root.parent
    monorepo_root = Path(__file__).resolve().parents[3]
    dev_integrations = workspace_root / "waveframe-dev" / "integrations"

    paths: list[Path] = []
    if compiler:
        paths.extend(
            [
                package_root / "integrations" / "contract-compiler" / "src",
                monorepo_root / "integrations" / "contract-compiler" / "src",
                dev_integrations / "contract-compiler" / "src",
                workspace_root / "cricore-contract-compiler" / "src",
            ]
        )
    if guard:
        paths.extend(
            [
                package_root / "integrations" / "guard",
                package_root / "integrations" / "proposal-normalizer",
                package_root / "integrations" / "cricore" / "src",
                monorepo_root / "integrations" / "guard",
                monorepo_root / "integrations" / "proposal-normalizer",
                monorepo_root / "integrations" / "cricore" / "src",
                dev_integrations / "guard",
                dev_integrations / "proposal-normalizer",
                dev_integrations / "cricore" / "src",
                workspace_root / "Waveframe-Guard",
                workspace_root / "proposal-normalizer",
                workspace_root / "CRI-CORE" / "src",
            ]
        )
    return paths
