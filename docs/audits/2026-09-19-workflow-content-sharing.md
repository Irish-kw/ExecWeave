# Workflow view, content-health drill-down, and structural sharing

Baseline: `abd2a5cbc7d9e8cb15cc73208316866d10a291b3`, PR #110.
This record describes an implementation batch, not release acceptance.

## Baseline and recovered progress

I verified the remote branch rather than relying on the previous PR description
or screenshots. The branch included the runtime-response-boundary fix, but did
not contain the workflow, content-health, or structural-sharing modules. I
restored the full source and historical tests from Actions artifact 10576959073,
SHA-256 `976fa75c222c854887679a1e23b86ca2fd78f5fe346382740e6a501b5319776b`.
Its tree matches `6aa135bf37a028a14ebad9c00e5122572671f3fd`.

At this baseline four specialty workflows passed, the main CI run was cancelled,
and Viewer Agent Isolation failed only on Windows. Linux and macOS completed
their viewer, offline, cleanup, and native-OS checks. These are baseline results,
not acceptance of the new source.

The Windows JUnit artifact 10578280438 reports two errors (setup and teardown of
one case), zero assertion failures, across 430 tests. Pytest included the entire
131,073-character oversized-storage payload in its generated test ID. Windows
rejected `PYTEST_CURRENT_TEST` because the environment value exceeded 32,767
characters. I assigned short explicit case IDs. The oversized input, test body,
and assertions are unchanged; the case is neither skipped nor reduced.

## Workflow-first navigation

Multi-agent runs initially show a workflow overview. Single-agent and runtime-only
runs retain the full existing view. The Graph view selector reversibly switches
between automatic, workflow, and all execution evidence.

The workflow view filters the existing display projection, not the raw graph.
Agents, models, tools, tasks, unresolved subtasks, recorded message nodes, explicit
snapshot sources, folded summaries, failure records, and selected nodes/edge
endpoints remain reachable. Infrastructure hidden from the canvas is counted and
can be revealed through All execution evidence or exact-ID runtime navigation.
No hidden path is contracted into a new relationship. Ambiguous display identity
falls back to the full view rather than resolving an identity by name.

I retained the existing geometry solver and full-view routing policy. In the
filtered workflow view, bundle rails use actual visible row order instead of
stale full-graph preferred rows. A metadata-only delta that retains positions
must also retain the corresponding bundle rail. The existing quality gate may
still accept a strictly better arrangement; it is not forced to retain a worse
crossing count. Manual camera ownership is preserved. An explicit view change
settles an already-active Fit camera immediately, so a pending fit cannot appear
to originate from the reader's next Arrange action.

The first complete-page screenshot exposed a grid integration defect: inserting
a third graph-panel child gave the toolbar the stretch row and squeezed the
canvas. The graph panel now has explicit bar, toolbar, and remaining-canvas rows.
Regression checks measure the actual canvas allocation at 1600x1000, 1024x768,
and 390x844. This is not a claim that the entire Dashboard is mobile-optimized.

Large-graph protection remains authoritative: switching views or preparing a
share cannot redraw/export the previous graph as if it were the compact current
payload. Existing file visibility and folding limits continue to apply.

## Inspectable content-health categories

Content health uses the existing versioned investigation index. Its denominator
is `indexed-record-phase-v1`: an indexed record paired with a particular phase,
not a unique real-world invocation, total provider activity, or readable-byte
recall. Model requests/responses, tool arguments/results, sent/received messages,
and explicit historical snapshots are listed separately.

The page distinguishes registered-but-unread references, source-incomplete
content, explicitly declared metadata-only capture, absent phases, unknown causes,
invalid references, and references outside the graph inventory. Registration
never certifies successful reading, hash verification, or source completeness.
Missing indexes and exhausted limits are disclosed as partial/unavailable, not
as zero activity. Duplicate index identities are withheld rather than resolved by
the last record. Counts across categories must not be summed as unique calls.

A row opens its exact current investigation record. If that record is missing
or ambiguous, the page reports the condition instead of opening a similarly
named record. New data does not replace the open health snapshot until refresh.
Refresh reuses the existing authenticated investigation request; there is no
new endpoint, periodic poll, arbitrary file read, or body fetch.

