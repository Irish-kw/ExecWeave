# Conversation compatibility, runtime navigation, and tab-local reading state

Baseline: `48eea34b42a42c6c282c9cb505f86f24ebebd81f`, PR #110. This is an
implementation record, not a declaration that the 0.8.34 plan is complete.

## Compatibility repair

I reproduced the unchanged historical test
`test_the_live_server_serves_the_same_index_the_file_would_carry` against the
baseline. The default conversation builder included `investigation`, while the
ordinary authenticated Live route intentionally omitted it. The latest baseline
Ubuntu/Python 3.12 report was **1 failed, 2,219 passed, 5 skipped**; the two older
synchronization failures were not the latest head's result.

The default builder now returns the historical lightweight projection. Both
Live's explicit `investigation=1` request and each offline exporter request the
extension explicitly. Extended and ordinary modes have identical conversation
entries. Ordinary polling never scans event streams. The original failed test
is unchanged; the recently introduced investigation-publication test now passes
`include_investigation=True`, preserving its assertions. New tests check the
no-scan default, exact projection equality, and all three static export entry
points. No test is deleted or made less strict to conceal the regression.

## Runtime evidence navigation

I added **Runtime evidence** to the shared Dashboard and **Runtime evidence for
selection** to the selected-node inspector. Users can search the published
process, file, directory, network, provider, and runtime inventory without
finding each node in the canvas. A selected agent, invocation, or tool can open
its recorded neighborhood directly; a separate action returns to all indexed
runtime evidence, including disconnected records.

This is bounded navigation over already-published graph relationships, not an
ownership solver. Exact graph IDs are used. A shared tool/model/file/network
resource is not traversed as a bridge between agents. Process parents are not
used to bridge sibling subtrees. A selected shared tool can still expose its
separately recorded call paths. Unsupported or absent bridges remain absent;
this does not claim all providers have exact invocation-to-process attribution.

Inferred/correlated edges remain labeled and never become observed causal
edges. Conflicting node or edge IDs are withheld rather than resolved by the
last record. Unresolved endpoints and partial inventories are disclosed. A
missing selected ID is not replaced with a same-named participant. Explicit
projected agent members are restricted to agent identities, not arbitrary
runtime nodes. Opening an exact node absent from the current display reports
that condition rather than choosing another node.

The reader uses no new endpoint, event scan, body fetch, filesystem read, or
outbound navigation. It does not change raw graph data, geometry, camera scope,
recorder behavior, resource aggregation, or evidence classifications. Remote
tool internals and unobserved file bytes are not reconstructed.

Limits: 100,000 graph records, 1,000 expansion containers, 10,000 runtime rows,
four relationship hops, 100 incident-edge previews per row, and 25 DOM records
per page. Labels/metadata previews are limited to 2,048 characters. Open records
are retained in bounded in-memory state; the active snapshot stays pinned until
explicit refresh, and a changed execution scope closes and clears it. These are
safety bounds, not completion of the planned large-run p95 benchmark.

## Reading state across controller restarts and reloads

The history reader can retain page, category, and up to 64 expanded-record keys
per view in **sessionStorage**, scoped by execution IDs, source path, exact
agent ID, and the selected records' native identities. A display name or
filename alone cannot enable persistence. Changing run, agent, source path, or
native execution identity prevents restoration into the new scope.

I do not store message text, search terms, graph attributes, or full transcripts.
A search-specific page resets to the first page because its query is not stored.
Saved state is versioned and validated, capped at 32 views and 128 KiB of JSON.
Malformed, oversized, unavailable, or quota-exhausted browser storage does not
break the reader. Restoration changes presentation only, never evidence content
or completeness. It is tab-local, not a cross-device or long-term history store.

The component tests use a storage double and restart the reader controller.
They are not described as real page reloads. A separate native HTTP test uses
real sessionStorage, the complete shipped Dashboard, and `page.reload()` without
route interception or storage mocking. Browser policy in the local environment
returns `ERR_BLOCKED_BY_ADMINISTRATOR` for localhost navigation, so that test
must be validated by current-head CI. File-origin persistence is browser-policy
dependent and may be unavailable; reading continues without it.

## Validation and provenance

I restored the complete baseline source and historical tests from Actions
artifact `10560811047` (`rc-source-provenance`), SHA-256
`df680196dca3d0895feedcc9b1df9ece804ce9fa9e91a049c9ef8e23303637ca`.
The baseline tree is `b8c3402b6682ca69f772e5a284659079c057955a`.
Local runtime: Linux, Python 3.13.5, Chromium, Node 22.16.0.

Focused results before the final clean-source run:

- Conversation opt-in, existing failure, investigation, and delivery: 107 passed.
- Runtime navigation: 16 passed, including 10,005 synthetic process nodes,
  bounded output, shared-resource separation, hostile labels, and raw equality.
- History and persistence components: 56 passed, one native HTTP case excluded.
- Ruff and assembled JavaScript syntax: passed.

An initial non-browser run failed 14 cases because CLI entry points/package
metadata were not installed and package-provenance checks correctly rejected
uncommitted source. An initial browser invocation used a missing bundled browser
instead of the installed Chromium. These failed setup attempts are not counted
as product passes. I installed an exact-source wheel and fixed the browser
selection before the final clean-source runs. Final results and the corresponding
remote source tree are recorded in the PR; overlapping counts are not summed.

The new browser fixtures are synthetic contracts. Existing recorder/SDK tests
exercise real local code, not new paid-model calls or fresh CAMEL/AutoGen/MetaGPT
or Ollama deployments. Current-head three-OS/Python 3.10 and 3.12 workflows,
installed-package checks, native offline journeys, and independent user testing
remain separate requirements.

## Impact, rollback, and remaining work

The compatibility changes are in the conversation core and static exporter.
The runtime reader is one added module injected by the shared Dashboard shell.
Reading-state persistence is confined to the existing history reader. Test
changes are limited to the explicit extension argument and added regressions.
No dependency, workflow, version metadata, original capture, main branch, tag,
or publication is changed.

The runtime module and its shell injection can be reverted independently.
History persistence can be reverted independently without losing captured data.
Retain the lightweight conversation default and explicit export extension as a
single compatibility repair; reverting only one side recreates the mismatch.

This advances the runtime-navigation portion of W04/W06 and the view-state part
of W03. It does not complete workflow-first canvas layout, independent task
validation, all native per-invocation/source contracts, capture policy for
historical artifacts, redacted sharing exports, large-run product acceptance,
or fresh-provider and independent-user acceptance. Those gates stay open.
