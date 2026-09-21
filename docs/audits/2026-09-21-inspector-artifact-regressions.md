# Selected evidence priority and portable artifact reads

Baseline: PR #110, `688d1c29780bcf57ed153a53b407fd332b379e46`, tree
`c9b0c61734f896a66807c1144d0e6152716a27ce`.
This batch repairs two regressions; it adds no task-verification authority.

## Failures actually inspected

I verified the downloaded ZIP hashes and parsed the JUnit records, rather than
using the failed workflow badge as a diagnosis:

| Artifact | ID | Outcome |
| --- | ---: | --- |
| Ordinary Linux / Python 3.12 | 10609967632 | 2,651 passed, 5 skipped, 1 failed |
| Ordinary Windows / Python 3.12 | 10610194527 | 2,653 passed, 2 skipped, 8 failed |
| Windows viewer | 10610374249 | 721 passed, 11 failed, no skips |

ZIP SHA-256 values, respectively:
`8e0eb261f0c08b9221d9796313ddc33a017197f7e59f7f720f15a0c3e15134fe`,
`3589140d6018f02f26606b75ca072c6c9db16c4b34467c04eebf081ae50171f2`,
`38d7461a191a90926131449ac8dc5a81ed63996cd76347dfe820e9f0ff1802f5`.
These overlapping runs are not additive unique failures or complete inspection
of every platform artifact.

The unchanged delivery test found the selected content below its first-screen
boundary. Local baseline reproduction placed `#details` at y=924.61 and failed
its existing y<750 assertion. Other Windows failures stopped at the artifact
reader's path-stat versus descriptor-stat comparison, before receipt generation.
The logs do not record the differing field; no particular native timestamp value
is claimed to have been measured by that CI run.

## 1. Selected content must precede navigation and full assessment

With no displayed evidence, the role guide remains open at the start of the
inspector. After selecting a record, the existing guide and full assessment move
below the selected content. The separate delivery summary stays ahead of it, so
an export/synchronization failure is not buried with the full assessment.

These are DOM moves of existing elements, not regenerated controls or automatic
collapse. Search text, role buttons, disclosure state, captured text and manual
camera remain intact. Same-record refresh does not repeatedly reorder elements.
The existing core retains readable details when graph highlighting clears; that
behavior is unchanged. Empty/protected states restore the discovery ordering.
No graph identity, layout engine, record classification or camera API changes.

An intermediate fix moved only the guide. It passed the historical starting-y
check but the inspected screenshot still left the actual answer below the pane.
The final regression therefore also requires the short fixture's actual answer
body to fit inside the inspector viewport at three desktop/narrow widths. The
final synthetic screenshot shows the selected body starting at y=194.69. This is
not an original-recording screenshot or a mobile/full-product usability verdict.

## 2. Compare like-for-like artifact metadata

Artifact reading now reuses the archive reader's existing metadata-only
`_path_descriptor_stat` helper. All identity/size/time comparisons use open-file
snapshots: initial selection, opened data handle, after reading, and reopened
selected path. The data handle remains open during final path verification.
Device, inode, size, mtime and ctime still compare exactly. No timestamp rounding,
ignored fields or platform-specific acceptance bypass is introduced.

Path metadata still rejects nonregular files and leaf symlinks/reparse points.
The read is binary and bounded. Metadata-only handles are closed on errors;
changed metadata, denied reopen or path replacement cannot produce a receipt.
The existing archive helper itself is unchanged. Sequential checks remain an
observed stability check, not an atomic directory snapshot or filesystem sandbox.
Actual native Windows execution must validate the repair on the new head; Linux
metadata doubles alone do not establish Windows acceptance.

## Completed local checks and limits

- Artifact portability, existing artifact core and report core: **95 passed**.
- New inspector priority, existing role guide, delivery and report/artifact UI:
  **86 passed**, eight native cases excluded from this component command.
- Existing archive metadata portability: **9 passed**.

Together these completed commands cover **190 distinct cases**, including 29 new
regressions. Prior iterations and overlapping focused commands are not added.
All existing tests and assertions are unchanged. Metadata fault injection tests
model each one-unit field mismatch and failure boundary; separate tests use real
file replacement, repeated modification and binary/empty bytes.

All eight native report/artifact cases were attempted separately. Each was
blocked at file-origin navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`, before the
journey. They remain enabled in normal CI; these failures are not local passes.
Existing browser component digest bridges remain explicitly component-only.

Several early combined commands exhausted the tool's short command budget before
final JUnit. The final 86-case command ran to completion under a separate bounded
supervisor without changing pytest assertions or per-test timeouts. Initial new
test harness mistakes (label capitalization and reinserting the entire shell in
the same document) were corrected; incomplete/intermediate logs are retained.

Ruff and assembled Live/static JavaScript checks passed. An offline-built wheel
was installed to a separate directory; all 212 Python files matched the candidate
and imports resolved outside source. Cached wheels supplied dependencies; this
was not a fresh-OS install. A first setup attempt lacked a cached build dependency
and failed; completing the local wheelhouse succeeded without repository changes.

## Impact and rollback

Five files change: two production files, two new test modules and this record.
Existing tests, archive helper, recorder, routes, provider contracts, workflows,
dependencies, version and raw captures are untouched. Revert the guide change
independently to restore inspector order, or the artifact change independently
to restore the former read policy. Neither requires data migration.

Grok #94's passing Linux native checks retain their fixed target and scope; they
did not establish native Windows behavior. The new-head verification must check
both the original delivery case and the Windows artifact failures. No broader
W01 completion, trusted test execution, artifact attestation, release readiness,
merge or publication is claimed by this repair.