I added generation guards to health and investigation refresh actions. Cancel,
reopen, and execution-scope changes invalidate old UI completions. Rejected
requests retain the currently readable snapshot. Modal Escape does not clear the
underlying graph selection.

## Structural sharing is a separate derivative, not a redacted raw archive

Share structure prepares a strict allowlisted projection. Original node/edge IDs
are replaced with local pseudonyms. Only fixed node types, fixed relationship
categories, and conservative evidence classifications survive. Names, paths,
hosts, timestamps, arbitrary attributes, content, original hashes, and execution
identifiers do not enter either exported document.

The preview explicitly warns that topology and counts may remain sensitive.
This is not a guarantee of anonymity, a full audit archive, or a content-aware
redaction feature. Unknown/malformed causality cannot become observed causality;
correlated and presentation-only relationships remain distinct. Duplicate IDs and
unresolved edges are withheld and counted. Limits reject oversized exports rather
than silently claiming full coverage.

The reader must prepare, review, confirm, and then save the derived JSON, static
HTML, and checksum file. The HTML has no scripts or external resources and uses a
restrictive content policy. Native SHA-256 is required for the new bytes; missing
browser crypto disables export. Cancelling a pending digest invalidates its
completion and allows a new preparation. Original capture bytes and archive
hashes are never rewritten. Nothing is uploaded by this feature.

## Test changes and evidence boundaries

Existing Windows storage input/assertions are retained, with short test IDs.
Existing full-graph geometry tests now select All execution evidence through the
shipped control before measuring. Their node counts, overlap, intersection,
manual-drag, deterministic-layout, and camera assertions are unchanged. A separate
new matrix exercises automatic workflow membership and retained geometry. This
prevents a small workflow view from being mislabeled as a dense 109-node test.
The untouched Antigravity ambiguity test also caught the missing subtask category;
the production filter was corrected instead of changing that test.

The initial expanded geometry run found five failures. Three directly attempted
to inspect hidden runtime/file records, one exposed bundle-rail drift, and one
caught the unresolved-subtask omission. The subsequent full-view setup exposed a
pending Fit animation; that production timing issue was fixed, not hidden with a
weaker camera assertion. Intermediate reports remain in the validation evidence.

Local component runs use the shipped Dashboard and real Chromium. Their fixtures
are synthetic SDK/graph records, not new paid-model or upstream framework runs.
Deferred request/digest doubles are restricted to explicitly named UI-race tests
and do not validate transport or cryptography.

Two separate native tests use actual localhost navigation, real sessionStorage
reload, and native SHA-256/downloads. Both local attempts were blocked with
`ERR_BLOCKED_BY_ADMINISTRATOR` before the journey began. They remain enabled in
the normal CI suite; they are not represented as local passes and no browser
policy was bypassed. The structural-download test recomputes both new file hashes
in Python and verifies the original graph remains unchanged.

Final clean-source test counts, package/source equality, and exact remote head
are reported in the PR and accompanying validation files. Overlapping focused,
geometry, and full-suite counts are not added as unique tests.

## Change impact and rollback

- Dashboard shell: three feature injections, plus filtered-view rail ordering;
  original static/live startup and full-view routing remain intact.
- Workflow module: display membership, explicit view controls, camera settling,
  protective-mode guard, and graph-panel row allocation.
- Investigation/runtime readers: exact record drill-down, cancellation guards,
  and exact hidden-node reveal; no new identity or capture authority.
- Content-health module: bounded index interpretation and metadata counts only.
- Structural-sharing module: new derivative files only; never a raw overwrite.
- Tests: short Windows case IDs, explicit full-view geometry setup, and new
  component/native regression cases. No existing assertions are deleted.

Workflow and its optional rail helper can be reverted together. Health and its
record-navigation action can be removed independently. Structural sharing can
be removed independently without losing original data. Remove each module's
shell injection with the module itself. Keep the Windows test-ID portability fix.
No recorder, dependency, workflow, version metadata, main branch, tag, or package
publication is changed by this batch.

## Gates still open

This advances W06's default view, W07's itemized metadata health, and a conservative
structure-only part of W08 sharing. It does not establish complete provider
capture, independent task-validation evidence, every historical artifact capture
policy, content-aware redacted archives, all large-run performance targets, fresh
provider recordings, or independent human user acceptance. Current-head CI and
native offline journeys remain requirements. The implementation PR stays draft.
