# Repository policy language for catalog 1

Ledger 0.9.2 includes mandatory source coverage for
`waveframe.coding-agent.repository-change@1.0.0`. The correction was merged in
[PR #29](https://github.com/Waveframe-Labs/Waveframe-Ledger/pull/29).

Catalog 1 can issue a new policy only when every source clause matches its installed
repository language. It supports modifying existing repository files. Whole-document
prose, conditional permissions, create/delete actions and arbitrary paraphrases remain
outside this authoring path. Drafts can retain those clauses for human review.

## Accepted forms

Write complete, case-sensitive sentences with the final period. Surrounding whitespace
is retained in the source and ignored only when matching a sentence.

| Purpose | Accepted example |
| --- | --- |
| Allow one exact path | `Agents may modify README.md.` |
| Deny one exact path | `Agents must not modify secrets.txt.` |
| Allow a literal path prefix | `Agents may modify files under docs/.` |
| Deny a literal path prefix | `Agents must not modify files under deployment/.` |
| Allow two exact paths | `Agents may modify README.md and CHANGELOG.md.` |
| Require an acting role | `Repository changes may be made only by repository maintainers.` |

The role form accepts the installed repository role vocabulary: repository maintainers,
repository reviewers and security reviewers. A role requirement does not grant an
action. A new policy needs at least one affirmative path grant, even if every sentence
matches the language. Every proposed control still needs human confirmation and approval.

Paths are repository-relative literal values without whitespace, backslashes, `.` or
`..` segments, or repeated separators. Exact paths cannot end in `/`; prefixes must
end in `/`. A path containing `*` is a literal path, not a wildcard expression.
Quotes and backticks, if accepted as part of the path, remain literal bytes. Do not
quote a path expecting Ledger to remove the punctuation.

## Text that blocks approval

These examples remain reviewable but cannot issue through catalog 1:

- `Agents may modify README.md only after Tech Lead approval.`
- `Agents may modify files under docs/ if they log each change and obtain security approval.`
- `Agents may modify README.md. Tech Lead approval is required before editing.`
- `Agents may create files under docs/.`
- `Agents may delete obsolete.txt.`
- `Agents can modify README.md.`
- `Agents may modify README.md. Policy overview.`
- A title, scope statement, rationale or ordinary prose mixed into an otherwise supported policy.

Marking such a clause informational or acknowledging its unsupported portion cannot
make the policy eligible for approval. A separate prerequisite may condition an earlier
grant. The current deterministic language cannot establish that arbitrary prose is
non-normative, so the candidate refuses every unmatched clause. This is an explicit
restriction to evaluate before release, not general policy-document ingestion.

## Resolve a blocked draft

The refusal lists every unmatched clause, its exact text, and half-open UTF-8 byte
range `[start_byte, end_byte)`. Byte offsets differ from character offsets for Unicode
text. `inspect_policy_translation_proposal` exposes `source_coverage_blockers`.
`inspect_policy_translation_customer_coverage` exposes the same text and spans in
`approval_blockers`, and marks each blocking row with `blocks_approval: true` and
`Not currently enforceable`. A recognized grant can also be unenforceable because
another clause blocks the entire document.

Show these transient blockers alongside the canonical review. The review preserves
the declared human coverage decision, including an informational label. That recorded
decision does not override current approval eligibility. Blocker views are not new
canonical schema fields and are not part of the commitment hash.

Keep the original document and all conditions intact. A policy owner can correct a
genuine typo or author a separately reviewed, explicitly scoped controlled-language
policy as a new source revision. They must resolve applicability and retain the
relationship to the original policy. Ledger does not automate that migration. Removing
a prerequisite, trimming source to a grant, or calling normative text context does not
provide the required support. If an applicable condition is unsupported, defer authority
until an enforcement path exists. Ask for clarification when meaning is uncertain.

There is currently no verified automatic exemption for headings or context, no
source-preserving free-form import path, and no new approval/logging control supplied
by this correction. Those are separate product decisions. Authors who need whole
manuals should keep the draft for review rather than strip it to force approval.

## Verify an old artifact or issue a new one

`validate_policy_translation_commitment` verifies historical artifact consistency by
default, like the bundle and receipt validators. A valid result can preserve an old
false-full declaration; it does not prove complete source meaning, authenticate the
reviewer, approve current issuance or authorize runtime activation.

Pass `require_supported_source=True` to additionally check today's source-language
eligibility during standalone verification. That option is only a source check and
cannot create approval. New approval, commitment construction and v2/v3 finalization
always require the source check, including when given an old approval. Those issuance
APIs expose no flag to bypass it. Historical verification cannot be used as a new
issuance permission. Existing-authority activation remains outside this correction.

See [the translation API and evidence chain](UNTRUSTED_POLICY_TRANSLATION.md) for
canonical source, review, confirmation and publication behavior.
