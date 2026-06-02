# UI Severity Semantics

Ledger UI severity labels describe governance posture, not infrastructure telemetry.

These labels are canonical for operator-facing UI surfaces. They should be used consistently across chips, queues, banners, registry rows, diagnostics, and future projection freshness surfaces.

## Canonical Labels

`informational`
: Context is available, but no operator action is implied.

`advisory`
: Governance awareness is useful. Publication or registration is not blocked.

`pending`
: Required governance interpretation, review, export, or registration work has not happened yet.

`review-required`
: Operator review is required before the next publication step.

`continuity-sensitive`
: Resume, supersession, revocation, or state posture may affect continued execution.

`replay-sensitive`
: Replay evidence, receipt binding, or lineage evidence affects future replay review.

`blocking`
: Ledger must not continue the requested workflow transition until the condition is resolved.

`invalid`
: A projection, semantic interpretation, or artifact is no longer causally valid for the current authority state.

`revoked`
: The authority is no longer valid as a governance posture and resumed execution should be reviewed against revocation semantics.

`superseded`
: A later authority version exists or is expected to replace this authority in lineage.

## UI Rules

- Use green only for complete, valid, or registered governance posture.
- Use orange for pending, review-required, continuity-sensitive, and replay-sensitive posture.
- Use muted gray for inactive, unavailable, informational, and unpublished posture.
- Use red only for invalid, blocking, revoked, or authority-conflict posture.
- Avoid generic alert language when governance posture language is available.
- Do not expose internal projection names as severity labels in primary operator surfaces.

## Boundary

These labels do not represent Guard admissibility decisions, Cloud operational state, or runtime enforcement outcomes. They describe Ledger's deterministic interpretation, publication, registry, continuity, replay, and lifecycle posture.
