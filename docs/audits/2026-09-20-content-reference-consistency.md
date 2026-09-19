# Content-reader reference consistency

Baseline: `0ad62839e2f9d6590c410c7e1f3115fa1139b9fb`, PR #110.
Baseline tree: `401ffdf56ebad41623b12b1094869564e97a7154`.

## Defect and bounded repair

I found a mismatch between the reader's metadata resolution and the archive
validator's existing conflict policy. The reader selected the first matching
content node and overlaid the supplied reference. A supplied size could replace
a different graph-declared size; a matching ID could be overlaid with another
path/hash. Repeated graph declarations were not checked together. The existing
byte hash check still ran, but it did not establish agreement with the other
recorded declarations.

The reader now checks all published graph declarations matching the supplied
content ID or content path before starting a file read or HTTP request. Matching
IDs must be observed-content records with that same path/hash. Every known size
must be a nonnegative safe integer and agree. Disagreement produces an explicit
`conflicting_reference` state, with no first/last-writer resolution. Malformed
sizes retain the existing `invalid_reference` state. Retry reevaluates the
current graph rather than treating the earlier resolution as authority.

This is byte-reference consistency, not a new ownership or source-completeness
inference. Distinct content kinds can legitimately reference the same bytes;
those are allowed when identity and known sizes agree. Identical repeated
records are allowed. Source-completeness flags remain separate from byte size
and are not combined into a stronger claim. Missing legacy size information is
not fabricated; a known agreeing graph size can supply it. References supplied
by the existing inspector/index without an available graph-node copy retain
their existing reading path. This is not a requirement that all reader input
have a raw node, nor a full archive/index reconciliation or authenticity check.

## Scope and impact

Three files change: `viewer_content_browser.py`, one new regression module,
and this record. All body entry points share the same resolver, including model,
tool, message and historical-content links. The existing authenticated endpoint,
file chooser, 8 MiB bound, SHA-256 verification, run isolation, modal handling,
source recording and original bytes are unchanged. No extra reads, endpoints,
network calls, polling or persistent storage are added. No historical test,
dependency, workflow, package version or main-branch change is included.

Resolution scans the already-published node list as before, now checking every
matching declaration rather than only the first. This adds bounded-by-inventory
match bookkeeping; it is not a completed large-run benchmark. Removing this
reader-only check reintroduces the disagreement behavior without altering any
captured data. No schema migration is required.

## Executed validation

The baseline was reconstructed from the mounted exact 6a144b3 Actions bundle
and the validated message-navigation, folder-scope and modal-boundary patches.
Its complete tree matched the baseline above before changes.

- Identical thirteen new tests on unmodified baseline: **9 failed, 4 passed**.
- New tests, unchanged modal-boundary tests and unchanged folder-scope component
  tests on the repair: **29 passed, 3 native relocated-folder cases deselected**.
- Unchanged message-handoff (16), model-output panel (13) and content-reader
  assembly/idempotence (2): **31 passed**.
- Ruff on changed/new Python, Python compilation and `git diff --check`: PASS.

The two final test runs contain **60 distinct passing checks**, not a unique
count augmented by the failed-baseline run. Local environment: Linux,
Python 3.13.5, system Chromium/Playwright. New cases use synthetic reference
metadata in the shipped reader and real DOM interactions through `set_content`.
They test ID/path/hash/size disagreement, reversed declaration order, malformed
sizes, retry and consistent legacy/multi-kind references. They assert unchanged
graph data and no network request. They reach rejection or `folder_required`,
not verified native plaintext. File/digest/fetch APIs are not replaced.

The three native relocated-folder cases remain enabled in normal repository CI;
they were not rerun locally in this small consistency batch. Full current-head
CI, original R2/R3 replay, fresh providers and independent buyer acceptance are
not established by these focused tests. Previous #83/#85/#86 frozen reports are
not rewritten or retroactively promoted to PASS.
