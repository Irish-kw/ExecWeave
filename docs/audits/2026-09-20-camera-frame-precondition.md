# Wait for an observed camera frame before testing Arrange

Baseline: `2b12869622e4035113852c30732c46e71568b82b`.
Baseline tree: `1f4a88202fa0b9835354f025415f0a690a59e1e9`.
Scope: test synchronization and this record only; no product change.

## Actual CI evidence

I audited the following artifacts from ordinary CI run `35515856487`:

| Platform | Artifact | SHA-256 | JUnit result |
| --- | --- | --- | --- |
| Windows / Python 3.12 | 10607530263 | `1ec6cf08754de119fd89e59e225463f3a6e00c769213aacb23e99c63252ba77d` | 2,485 passed, 2 skipped, no failures/errors |
| macOS / Python 3.12 | 10607161444 | `1b71257d16e83067577338f3d5c202d449fa0ee9be7da26162b727743ef53eb1` | 2,474 passed, 6 skipped, 1 failure, no errors |

Both artifacts have identical before/after tracked-source manifests: 767 files,
clean tracked status, merge `71223fd1012c91290393653b57c8ac7ef3c8266a`, and
exactly the baseline tree. Both explicitly contain a passing cross-chunk byte
case and all 18 diagnostic-runner/sampler cases. These are completed ordinary
suite executions, not collection-only checks or split local runs. They establish
those checks on these two environments, not universal absence of timing faults.
Windows/Python 3.10 was still running when this evidence was retrieved.

The sole macOS failure was
`test_arrange_preserves_camera_and_next_update_can_resume[animating-follow]`.
It failed its prerequisite `initial != before`: both transforms were
`translate(36 -12) scale(0.48)` after the fixed 60 ms sleep. The test had not
established the animating condition it intended to test. This does not show that
Arrange changed the camera, nor explain the older Windows cancellations.

## Narrow change

The animating branches now register a native MutationObserver before starting
the real camera action and await a changed viewport transform. The wait has an
explicit three-second failure deadline; no observed motion means rejection,
never success. This replaces the fixed 60 ms sleep with an event-based
prerequisite, rather than claiming the first frame always arrives within 60 ms.

All original assertions, mode/queued combinations, graph fixture, and 550 ms
post-Arrange/resumption observation windows remain unchanged. The original
29-case geometry module is byte-identical. No camera implementation, animation
speed, browser clock, timer API, scheduler, or renderer is replaced. There is no
retry, skip, threshold relaxation, or workflow timeout change.

Two added tests check the observer itself: an unchanged transform plus an
unrelated attribute mutation must time out; a deliberately delayed real Follow
camera action must produce an actual changed transform before resolving. The
latter uses the shipped renderer and native timer/animation APIs, not a mocked
frame. The other browser cases use synthetic graphs and `set_content`; they are
not original-capture replay or new provider runs.

This choice follows the browser's repaint-based scheduling contract and
Playwright's guidance to wait for observable signals rather than fixed sleeps:

- https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame
- https://playwright.dev/python/docs/api/class-page#page-wait-for-timeout

## Completed local validation

- Updated camera transaction module: **9 passed**, one uninterrupted command,
  exit 0; seven original cases and two additional prerequisite checks.
- Unchanged historical geometry module: **29 passed**, one uninterrupted command,
  exit 0; no skip or deselection.
- These disjoint commands cover **38 unique passing tests**. The JUnit files are
  retained separately; this is not a full product-suite result.
- Python AST comparisons confirm every assertion in each original camera-test
  function is unchanged. The helper changes only the animating prerequisite.
- Ruff and diff-whitespace checks passed. Product source, original geometry
  tests, dependencies, workflows, package version and original data are unchanged.

Local runtime: Linux, Python 3.13.5, pytest 9.0.2, system Chromium/Playwright.
The failing macOS baseline is established by the downloaded CI artifact; I did
not reproduce that precise scheduling delay on a local macOS host. New-head
native CI is still required. The local source was reconstructed from the mounted
source bundle and validated changes and matched the baseline tree before edits.

## Impact, rollback and outstanding gates

Only `tests/test_arrange_camera_transaction.py` and this document change. Revert
this commit to restore the prior timing prerequisite; no product migration is
needed. The change does not introduce a user-facing feature or close any of the
remaining W01-W08 product requirements.

The passing Windows/Python 3.12 suite and its byte/diagnostic cases are a concrete
new acceptance result for 2b12869. Windows/Python 3.10, current-head full CI,
remaining original/provider journeys and the broader release gates remain
separate. No merge, release or readiness claim is made.
