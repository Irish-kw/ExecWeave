# Content-reader Escape isolation

Baseline: `d20182bf6bb6850f4f94281b424c639845c89c9a`, PR #110.
This is one interaction repair, not a release-acceptance report.

## Reproduced user problem

Opening a captured body from a selected message group and pressing Escape
closed the body dialog but also cleared the canvas selection underneath it.
The same problem occurred when opening a body from Explore run. In the direct
message path, clearing the selection removed the source navigation and disrupted
the user's return to the expanded handoff record.

The content dialog handled the browser's `cancel` event but did not stop its
Escape `keydown` from reaching the existing document-level clear-selection
handler. The Close button did not have this problem. I reproduced both entry
paths on the unchanged baseline before editing the implementation.

## Repair and impact

The shared content dialog now stops propagation of Escape keydown within its
own boundary. It does **not** prevent the browser's default cancellation: the
existing cancel handler still aborts pending reading, clears displayed content
and closes the dialog. Native focus restoration returns to the invoking body
button. A containing Explore run dialog remains open; another Escape closes
that parent, and Escape on the canvas still clears the selection normally.

Only three production lines change in `viewer_content_browser.py`. There are
no changes to reference validation, authentication, file access, folder scope,
hashing, polling, graph selection policy, native key handling outside this
modal, capture, dependencies, workflow configuration or package version.
Historical tests are unchanged. The other two files are the new regression
module and this record. Reverting this batch restores only the previous modal
key behavior; original evidence and all body-reading capabilities are unchanged.

## Validation

The exact baseline was reconstructed from the mounted 6a144b3 Actions bundle
and the validated 5523110/d20182b patches. Its complete tree matched
`0e30b2514528b099625d1dc2cbbf7ff5f898b753` before edits. Local runtime:
Linux, Python 3.13.5, system Chromium/Playwright, Node 22.16.0.

- Identical seven new cases on the unchanged baseline: **5 failed, 2 passed**.
  The five failures lose the selected node after Escape; both Close-button
  controls pass.
- New modal cases plus existing folder-scope component cases:
  **16 passed, 3 native relocated-folder cases deselected**.
- Unchanged message-handoff navigation, two existing content-reader assembly
  checks and the existing complete-shell JavaScript syntax check:
  **19 passed**, with no skipped or deselected cases in this command.
- Ruff, Python compilation and diff whitespace checks: **PASS**.

The two final runs contain **35 distinct passing checks** (7 new, 28 existing).
The baseline comparison and repeated cases are not added to that count. Exact
commands, JUnit and failed/passing logs accompany the validation archive.
Ruff was installed from an existing mounted wheel without changing repository
dependencies. These runs import the local `src` tree through pytest; they are
not installed-package acceptance.

These are actual Chromium keyboard/dialog interactions over synthetic SDK
messages and the shipped Dashboard, loaded with `set_content`. No key handler,
fetch, timer, File API or digest is replaced. Tests assert selection, expanded
record retention, return focus, keyboard reopening, parent-modal ordering,
retry behavior and raw-graph equality. They stop at the real folder-required
boundary; they do not claim native Offline plaintext/hash verification, original
R2/R3 replay, fresh-provider recording, or full cross-platform acceptance.

## Independent verification and remaining scope

ChatGPT2GrokBot #86 retains its frozen d20182b target for native Offline reading.
This repair does not retarget that report or convert its Started acknowledgement
into a result. A separately identified follow-up should exercise Escape and
Close after both verified and failed body reads, from the direct message panel
and Explore run, without changing source or tests.

Current-head CI and the original buyer journeys remain required. No main-branch
change, merge, version bump, tag or publication is part of this repair.
