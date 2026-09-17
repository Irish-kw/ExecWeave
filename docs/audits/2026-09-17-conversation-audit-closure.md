# Conversation and artifact audit repair — 2026-09-17

## Scope and release boundary

Base: `Irish-kw/ExecWeave`, main `21bc7ff627750170ca6d31ea6c4220ac62a48861` (0.8.32).
This is a repair candidate, not a release or an assertion that all providers passed.
No version bump, merge, tag, or release is included. All regression fixtures are synthetic;
no uploaded user conversations, events, content blobs, or screenshots are committed.

## Repairs

- Retain an explicit inference occurrence ID when publishing Ollama exchanges under
  the run root. Equal text/local ordinals from different requests must not collapse.
  Preserve request/response surface provenance when merging an already merged preview.
- Render each agent round, including the latest, as a disclosure. Render model
  inference occurrences separately instead of flattening their complete chronology
  into one string. Remember user choices across refreshes, incremental updates,
  node switching and live-to-finished synchronization.
- Store fold booleans under opaque run/node/round keys in same-origin localStorage;
  do not store message text. Blocked storage degrades to in-page state. This does
  not transfer preferences across origins, browser profiles, or computers.
- Always perform the final authoritative conversation fetch, even without a selected
  agent. Validate the response before replacing the index; use a bounded request;
  stop periodic polling at finish; expose a visible manual retry after failure.
- Materialize evidence counts and observed workload outcomes in graph artifacts.
  Missing counts display as unknown, not zero. Recorder completion is independent
  of succeeded/failed/interrupted/collector-failed/unknown workload states.
- Preserve counts/outcomes in compact final payloads. Record interpreter/package
  provenance for new sessions; do not relabel older recordings as a newer version.
- Remove the initial camera's 0.5 zoom floor, fold exact Python cache paths into an
  expandable evidence-preserving display aggregate, and compact small framework
  message graphs without changing their raw edges or evidence semantics.
- Permit the MetaGPT team acceptance workload to share its current recording
  directory. Reject non-empty foreign or completed acceptance output directories.
- Decode active Codex hook transport as strict UTF-8 independently of terminal
  encoding. Capture fields independently so a malformed input cannot erase a valid
  output; retain a structured field-level failure and strict-mode failure result.
  The panel distinguishes archived references from content that was not observed.
- Write a durable finalization manifest with required artifact sizes and hashes.
  Attempt to export a valid terminal stream even when collection raises. Preserve
  the original error; export completion is not workload success.

## Local verification

Command:

```sh
python -m pytest -q tests/test_audit_closure_20260917.py tests/test_audit_closure_viewer_20260917.py
```

Result: **25 passed, 2 skipped**. Python compilation and `git diff --check` also passed.
This is the newly added regression suite, not the repository's full existing suite.

Key executed cases:

- Full content-store -> graph -> conversations.json round trip for 125 equal-text
  Ollama exchanges: 250 messages, every occurrence preserved, no middle truncation.
- 200-round browser history; a selected old round remains open after adding round
  201 and after switching nodes; old automatic-latest defaults do not become
  permanent user overrides.
- Twelve separately foldable model invocations and node-switch preservation.
- Final conversation sync with no selected node; no subsequent periodic fetch.
- Malformed final response preserves the previous history, reports the failure,
  and recovers via the visible Retry sync button.
- Known/unknown counts, observed failure outcome, safe shared output placement,
  cache evidence conservation, UTF-8 transport, independent tool-result capture,
  and incomplete-export manifest rejection.

Skipped locally:

1. True-origin reload/storage isolation: the sandbox browser prohibits navigation.
   The test is present and must execute in ordinary Chromium/CI.
2. The native live collector-error/export path: this sandbox lacks `watchdog`.
   The test is present and should execute with the project's declared dependencies.

The current full three-OS CI matrix has **not been run on this patch**. The 0.8.32
source distribution used for local work does not include the pre-existing tests.

## Uploaded-run replay, not a fresh provider execution

Seven recorded runs were re-materialized with the candidate. At a 1600x1000 browser
viewport, each had zero clipped displayed nodes, zero node-rectangle overlaps,
and zero JavaScript page errors. These measurements do not prove optimal edge
routing, aesthetics, accessibility at every scale, or live/cross-platform parity.
The original graph evidence and recorded exit outcomes are not rewritten.

## Open acceptance requirements

- Run the entire repository suite and the six-job OS/Python matrix.
- Run real Windows/Linux/macOS provider acceptance, including long Ollama sessions.
- Re-run MetaGPT with its native dependencies and the same active output directory.
  The directory collision is a definite script defect; missing original stderr
  prevents proving that it was the first/only cause of the uploaded failed run.
- Re-run Antigravity finalization. Offline regeneration recovered the missing output
  files, but it does not distinguish an original export fault from omitted packaging.
- Re-run Codex tool calls on Windows and verify complete input/output bytes. Existing
  missing output blobs cannot be reconstructed merely from a character count or
  an ambiguous transcript ID; do not fabricate those joins.
- Re-record Ollama using this same candidate. Uploaded 0.8.28 evidence remains 0.8.28.
- Review the new initial layouts visually; passing clipping/overlap checks is not a
  blanket claim that every graph is aesthetically finished.
