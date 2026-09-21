# Exact message-group navigation

Baseline: `6a144b3047387a6867be129013247125e4a4a37e`, PR #110.

## Reading gap

The buyer report in ChatGPT2GrokBot #83 describes an empty AutoGen message-node
panel. A framework group carries explicit participants and raw routing-edge IDs,
while the investigation index already carries separate native message records and
registered body references. The default node inspector did not connect these two
surfaces. This batch adds that connection, not a new recorder or message parser.

Selecting an eligible framework message group now shows **Recorded message
handoffs** in the inspector. Only the exact ordered sender/recipient pair is
selected. Each record expands using the existing investigation card and opens
its original reference through the existing content reader. This is two actions
from the selected-group panel to the body reader (expand, open). Missing bytes,
verification failures and Offline folder selection retain the reader's existing
rules. A folder-required prompt is not successful full-body reading.

## Boundaries

The group must have unique raw framework-agent participants and uniquely resolved
MESSAGE_SENT/MESSAGE_RECEIVED evidence edges agreeing with that ordered pair.
Inferred, viewer-only, malformed and ambiguous raw support cannot authorize the
list. Only identity-bound, uniquely keyed index records qualify. Same names,
reverse routes, sibling routes and shared models are not substitutions. Sent and
received records remain distinct observations; neither proves consumption.

The panel pins a copy of the accepted route rows. A new accepted index raises a
notice rather than replacing an expanded record. Its explicit action uses the
latest accepted index locally; if Live has no versioned index, the shared
authenticated reader must return true AND publish an accepted index. Missing
inventory is not zero activity. Older offline exports without an index need
regeneration; this patch does not reconstruct their missing data.

Selection/run changes invalidate pending UI completion. Withdrawing valid raw
routing support removes the body list rather than keeping it authorized. Records
are loaded in batches of 25 without text-based deduplication. The index's existing
10,000-row bound still applies; group support is capped at 100 routing-edge IDs.
Navigation is outside the original agent/task response content. Text is rendered
literally, with no HTML execution or automatic content fetch.

## Executed validation

- Baseline, same three framework navigation cases: 3 failed, 10 deselected.
  Each failed because the new message-body route was absent.
- Initial repaired module: 13 passed.
- Expanded final navigation module (16) plus unchanged model-output module (13):
  29 passed.
- Existing investigation backend cases: 39 passed, 7 browser cases deselected.
- Existing investigation browser cases: 7 passed, 39 backend cases deselected.
- Existing refresh-outcome cases: 15 passed.

The final groups cover 90 distinct cases; the baseline, initial and repeated runs
are not additional unique coverage. Ruff initially flagged semicolon formatting
in the new test file; formatting was corrected before final checks. No test
assertion, historical test, timeout, skip rule or CI policy was weakened.

These are synthetic SDK records through actual content storage, index generation
and Chromium DOM interactions. The native framework classes are AutoGen, CAMEL
and MetaGPT adapters, not fresh upstream model deployments. The new full-content
case reaches the actual folder-required state, not a completed native Offline
read. Controlled refresh promises are restricted to UI outcome/race tests. The
original R2 replay, native HTTP/Offline journey and fresh-provider coverage remain
unverified by this batch. Keep the buyer FAIL report until a separate exact-head
replay supports a narrower updated verdict.

Baseline source came from Actions artifact 10587310533, SHA-256
`c62a458896c0269cdd410af803862a545a5e9c213902695dfd28a99b0cd40b79`;
its checked-out tree matched `8b4ab623d4d3ee45fdc69e89e96189e6b4b62b1d`.

## Impact and rollback

Four files change: an additive reader module, the investigation reader's small
integration, a new regression module and this record. Existing investigation
cards gain an optional category argument; default behavior is unchanged. The
accepted-index and Dashboard update callbacks only schedule selection inspection.
There is no new endpoint, timer, filesystem read, capture behavior, ownership
solver, final-sync change, layout change, dependency or version bump.

Revert the new reader and its investigation integration together. Existing body
reading, model-output navigation and raw evidence remain intact. Full current-head
CI, original R2 replay and the broader work-package gates remain open. No merge,
tag, release or modification of main is included.
