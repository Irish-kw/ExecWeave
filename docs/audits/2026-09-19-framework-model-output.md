# Framework model output in the agent inspector

Baseline: `7e0b4c71709d439b6d53897061dc4684374a0989` (PR #110).
Related finding: ChatGPT2GrokBot #83, R3 / original #75.

## Problem and bounded repair

The buyer replay reports model bodies present in the MetaGPT conversation ledger
while a later agent report says "No actions taken yet." I am not replacing that
report with a model response or treating generated code as a verified task result.

The conversation index now retains a separate, versioned model-response preview
on its original content-reference entry before conversation merging. Publication
requires a unique graph agent ID, a framework-agent scope, an explicit
HAS_MODEL_CONTENT relationship, a recognized CAMEL/AutoGen/MetaGPT model_response
content kind, and no inferred/view-only flags. Duplicate source identities are
withheld. Request context and model-failure records do not become response output.

The agent inspector shows **Captured model output** above the existing reported
response. The latest captured response preview starts expanded. Older records
remain individually expandable, 25 at a time, with lazily populated bodies and
the existing full-content reader. The source link keeps the original path/hash;
opening it still uses the existing authentication, local-folder and integrity
checks. This is a count of content records, not unique model invocations.

Only the exact source agent is eligible. Labels, sibling paths, shared models and
parent/root fallbacks do not provide ownership. Existing reported outcomes and
conversation history are retained, not rewritten. Expanded/collapsed records use
the existing per-agent fold-state mechanism.

## Scope and impact

Five files change: the conversation-index core, the shared Dashboard shell, one
small model-output renderer, one new regression module and this record.

The new model_response_preview field is additive to freshly generated Live and
static conversation indexes. Older indexes without it remain readable but do not
magically acquire the new preview; regenerating the viewer/index from preserved
capture is required. The ordinary and extended investigation indexes retain the
same conversation projection. No extra filesystem reads or network requests are
added: the preview reuses the content already parsed for that index entry.

Preview text remains limited by the existing normalizer (6,000 characters per
message, at most 80 messages per record). Source completeness and byte integrity
are not certified by seeing a preview. Empty/unparseable response bodies, unknown
frameworks, missing raw content and missing owners are not reconstructed. Copying
the per-record preview increases index size; large-run performance is not measured
by this batch. Raw events, body bytes/hashes, recorder behavior, authentication,
layout, final-sync, package version and existing tests are unchanged.

The shared shell installs the renderer inside the existing inspector closure with
explicit seam checks; the historical agent-panel source stays unchanged.

Rollback: remove the preview publication and renderer integration together with
the new renderer module. This removes the new browsing path, not captured evidence.

## Verification

The exact baseline tree was reconstructed from the mounted Actions source bundle
and validated patches and matched `78a59b2b5b047e09c752cf0e524421fde6385481`.
Local environment: Linux, Python 3.13.5, system Chromium, Playwright.

The same final 13 new cases produced **7 failed / 6 passed** on the unchanged
baseline and **13 passed** on the repaired implementation. The completed focused
run, including unchanged framework conversation/privacy, index opt-in and default
agent-panel tests, produced **30 passed**, with no skipped/deselected cases. Counts
overlap; they are not additive.

The tests build real SDK events and content-addressed files using synthetic
model responses, normalize them through the actual graph/conversation pipeline,
and exercise the complete shipped Dashboard in Chromium. They cover three
frameworks, same-name participants, shared-model isolation, later status reports,
original source references, request/failure exclusion, conflicting identities,
malformed attribution flags, HTML escaping, fold retention and record pagination.
The source-reader action is checked through its native folder-required state,
not represented as completed native Offline reading.

Initial fixture development used an unavailable MetaGPT convenience method; that
setup error was corrected to the shared SDK MessageRecord API before the final
baseline/repair comparison. An earlier baseline command timed out before a final
report. A lazy-render candidate exposed a queued-toggle timing issue; populating
on opening activation resolved it without changing the final test assertions.

The original R3 release ZIP could not be downloaded in this environment (direct
GitHub hostname resolution failed). Therefore this is **synthetic SDK/component
verification**, not a replay of R3, fresh model execution, all-provider validation
or buyer acceptance. Grok must rerun the original frozen R3 package on the new
commit and confirm each role's actual body/source path. The original buyer failure
remains open until that evidence exists. No merge or release is justified here.
