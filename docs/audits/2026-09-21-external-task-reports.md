# External task report intake and review

Baseline: `7f51c21175e175dd5eec7be2658026e240568e3a` (PR #110).
This is the W01 external-test-evidence path, not a completed independent task
validator or a release-ready claim.

## What is available

I added an explicit operator workflow for binding an existing UTF-8 JUnit report
to one exact native task snapshot and reviewing it in the shared Dashboard:

```bash
python -m execweave.task_validation \
  --graph /path/to/run/graph.json \
  --task-id 'task:framework:run:exact-native-id' \
  --junit /path/to/external-tests.xml \
  --validator 'Operator-selected QA check' \
  --criterion 'The specified acceptance test set' \
  --output /path/to/new-task-report.json
```

Use **Run assessment > Task verification > Review external task reports**, then
select the new JSON receipt. The CLI succeeds when it creates a valid receipt,
including a receipt describing failed checks. Its exit zero is not a passing
assessment; inspect `summary.state`. It refuses to overwrite an existing output.
No command from a report is executed, no report is fetched automatically, and
no original run, graph, captured body or archive receipt is rewritten.

The binding contains the run/session/source identity and a SHA-256 fingerprint
of the complete recorded task node. Same-named agents or another task cannot
substitute for the exact native task. The metadata assessment publishes at most
200 task fingerprints before display folding. Omitted, ambiguous, inferred or
projected subjects do not become valid receipt targets. Changing the recorded
task snapshot revokes its prior imported evidence.

## Evidence and authority are deliberately different

A report can show `checks_passed`, `checks_failed`, `partial` (passing and skipped
cases), or `no_executed_checks`. The browser independently parses the embedded
original XML and recounts case records; a supplied summary is not trusted. Zero
cases, all-skipped cases, missing case records behind a positive summary, bad
counters, duplicate case identities and unsupported outcome shapes never become
an all-passing check result. Failures/errors remain visible beside native agent
completion reports. Different contradictory reports are retained separately;
the latest report does not silently erase the previous one.

**This does not authenticate an independent verifier.** The operator chooses the
task association, verifier label and criterion. The report checksum verifies
its embedded bytes, not who ran the tests, whether they tested the delivered
artifact version, whether the criterion is sufficient, or whether a producer
forged the report. Every result explicitly states `authority_authenticated=false`
and `task_success_implied=false`. The original task axis remains unverified.

This is useful external evidence intake, not a universal correctness oracle.
W01 remains open for an authenticated/controlled validator execution contract,
artifact-version binding and full lifecycle acceptance. Importing a JUnit file
must not be relabeled as those stronger guarantees.

## Parser and UI boundaries

The supported subset is unnamespaced testsuites/testsuite/testcase XML with
standard failure/error/skipped children. Optional suite counters must equal the
recounted descendant cases. Testcase status/result extensions, ambiguous repeated
identities, multiple outcomes, DTD/entity declarations, non-UTF-8 declarations,
nested markup in output fields, non-finite/duplicate JSON fields and oversized
inputs are rejected rather than interpreted permissively. Unsupported producer
variants require a separately tested extension; they are not evidence of a
provider defect.

The report budget is 2 MiB UTF-8, 10,000 cases, 50,000 XML elements and depth 32.
The selected JSON receipt is bounded at 8 MiB. At most 20 reports are held in
memory; the case-detail view shows the first 50 while all supported cases are
counted. A task fingerprint has a 1 MiB canonical JSON budget. The CLI reads only
explicitly supplied regular files, with bounded reads and metadata change checks.

Report checksums require native WebCrypto in the shipped UI. Missing crypto,
malformed inputs, changed scope, changed task fingerprints and cancelled pending
reads cannot create an accepted report. File contents are never inserted as HTML,
linked URLs are not followed, and report commands are not executed. The ledger
contains task bindings, report hashes and recounted case summaries, not raw XML.
It is tab-local, not persistent browser storage or an archive extension. Report
files may still contain sensitive test output; keep them private when appropriate.
Escape returns to the original action without clearing the graph selection.

Primary format/security references reviewed:
- https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files
- https://docs.python.org/3/library/xml.html

## Validation and provenance

The complete baseline came from Actions artifact `10609173935`, SHA-256
`14503c23847c6000601fbe37e89cebee8159c84fd84091e9a69afb07d5bfa690`.
Its checked-out source tree is `71ffc09fa692ef6f606a072b3f9dfb36743c7d65`.

Final focused checks:
- 40 new core/CLI cases plus 65 unchanged run-assessment cases: **105 passed**,
  one completed command, no skip/deselection.
- 20 new browser component cases: **20 passed**, four native cases deselected
  from that component command.
- The native file/crypto cases were separately attempted: all four were blocked
  at `page.goto(file:...)` by `ERR_BLOCKED_BY_ADMINISTRATOR`, before import.
  They remain enabled in CI and are not counted as passing native evidence.

Thus 125 distinct focused cases passed. Earlier iterations overlap and are not
added. The real-report test executes a real pytest child with one pass, one
failure and one skip, then parses its actual JUnit output. Browser parser parity
checks accept/reject the same cases as Python. The explicitly named component
digest bridge uses Python hashlib for UI/identity testing; it is not native
browser cryptographic acceptance. Native tests have no bridge or request mock.
The positive checksum component results must not stand in for those native tests.

Ruff, assembled JavaScript syntax, installed-package/source equality and exact
local/remote tree results are recorded with the candidate in the PR. Network
package installation was unavailable; local setup used previously downloaded
wheel inputs without changing project dependency declarations. No native Windows,
macOS, fresh-provider or original-capture replay is claimed by these local tests.

## Change impact and rollback

Seven files: two new product modules, metadata-assessment and its shared-view
integration, two new test modules and this record. Existing tests, provider
adapters, event capture, server endpoints, dependencies, workflows and version
metadata are unchanged. The CLI is an installed Python module, without changing
existing command routing or adding a package entry point.

Removing the two new modules together with their assessment/injection integration
reverts this feature. New receipts are separate files; no data migration or raw
archive rewrite is required. Existing process results, native task reports,
content-health counts and delivery states retain their prior meanings.

Grok #92's three-path PASS remains scoped to 7f51c21. It does not validate this
new task-report feature. This change requires its own fixed-target native review
and current-head CI; main and release state remain unchanged.
