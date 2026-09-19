# Explicit refresh outcomes in investigation readers

Baseline: `c80df1565edbc1b928dcf0881680ef9d697ec959`, PR #110.

## Failure and repair

The shared conversation reader resolves to `false` on HTTP, scope, terminal-state
or other unsuccessful refreshes. Content health and Explore run caught rejected
promises but treated a resolved `false` as success. The first on-demand index
request could also say "completed" after such a failure.

I now require the shared reader's explicit `true` before replacing the open
snapshot. `false`, an absent method, undefined/non-boolean results and exceptions
produce a failure notice while retaining the currently readable content. The
initial request also distinguishes success from failure. Static index refresh
continues to use local data without a transport requirement. Existing generation
and execution-scope guards still prevent stale completion after cancellation.

This is a UI outcome repair, not a new definition of index validity. It does not
change the shared reader's return contract, final-sync policy, index validation,
authentication, polling, raw data, layout or capture. Success here means the
existing refresh contract completed, not that every referenced body was read or
that the source supplied a complete history.

## Verification

The exact baseline tree was reconstructed from the mounted 875542d source bundle
and the 75afa9f/c80df15 patches, and matched
`43b9f226d03a339149b6d2cdfdea44e55347c5cd` before edits.

- Identical 15 new cases on the baseline: **11 failed, 4 passed**.
- Same 15 cases after repair: **15 passed**.
- Those cases plus six unchanged pinning, cancellation, foreign-index and
  assembled-JavaScript regressions: **21 passed, zero skipped**.
- Ruff and `git diff --check`: passed.

These counts overlap. The browser cases execute the shipped Dashboard in system
Chromium on Linux/Python 3.13.5, using synthetic SDK records. Controlled refresh
outcomes and a substituted 401 fetch response are component tests, not native
HTTP or provider acceptance. The 401 cases retain the actual shared refresh
implementation, rather than replacing its boolean result.

Two broader test attempts were interrupted by the local command timeout before
a final report. Their incomplete output is not a passing suite. The completed
21-case run above is the validation scope of this small batch; current-head CI,
native provider journeys and the remaining release gates are still required.

## Impact and rollback

Two production modules change: `viewer_content_health.py` and
`viewer_investigation.py`. One new 15-case test module and this record are added.
No historical test, workflow, dependency, package version or main branch changes.
The two UI changes can be reverted together without modifying recorded evidence.
The return-value guard must remain aligned with the shared reader's boolean API.

Independent verification is requested in ChatGPT2GrokBot for the resulting exact
commit. It is candidate validation, not a claim that all eight 0.8.34 work
packages are complete or authorization to merge, release or alter the source.
