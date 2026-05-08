from governance_authoring import build_review_report, extract_constraints, review_constraints


def test_builds_review_report_with_source_text():
    text = """
    Transfers above $1M require manager approval.
    Proposer and approver must be separate.
    """
    policy = extract_constraints(text)

    report = build_review_report(text, policy)

    assert report == {
        "detected_constraints": [
            {
                "type": "required_role",
                "value": "manager",
                "source_text": "require manager approval",
            },
            {
                "type": "separation_of_duties",
                "value": True,
                "source_text": "must be separate",
            },
            {
                "type": "approval_threshold",
                "operation": "transfer_funds",
                "value": 1_000_000,
                "source_text": "above $1M",
            },
        ],
    }


def test_review_constraints_extracts_and_reports():
    report = review_constraints("Only compliance may approve transfers.")

    assert report == {
        "detected_constraints": [
            {
                "type": "required_role",
                "value": "compliance",
                "source_text": "Only compliance may",
            },
        ],
    }
