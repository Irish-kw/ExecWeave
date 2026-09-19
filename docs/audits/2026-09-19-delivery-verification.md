# Delivery verification: export receipt, final synchronization, selected archive

Baseline: `c0c33284418107ab7fce6a9ae0ee12ba7b1a2efe`, PR #110.
Scope: partial W01/W08 delivery. Task validation, full source coverage, handoffs,
workflow layout, and large-run acceptance are still open.

## User-facing behavior

I separated three different delivery facts in Run assessment:

- **Recorded export check** reports the bounded result returned by the existing
  finalization verifier. It is an export-time receipt, not a fresh filesystem audit.
- **Conversation synchronization** reports the existing final-history request.
  Failed synchronization preserves history and offers an explicit retry. Embedded
  static history is not reported as a successful live-server synchronization.
- **Selected archive verification** checks the exported folder selected by the
  reader. It hashes the three primary files and every content reference declared
  by the graph/conversation indexes, including named graph expansion clusters.
  Success is explicitly scoped to those selected files, not all raw telemetry,
  provider recall, task quality, authenticity, or equivalence to the current tab.

A collapsed-by-default delivery disclosure keeps status summaries visible without
pushing agent content below the initial viewport. Expanding it exposes verification
and retry controls; its state survives status updates and resets on run changes.

There is no automatic workspace scan, new server endpoint, or second polling loop.
Only canonical run-local content paths are accepted. Nothing is executed or read
from paths found inside provider bodies. The verification result is never written
back into `viewer.html`: doing so would invalidate the receipt's viewer hash.

The browser rejects missing files, mismatched hashes/sizes, conflicting references,
unsupported receipts, duplicate decoded JSON keys, and mismatched run/source scope.
Empty/binary payloads can be byte-verified without claiming they are readable text.
Verification is bounded to 64 MiB per file, 256 MiB total, a 16 MiB receipt,
100,000 selected files/references, and bounded JSON parsing. Budget exhaustion,
missing native cryptography, cancellation, and the 120-second UI deadline do not
produce a complete verdict. Browser file selection itself is not a streaming API;
this is not full large-run memory acceptance. An in-flight native read/hash may
finish after cancellation, but its result cannot update another run.

## Synchronization and compatibility

The existing synchronizer now publishes explicit status and binds requests to an
execution generation. Old requests cannot update new-run history or report new-run
success. Malformed entries, partial HTTP responses, and explicit scope mismatches
are rejected. The original authenticated fetch call and existing stop/retry APIs
remain; default preview callers, raw messages, and existing tests are unchanged.

New conversation indexes include session/source identity. Legacy responses lacking
identity remain readable, but the panel explicitly says the session was not checked.
Reading a response does not prove provider completeness or task success.

## Regression found in the previous commit

`c0c3328` failed the mirrored-tool browser invariant on all three CI operating
systems. Its static bootstrap added derived `run_assessment` metadata to the object
exposed by `getGraph()`. Nodes and edges were unchanged, but the browser's raw graph
was no longer equal to its input. The Ubuntu viewer suite reported 2 failed and
353 passed; local baseline reproduction reported 2 failed and 10 passed.

The bootstrap now publishes assessment beside the raw graph, with the same scope
validation. The original mirrored-tool tests and assessment tests pass unchanged.
Do not weaken raw-graph equality or remove assessment functionality to resolve this.

## Verification

Source provenance: package artifact `10557290448`, ZIP SHA-256
`186d38bd8ea45724c2b9e0cdcf5dccece23eac990d0a8a8d65d7a83895477edf`;
full repository bundle artifact `10557510125`, ZIP SHA-256
`8c852d8b77869a2a16707bff7a3ccb29a81098a2c6cfc3b9121460a66741f820`.
Both point to source tree `6e75188c44d05f8b9a65f720fde153b8cb56ffad`.
The full bundle supplies unchanged historical tests, not just production modules.

```sh
PYTHONPATH=src EXECWEAVE_E2E_CHROMIUM=/usr/bin/chromium python -m pytest -q \
  tests/test_delivery_status.py tests/test_delivery_status_browser.py
# 89 passed after adding two delivery-disclosure regressions.

PYTHONPATH=src EXECWEAVE_E2E_CHROMIUM=/usr/bin/chromium python -m pytest -q \
  tests/test_projection_tool_mirror_identity.py tests/test_run_assessment.py
# 77 passed, including the unchanged historical equality assertions.

PYTHONPATH=src python -m pytest -q \
  tests/test_conversation_access.py tests/test_content_integrity.py \
  tests/test_content_integrity_portability.py tests/test_audit_closure_20260917.py \
  tests/test_history_publication_http.py tests/test_live.py tests/test_live_auth.py
# 113 passed.
```

Before the two disclosure regressions were added, the combined first two groups
reported 164 passed and pytest returned 0.
The command transport timed out after those results; separate invocations above
were used to confirm execution rather than treating that timeout as a clean exit.
Ruff, Python compilation, and assembled JavaScript syntax checks pass. Local stage
integrity preserves all 1,800 baseline test node IDs, with no new skip/xfail markers
and no release metadata change. The existing hash-pinned fixture exception is
unchanged; no additional existing-test exception is needed.

The new checks include native Node WebCrypto with the production verifier,
actual Chromium DOM/file-chooser interactions, a real failed portable workload
with a complete exported archive, and the authenticated Live HTTP handler.
Mocked synchronization responses are explicitly component tests, not native HTTP.

Two committed native browser acceptance cases separately attempt real HTTP and
`file://` navigation, native browser SHA-256, folder selection, and later tampering.
Both were attempted locally and blocked at navigation by environment policy
(`ERR_BLOCKED_BY_ADMINISTRATOR`). Three historical navigation cases encountered
that same restriction. These are **not passes**. No browser-policy bypass,
cryptographic substitute, new skip, or relaxed assertion is committed.

Local runtime: Linux/Python 3.13.5 and Chromium. Python 3.10/3.12 three-OS CI,
installed-wheel checks, the full historical suite, fresh model-provider captures,
and independent user acceptance remain separate gates on the new head.

## Change impact and rollback

| Area | Change and preservation boundary |
|---|---|
| `live_core.py`, `delivery_status.py` | Publish existing verifier receipts in all Live envelope kinds; no archive rereads, raw mutation, new endpoint, or change to finalization acceptance. |
| `_conversation_records_core.py` | Add response identity without changing entries or interpreting message bodies. |
| `dashboard_shell.py`, `viewer_conversation_sync.py` | Keep original lifecycle seams and authentication; add scoped state, stale-response rejection, and existing-loop restart on an actual run change. |
| `_dashboard_shell_base.py`, `viewer_run_assessment.py` | Separate derived bootstrap metadata from raw graph; retain singleton panels, inspector CSS, scope checks, and history DOM. |
| `viewer_delivery_status.py`, `viewer_archive_verifier.py` | Manual read-only verification, explicit limits/cancellation, no body execution or automatic network access. |

No recorder, dependency, workflow, existing test, package version, release metadata,
raw event, or captured-content hash is changed. The delivery feature can be reverted
with its publication/UI hooks; retain the separate static assessment bootstrap and
its raw-graph invariant. Existing archives are not migrated or rewritten. Verification
covers declared graph/conversation references, not every export route or raw event.
