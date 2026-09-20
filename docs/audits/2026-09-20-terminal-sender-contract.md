# Terminal annotation and compact-inspector source compatibility

Baseline: `e69c86ef3e80c52e3bb90d3266bb473f518ee552`, tree
`a6dd192b1dba6e3c9e2579e9a74ae9fa5875166c`, PR #110.

## Actual CI blocker

I checked the completed baseline workflows before making another feature change.
The five specialty workflows passed; the umbrella CI failed. Its Ubuntu/Python
3.12 JUnit report contains **1 failed, 2,434 passed, 5 skipped**. The failed case
is `test_unexposed_turns_from_different_senders_do_not_merge` in the unchanged
`tests/test_agent_said_panel.py`.

The historical test searches the whole assembled inspector source for an
excluded sender/path expression. The new terminal-annotation helper introduced
that same expression for an unrelated outgoing-response check. This is a
source-contract compatibility failure, not evidence that a runtime sender mix-up
occurred. I did not delete, scope down, rename or weaken the historical test.

Evidence: Actions run `35489539438`, artifact `10598338725`, SHA-256
`5c86e23cc219227419a7a0c7a2e31b6066d06d6d6c30679ecc034ed5dee00468`.
Only the downloaded Ubuntu 3.12 JUnit was analyzed for the per-test totals;
other job failures/cancellations are not claimed as locally reproduced results.

## Narrow repair

The annotation now uses the inspector's existing `own(message, path)` comparison
through an explicit `hasExactSender` guard. The guard first requires a nonempty
string sender. That requirement is essential: the historical `own` helper alone
also permits missing senders for legacy display, which is not sufficient evidence
for this annotation or an earlier-message excerpt.

Both the outgoing-message predicate and normalized model-response annotation use
the same guarded comparison. Assignment admission, round grouping, selection of
the reported Response, accepted kinds/phases and source/native-identity checks
are unchanged. This refactoring removes the new source-contract collision without
relaxing sender requirements or merely reformatting the excluded expression.

## Behavioral coverage instead of a textual workaround

Twenty new Chromium cases check both annotation paths with missing, empty,
boolean, numeric, array, object, sibling-path and display-name senders. They also
check that parent/user assignments remain admissible while self/sibling
assignments do not become the selected Task. The original Response stays intact;
raw graph and conversation payloads remain unchanged.

These are synthetic SDK records through the shipped renderer using `set_content`,
not original buyer replay, native HTTP/Offline reading or fresh provider capture.
No browser API, ownership helper, key handler or renderer is substituted.

## Executed checks

- Unchanged historical inspector module on the baseline: **1 failed, 7 passed**.
- Same historical module after repair: **8 passed**.
- New sender/assignment behavior module: **20 passed**.
- Unchanged normalized model-terminal module: **17 passed**, exit 0.
- Unchanged earlier terminal-response module: **22 passed**, exit 0.
- Ruff on modified/new Python files, `git diff --check`, and assembled Live/static
  JavaScript syntax: **PASS**.

The four repaired groups contain **67 distinct passing tests**. An initial
combined regression command reached the tool deadline without returning its final
summary/exit status. It is not counted as a passing command; the two relevant
modules were rerun separately with complete reports and exit 0. The second suite
in that chained command never started. Baseline failures and repeats are not
added to the pass total.

Local environment: Linux, Python 3.13.5, Chromium 144.0.7559.96, Node 22.16.0.
Ruff and watchdog were installed from existing mounted wheel artifacts, with no
repository dependency change. Source was reconstructed from the mounted 6a144b3
Git bundle plus the validated patch sequence; its full tree matched the baseline
before editing. Tests import this source tree, not a new isolated wheel install.
The original inspector-test blob remains
`4a1cc2e92b4511cd9845efdb17ae217d6f7a0967`.

## Impact and rollback

Three files change: one production child-policy file, one new behavioral test
module and this record. There is no capture, parser, payload schema, index,
network/file access, authentication, camera, layout, polling, workflow, version or
historical-test change. Revert this commit independently to restore the previous
annotation implementation; captured evidence needs no migration.

Current-head CI must run again. This local repair does not establish complete
cross-platform acceptance or finish the eight-work-package plan. Existing Grok
reports retain their frozen commits and verdicts. No merge, tag or publication is
included.
