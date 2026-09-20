# Preserve evidence when the Windows full suite does not finish

Product candidate: `fc3184e884a39ecd761c719c86672dfc1f957f8a`  
Product tree: `c599c821341e583f7dc36280dc3086ff888d32da`  
Tracking: PR #110; ChatGPT2GrokBot #89.

## Observed blocker and scope

The candidate has five successful specialty workflows, including the previously
audited three-OS viewer matrix. Umbrella CI 35494320063 ended cancelled twice in
the Windows full-suite jobs. Available metadata does not contain a completed
Tests result, and earlier job-log requests returned BlobNotFound. This does not
identify the offending test or prove whether the suite stalled, ran too slowly,
or was externally cancelled. At the initial read for this change, #89 had only
acknowledged the report-only investigation; no cause was reported.

I am not changing product behavior or guessing a repair. This batch adds one
opt-in diagnostic script, twelve tests, one narrowly triggered Windows workflow,
and this record. The original ci.yml, all historical tests, dependencies,
package metadata and every src/ file stay byte-identical. No timeout allowance
or test exclusion is added to the original acceptance workflow.

## Diagnostic design

The additional workflow checks out its tooling separately, then checks out the
unchanged fc3184e product candidate. Only Windows/Python 3.12 is targeted. Normal
project installation is used. The workflow is path-filtered, restricted to PR
#110 for pull-request events, read-only, and does not persist checkout credentials.
It records and compares the candidate's existing tracked-source fingerprints.

The script starts one pytest process with the ordinary default test collection
and `-q`, adding only a JUnit output path and an observer plugin. It does not
partition, reorder, filter, skip or rewrite the candidate's tests. Consequently
order-dependent behavior is not intentionally removed by starting a fresh
process for each test. Instrumentation can still affect timing and invocation
context; this is diagnosis, not acceptance of the original full command.

The observer records the ordered collection manifest and flushes JSONL events
for test start, each completed setup/call/teardown phase, test finish and session
finish. A periodic native faulthandler dump captures Python stacks without local
variable values. A last-started test or stack is evidence of execution location,
not by itself proof of causation. Journaling does not include test output; the
separate pytest.log retains ordinary captured diagnostic output. Review test
identifiers and logs before sharing beyond authorized repository access.

A supervising parent enforces a **25-minute diagnostic budget**, below both the
new job's 40-minute ceiling and the original job's unchanged 45-minute setting.
This creates room for cleanup, fingerprint comparison and artifact upload.
At its deadline it saves the owned process tree without command lines or
environment variables, terminates only its worker and captured descendants,
and returns **124**. A cancelled, incomplete, failed or zero-test run cannot
become a successful diagnostic. A completed diagnostic is still explicitly
marked `acceptance=false`; the original six-job acceptance matrix is separate.

The workflow uploads partial logs, collection, progress, stack samples, summary,
and available before/after fingerprints with `always()`. This improves evidence
retention for the script's own deadline; it cannot guarantee artifacts if the
runner dies, storage fails, or GitHub externally cancels the job before upload.
No GitHub-level cancellation root cause is asserted in this batch.

## Executed local validation

Environment: Linux, Python 3.13.5, pytest 9.0.2.

The first ten tests passed; the final run includes those tests plus two more:
**12 passed, exit 0**, with a completed JUnit report. Repeated runs are not added
as distinct cases. They execute real pytest subprocesses and native stack timers.
The tests cover ordered collection and phases, actual assertion failures, an
actual sleeping test stopped at a deadline, last-test/stack retention, cleanup
of a spawned descendant, survival of an unrelated sentinel process, collection
errors, refusal to overwrite evidence, invalid budgets, zero collected tests,
and the fixed workflow's deadline/exit-code/upload settings. No process,
faulthandler, clock or pytest outcome is mocked.

Ruff, Python AST parsing and workflow YAML parsing passed. No original product
suite was rerun locally for this diagnostic-only batch. No native Windows run
or successful cancellation diagnosis is claimed before Actions returns evidence.
The supplied source archive was verified as SHA-256
`1becc84e4f2ee76abade9ace509f32100d2be7d51e0f4e2114a4dee7c1909ad0` and its
complete tree matched the candidate before these additions.

## Impact, rollback and remaining gate

All four added files can be reverted together. The diagnostic's separate fixed
checkout leaves the frozen R2/R3 replay target and original reports intact.
The new script imports only standard-library modules, pytest and psutil already
present in the development environment. It is not installed as a product CLI.
No merge, release, tag, force push or dependency change is part of this batch.

The immediate next evidence is the completed diagnostic artifact: its last
started/finished tests, phase records, ordered manifest and native Windows stack
samples. Only that evidence, or another independently reproduced failing case,
should determine the minimal product/test-harness repair. #89 remains report-only;
this separately committed tooling does not retrospectively authorize it to edit
source. Windows acceptance and the broader work packages remain open.

Implementation references: pytest public reporting hooks in
https://docs.pytest.org/en/stable/reference/reference.html and Python's
faulthandler.dump_traceback_later contract in
https://docs.python.org/3.12/library/faulthandler.html .
