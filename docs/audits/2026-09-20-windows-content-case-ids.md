# Windows byte-integrity test identity repair

Parent: `02f3bd3b5f177d535422791d4ad049f3cfa6d7ae`.
This is a test-portability repair, not a product change or full Windows acceptance.

## Native evidence

The first Windows Suite Diagnosis completed its pytest session instead of
reaching the 1,500-second diagnostic deadline. Run `35511908734`, artifact
`10605893907` (`windows-suite-diagnostic-py312`), ZIP SHA-256
`66d974fac9318ddbe5896d16efea327fae528e0ce914997588959ad6ab74fd81`,
contains 2,466 completed case records: **2,463 passed, two skipped, and one case
with setup and teardown errors**. JUnit reports two errors, zero assertion
failures. The diagnostic returned 1 after 1,077.078 seconds; `acceptance=false`.
The before/after manifests agree on the unchanged fc3184e product tree
`c599c821341e583f7dc36280dc3086ff888d32da` and 759 tracked files.

The failing case is
`tests/test_content_integrity.py::test_all_captured_bytes_and_duplicate_refs_are_verified_once`.
Its cross-chunk parameter contains **1,048,593 bytes** (`CHUNK + 17`). Pytest
expanded those bytes into the node ID, making the full ID **1,048,688
characters**. In setup and teardown, `_update_current_test_var` failed while
assigning `PYTEST_CURRENT_TEST`, with
`ValueError: the environment variable is longer than 32767 characters`.
The test body did not run for that parameter. The other six byte cases did run.

This establishes a native Windows collection/execution blocker. It does not
establish that this was the sole cause of the earlier cancelled umbrella jobs:
the instrumented diagnostic actually finished. Earlier cancellations, missing
logs, and their unknown cause remain separate evidence.

## Narrow change

The seven byte-integrity parameters now have explicit short descriptive IDs.
Their order, byte values, cross-chunk length, function body and assertions are
unchanged. Comparing the full old and new module ASTs after removing only the
new `ids` keyword yields equality. The case existed on this development branch;
it is not a test-file modification relative to the v0.8.33 main baseline.

Three new tests collect the actual module in a child pytest process. They check
short unique identities, exact byte sizes/hashes in the original order, and the
completed historical diagnosis's explicit-only trigger. Collection observation
does not rewrite IDs or test parameters. The original large-content case still
reads and verifies the complete byte payload and duplicate references.

The historical Windows diagnostic workflow is now **workflow_dispatch only**.
Its fixed fc3184e target, diagnostic budget, job timeout, read-only permissions,
source checks and unconditional artifact upload are unchanged. Re-running the
known-broken frozen candidate on every PR synchronization would not validate this
repair. Explicit historical reproduction remains available; its failed run and
artifact are preserved. The ordinary `ci.yml` still runs against each PR head
and is byte-identical to the parent. No acceptance workflow is disabled.

## Executed local validation

- The two initial collection tests against the unchanged parent: **one failed,
  one passed**. The failure measured the 1,048,688-character ID; the passing
  check confirmed all original bytes and their order.
- Repaired byte-integrity module and the three new checks: **65 passed**, exit 0
  (62 existing cases plus three new cases), no skip or deselection.
- Full local collection: **2,481 test IDs**, exit 0, longest 2,133 characters;
  none reaches the Windows environment-value boundary including the teardown
  suffix. This is collection only, not 2,481 executed passing tests. The native
  historical collection had 2,466 cases; the current tooling adds 12 and this
  change adds three.
- Ruff, Python compilation, YAML parsing, whitespace checks and the unchanged
  product/ordinary-CI/dependency diff: checked separately in the validation pack.

A wider local run including the unchanged diagnostic-runner tests returned
**75 passed, two failed**. The two deadline cases received worker exit -11 before
reaching their expected timeout (parent exit 245 rather than 124). An isolated
checkout of the exact parent tree reproduced one failure, while the other case
passed in that attempt. Neither the diagnostic script nor those existing tests
was edited. The intermittent worker failure is unresolved and is not described
as a product regression caused by parameter naming, an environment root cause,
or a passed diagnostic-tool suite. Its logs are retained.

Local environment: Linux, Python 3.13.5, pytest 9.0.2. The source was restored from
the verified fc3184e Actions bundle plus the mounted 02f3bd3 additions; the full
parent tree matched `777370d56f511106d2a1459056540ff23b9463ef` before editing.
The native diagnostic used Windows/Python 3.12 and pytest 9.1.1. No native Windows
post-repair execution, installed-wheel test, browser replay or full product run
is claimed by the local checks.

## Impact, rollback and remaining gates

Four files change: the byte-test decorator, the new collection checks, the
historical diagnostic trigger and this record. Product source, original CI,
package/dependency metadata, existing assertions, original evidence and all
capture/reader behavior remain unchanged. No main update, merge, tag or release.

The decorator and its new collection checks can be reverted together, restoring
the known native failure. Restoring the workflow's automatic trigger would
repeatedly reproduce the old candidate rather than assess the repaired head.
The full Windows 3.10/3.12 matrix must finish on the new head. Any later timeout,
assertion failure or diagnostic-worker failure remains a separate open item;
this repair does not close the eight work packages or alter prior buyer verdicts.
