# 0.8.34 buyer remediation — first content-reading slice

Date: 2026-09-18. Planning parent: `82e0d54ed1e5be40029983633a8e10e0c1f88af8`.
Baseline product: v0.8.33, `b2bdd9e4e2acf0e035f94f935e167769ca9adcea`.
Scope: W02/W04 partial implementation. This is not a release or full buyer acceptance.

## Implemented

- Add on-demand Read input / Read output controls to the existing inspector's tool
  occurrence reference metadata, and the same component to model occurrence
  reference cards that already exist. No owners, calls, routes, or content are
  invented. Provider-specific model histories that do not reach these cards are
  not repaired by this slice.
- Open captured UTF-8 content inside a plain-text dialog, not a workspace file or
  an external application. Show source completeness separately from byte integrity.
- Reuse the existing run-local authenticated content route. Only canonical
  `content/sha256/<sha256>.<json|txt|bin>` references with matching hashes are
  eligible. Do not parse arbitrary agent messages or tool output for paths.
- Verify full bytes with browser SHA-256 before displaying text. Distinguish
  invalid reference, missing blob, unauthorized, size/hash mismatch, unsupported
  binary content, unavailable verification, partial HTTP response, timeout and
  run change. None of these silently becomes a provider visibility claim.
- Bound reads at 8 MiB and display at 16,384 UTF-16 units per page, preserving
  surrogate pairs. Search the complete loaded text and copy it explicitly. Larger
  content is explicitly unsupported by this in-browser slice, not silently cut.
- Keep one active content dialog with no persistent plaintext cache. Abort previous
  retrieval on close/retry/new content; ignore late responses and run changes.
- For static/offline pages, require explicit selection of the exported run folder.
  Match its captured content paths, read on demand and verify bytes. Do not fetch
  file URLs, scan the current workspace, or claim that archive closure is proven.
- Integrate through one additive shared-shell component. Existing renderer source,
  raw graph, identity policy, fold state, finalization and collectors are unchanged.

## Local verification and limits

The environment cannot resolve GitHub through local git and prohibits Chromium
navigation to loopback HTTP (`net::ERR_BLOCKED_BY_ADMINISTRATOR`). Therefore:

| Check | Actual result |
|---|---|
| New Python modules compile / parse | PASS |
| Additive/idempotent HTML component unit test | PASS |
| Chromium component tests with explicit test-only fetch/response and SHA-256 bridge substitutes | 32 total tests passed, including the unit test; 1 full-shell integration test deselected |
| Native loopback HTTP / browser WebCrypto suite | BLOCKED by environment; not PASS |
| Full repository shared-shell integration test | Not run locally; requires the complete repository |
| Ruff | Not run locally; executable not installed |
| Full existing suite / three OS / clean wheel | Not run locally; existing PR CI must execute |
| Fresh real provider and independent buyer operation | Not performed |

The 32-test diagnostic used a local, uncommitted pytest plugin. It substituted
transport and digest interfaces while executing the actual component JavaScript,
DOM, user clicks, file selection, search, paging, cancellation and error handling
in Chromium. This does NOT prove native HTTP/auth behavior or browser WebCrypto.
The committed tests retain real loopback HTTP and native browser SHA-256; no mock
plugin, admin-policy bypass, automatic skip, or weakened assertion is committed.

Tests cover tool/model reference cards, literal malicious HTML display, unsafe
paths, empty/null/false/zero content, HTTP failure states, tampering, binary input,
unknown-length oversized response, preflight size limit, long-text tail search,
offline folder selection, cancellation, missing crypto, run changes and folder
isolation. The full-shell test asserts installation in both Live and Static HTML.

## Remaining work / integration risks

- W02 is NOT complete: no archive reference-closure proof, automatic self-contained
  bundle embedding, greater-than-8-MiB browsing, or binary preview.
- W03/W05/W06/W07 and separate execution/task/observability status are not delivered.
  Agent-history pagination, control-token classification, artifact version lineage,
  story layout, metrics and capture gap diagnosis remain pending.
- The component observes only the existing inspector's dedicated metadata
  containers. If that DOM contract changes, update its integration tests; do not
  broaden it to arbitrary text or infer missing references from filenames.
- Full-shell assembly, all provider fixtures, Windows folder selection, package
  inclusion and native authentication must pass the existing CI. Keep the PR draft.
- No version bump, merge, force push, tag, release or issue closure is authorized
  or performed by this slice. The buyer plan's work-package checkboxes remain open.
