from governance_ledger import (
    build_review_report,
    extract_constraints,
    validate_authoring,
    validate_constraints,
)


def test_detects_unsupported_governance_language():
    report = validate_constraints("Transfers require reasonable approval timing.")

    assert report == {
        "warnings": [
            {
                "type": "unsupported_constraint",
                "severity": "warning",
                "text": "reasonable approval timing",
            },
        ],
    }


def test_detects_ambiguous_authority_language():
    policy = extract_constraints("Transfers require appropriate manager approval.")

    report = validate_authoring(
        "Transfers require appropriate manager approval.",
        policy,
    )

    assert report == {
        "warnings": [
            {
                "type": "ambiguous_authority",
                "severity": "error",
                "text": "appropriate manager",
            },
        ],
    }


def test_detects_extraction_gaps_for_unmatched_governance_sentences():
    report = validate_constraints("Transfers shall be reviewed quarterly.")

    assert report == {
        "warnings": [
            {
                "type": "extraction_gap",
                "severity": "warning",
                "text": "Transfers shall be reviewed quarterly.",
            },
        ],
    }


def test_review_report_includes_authoring_warnings():
    text = (
        "Transfers above $1M require manager approval. "
        "Transfers require reasonable approval timing."
    )
    policy = extract_constraints(text)

    report = build_review_report(
        text,
        policy,
        review_id="review-003",
        created_at="2026-05-07T20:16:00Z",
    )

    assert report["detected_constraints"] == [
        {
            "type": "required_role",
            "value": "manager",
            "source_text": "require manager approval",
        },
        {
            "type": "approval_threshold",
            "operation": "transfer_funds",
            "value": 1_000_000,
            "source_text": "above $1M",
        },
    ]
    assert report["warnings"] == [
        {
            "type": "unsupported_constraint",
            "severity": "warning",
            "text": "reasonable approval timing",
        },
    ]
