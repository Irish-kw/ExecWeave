# Captured model output: explicit refresh and pinned reading

Baseline: `fde47e54bd478270c63322326e787ec94596ab35`, PR #110.

## Reproduction and repair

The previous slice rendered per-reference model previews, but the existing
conversation signature only compared merged conversation messages. Updating
`model_response_preview` alone did not update the selected role or tell the
reader that new output existed. Conversely, an unrelated conversation change
could rebuild the inspector and replace the preview without a reading action.

I added a scoped, in-memory snapshot to the captured-output reader. When accepted
index entries change, the section reports that newer output is available and
keeps the displayed records pinned. **Refresh captured model output** loads the
latest accepted index into this section, without reselecting the agent or
replacing its reported final response. This button is a local view refresh, not
a new HTTP request or a retry of a failed transport operation.

An output section can become discoverable when the selected agent previously
had no model preview. Explicit refresh preserves expanded records and the number
of loaded rows, including older pages. New latest records do not close the record
already being read. Identical indexes and sibling-only changes do not create a
false update notice. Withdrawn previews remain explicitly labeled as an earlier
snapshot until refresh, then disappear. A changed run scope clears the old view
rather than retaining another run's output. Selecting another agent resets the
snapshot; returning to a role opens its current accepted index.

## Impact and boundaries

Three files change: the existing model-output module, a new eleven-case test
module, and this record. The shared setEntries callsite is extended by a checked
injection seam; the historical agent-panel source and tests remain unchanged.
No recorder, normalizer, model ownership rule, layout, final-sync policy, endpoint,
authentication, original body/hash, dependency, workflow or version is changed.

Only the active agent's pinned preview and its comparison signature are retained
in memory. They are not written to browser storage and are released on pagehide.
Fold booleans continue to use the existing state mechanism. The snapshot is an
additional in-memory copy of already-published previews; large-run memory and
latency are not benchmarked here. Existing preview limits and exact-source gates
remain unchanged. Showing a preview still does not verify captured bytes or
establish task success.

Rollback: revert the model-output module change and remove the new regression
module; no captured data is lost. This restores the prior stale/automatic-replace
behavior, not a different ownership or recording contract.

## Executed validation

Local runtime: Linux, Python 3.13.5, system Chromium and Playwright. The baseline
was reconstructed from the mounted source bundle and four validated patches;
its Git tree matched `c1005d44b5f918bae6c5fc1ca1bade432e02b54b` before editing.

The same eleven new tests were run against the unchanged baseline in two disjoint
batches: **4 failed / 1 passed** and **5 failed / 1 passed**. Repaired source:
**11 passed**, with no skipped/deselected cases. The previous slice's unchanged
thirteen cases also passed: **13 passed**, separately. Ruff, diff whitespace,
Python compilation and assembled Live/static JavaScript checks passed.

Several earlier combined commands exceeded the execution tool's command deadline
before emitting a final report; those attempts are not passing results. The final
smaller batches above all emitted complete JUnit reports. Network dependency
installation failed; the lint/watchdog wheels already present in a mounted CI
artifact were installed offline without changing repository dependencies.

Tests use synthetic SDK-generated records and the shipped renderer in Chromium.
They call the real shared setEntries path, without substituting fetch, and cover
MetaGPT, AutoGen and CAMEL preview updates. They do not prove native HTTP capture,
original R3 replay, full Offline reading, all-provider coverage or buyer acceptance.
The original Grok #83 buyer failure and fde47e5 replay request are not relabeled
as passing. A separate pinned follow-up is required for this new candidate.
