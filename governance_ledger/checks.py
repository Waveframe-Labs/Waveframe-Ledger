"""Operational checks for Governance-Ledger generated artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def check_validation_directory(generated_dir: str | Path) -> dict[str, Any]:
    """Return validation check results and error-severity warnings."""
    generated_root = Path(generated_dir)
    errors: list[dict[str, str]] = []

    for path in sorted(generated_root.glob("*.validation.json")):
        validation = json.loads(path.read_text(encoding="utf-8"))
        for warning in validation.get("warnings", []):
            if warning.get("severity") == "error":
                errors.append(
                    {
                        "file": str(path),
                        "type": warning.get("type", ""),
                        "text": warning.get("text", ""),
                    }
                )

    return {
        "status": "failed" if errors else "passed",
        "error_count": len(errors),
        "errors": errors,
    }


def format_check_summary(result: dict[str, Any]) -> str:
    """Format validation check results for CLI output."""
    lines = [
        "[Governance Ledger]",
        "",
        "Validation Check:",
        f"  {result['status']}",
        f"  {result['error_count']} error-severity warnings detected",
    ]
    for error in result["errors"]:
        lines.extend(
            [
                "",
                f"File: {error['file']}",
                f"  {error['type']}: {error['text']}",
            ]
        )
    return "\n".join(lines)
