# Interpret normalized terminal text without inventing an outgoing message

Baseline: `0823a319b188a70599b1d80a9426c6d8ac84423e`, PR #110.

## Evidence behind this correction

The independent follow-up in ChatGPT2GrokBot #87 passed the previous component
checks but did not fix the original R1/R2 reading complaint. Its replay report
shows two records for terminal-only responses:

- `assistant_message`, `phase=response`, sender equal to the exact agent path,
  no recipient, and `TERMINATE` or `<CAMEL_TASK_DONE>` as text;
- an `agent_message` with a display-name sender, not the agent path.

The previous annotation required an outgoing message kind even to explain the
text already displayed in the Response card. That excluded the model-response
shape produced by the existing SDK/normalizer. The synthetic positive fixtures
had supplied explicit outgoing kinds/paths and did not expose that mismatch.
The #87 replay verdict is retained; this record does not change it to PASS.

## Narrow change and preserved boundaries

I separated eligibility for a text-only interpretation from eligibility for an
earlier outgoing-message excerpt. An exact-source normalized `assistant_message`
with phase `response`, exact agent-path sender and no recipient can now receive
the existing terminal-text note. Quoted/truncated, injected and encrypted text
remain excluded. The note describes an exact text match, not protocol completion,
message delivery, task validation or an independent final answer.

The earlier-message `outgoing()` predicate is unchanged. Generic assistant
records, including repeated request context, are still not used as an earlier
outgoing-message excerpt. Neither display-name senders nor siblings gain identity
authority. A missing eligible earlier message remains missing. A separately
qualified earlier outgoing message may still be shown beside the original report.

The original Response selection and body are unchanged. Exact framework/source,
path and native-identity checks remain in force. Root rendering, other providers,
conversation indexing, raw evidence, model-output previews, file/hash access,
layout, capture and task-status interpretation are outside this change.

## Regression evidence

The new positive fixtures use the real default SDK serialization, not custom
`content_payload` fields: they record a model request, a model response and a
framework message using display-name participants. They assert the two normalized
shapes above before inspecting the shipped Dashboard. These are report-shaped
synthetic captures, not the original R1/R2 files or fresh model calls.

Three positive-path cases failed unchanged on the baseline. The new module also
checks the preserved earlier-message boundary, request/received/candidate phases,
addressed and inbound records, wrong/display-name senders, truncation, encryption,
injected context, quoted text and conflicting source/path/native identity.
Historical tests and their assertions are unchanged.

Final completed command results are recorded with the PR and validation bundle.
An initial combined command timed out after partial progress without a completed
JUnit result; it is not counted as a passing run. Subsequent groups run separately
and their disjoint counts may be reported without adding repeated attempts.

Validation uses Linux, Python 3.13.5, installed Chromium/Playwright and the shipped
renderer via `set_content`. Default SDK events pass through hashed content storage,
graph construction and the normal conversation index. Negative cases change copies
of normalized test data. These checks do not exercise native HTTP, Offline folder
verification, an installed package, original replay or other operating systems.

The baseline was reconstructed from the mounted exact-source bundle and validated
patches; its tree matched `7e76f1e98f918b68c9425ae781da1f04d9a8afd6` before editing.
Existing lint/watchdog wheels were installed offline from a mounted CI artifact,
without changing repository dependencies.

## Impact, rollback and remaining acceptance

This batch changes one production child-policy module, adds one regression module
and this record. Reverting the commit removes only the additional text-annotation
eligibility and tests; no captured bytes or metadata must be migrated. There are
no new endpoints, background polls, storage, dependency, workflow, version, tag,
release or main-branch changes.

A new follow-up on #87 must use this batch's exact commit and replay copies of the
original R1/R2 files. It must confirm the note appears next to the unchanged token,
that unqualified earlier messages remain absent, and that no sibling content is
borrowed. It must not silently retarget the previous report or mark all of #75
fixed from one explanatory card. Native body verification and the wider buyer
acceptance gates remain separate. The implementation PR remains draft.
