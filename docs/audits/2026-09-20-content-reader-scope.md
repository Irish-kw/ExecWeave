# Content-folder scope and relocated Offline verification

Baseline: `5523110e73ad91587fdc27b083002fb5f620d98b` (PR #110).

## Finding and repair

The #85 report confirms the original AutoGen message-group navigation works,
but stops at `folder_required`; it does not establish successful native body
reading. While checking that boundary, I found a separate scope defect: the
content reader selected its identity with a fallback expression. When a session
ID existed, changed run IDs and source paths were ignored. A selected local
folder could consequently remain available to another execution scope. Retry
also lacked a fresh scope check, and lifecycle updates without inspector DOM
changes did not revoke the old folder.

The reader now keys that capability by all three fields: run ID, session ID and
source path. Opening, retrying and choosing a folder check this complete scope.
Dashboard payload/finish callbacks revoke stale state without waiting for an
inspector mutation. Leaving the page clears the folder map and cancels pending
work. Closing/reopening within the same scope retains the chosen folder; an
ordinary event-count update does not cause unnecessary re-selection.

This changes one production file. It does not change content bytes, reference
validation, SHA-256 verification, the 8 MiB limit, the authenticated endpoint,
recorders, layout, historical tests, dependencies, workflow policy or version.
The existing callback chain and arguments remain intact. No additional polling,
network request, filesystem scan or browser-storage persistence is introduced.
Reverting the content-reader change and new tests is independent of message and
model-output navigation; it does not alter captured evidence.

## Executed checks

The restored baseline was built from the mounted `6a144b3` source bundle plus
the validated `5523110` patch. Its complete Git tree was verified as
`ff3fe3942da654339e6de477b4bd463505db2899` before editing.

Local runtime: Linux, Python 3.13.5, installed Chromium/Playwright. Existing
watchdog and Ruff wheels were installed from a mounted CI artifact; repository
dependencies were not changed.

- The final nine component cases on unchanged baseline: **6 failed, 3 passed**.
- The identical nine cases on repaired source: **9 passed**.
- Unchanged message-handoff navigation module: **16 passed**.
- Unchanged refresh-outcome cases and three existing injection/assembly checks:
  **18 passed**.
- These completed groups cover **43 distinct checks**; repeated runs are not
  counted again. One combined command exceeded the tool deadline without a final
  report; the separate complete results above replace no failed assertion.

The scope cases use the real directory input and native File reading with
intentionally size-mismatched bytes. Reaching `size_mismatch` demonstrates access
to the selected file; it is not a successful hash-verification claim. No file
API, digest, fetch or timer is replaced. An initial new hook test incorrectly
assumed the pre-existing wrapper preserved a global `this` receiver; that
unrelated expectation was removed before the final baseline comparison. No
historical test was changed.

## Native Offline cases: attempted, not passed locally

Three additional cases generate the full Dashboard and investigation index from
synthetic SDK captures, copy the run folder, delete the original copy and open
the relocated `viewer.html` using its actual file URL. They select the message
route, expand a record and choose the folder using the real directory input.
The required states are `verified`, `hash_mismatch` for same-size tampering, and
`missing_blob` for a deleted file. They compare displayed text against original
bytes, check no HTTP requests occur and verify files remain unchanged.

All three local attempts stopped at `Page.goto` with
`ERR_BLOCKED_BY_ADMINISTRATOR`. They therefore do **not** establish native
Offline completion, original R2 replay or fresh-provider acceptance. They remain
enabled in the ordinary browser suite with no skips or policy workarounds.
Independent execution is requested with native file input and SHA-256, not a
folder-required screenshot or a substituted digest. The #85 verdict remains
PARTIAL until that actual journey is demonstrated.
