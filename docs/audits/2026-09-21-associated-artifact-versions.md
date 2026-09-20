# Associated artifact versions and explicit file comparison

Baseline: `cd1e0b44957c9e9bf03e83ab7a3d8efef8434a97`, tree
`4efb36d1b2a130df9c89cb99965c5caec5afc444`, PR #110.

## User journey and authority boundary

I extended the existing external-report workflow so a report can carry an
explicit list of associated file versions. The operator supplies each logical
relative name and the local file to hash:

```bash
python -m execweave.task_validation \
  --graph /copied-run/graph.json --task-id 'EXACT_NATIVE_TASK_ID' \
  --junit /checks/tests.xml --validator 'Operator-selected QA' \
  --criterion 'Specified checks only' \
  --artifact 'src/main.py=/delivered/src/main.py' \
  --artifact 'tests/test_main.py=/checks/test_main.py' \
  --output /new-associated-report.json
```

The existing v1 receipt remains unchanged when no artifacts are selected. An
artifact-bearing receipt uses `execweave.external-task-report.v2`; old readers
reject it rather than silently treating its extra version claim as checked.
The manifest contains logical names, exact sizes, file SHA-256 values, and a
SHA-256 over the UTF-8 encoding of compact `[name,size,hash]` arrays. Local absolute
paths and artifact bodies are not included. The manifest association is operator
supplied, just like the existing verifier label and criterion.

In Review external task reports, Associated artifact versions starts as **not
checked**. Selecting a directory uses its actual FileList and hashes only the
explicitly listed matching relative paths. Match, same-size hash mismatch, size
mismatch, missing files, unavailable verification and cancellation are distinct.
Different artifact manifests keep otherwise identical reports separate. A
report without a manifest states that no file versions were supplied.

**This does not prove the tests executed on those files.** A correct manifest
hash is not an authenticated signature, and a matching folder is not a verified
independent task result. The original task axis remains unverified. This closes
the ability to record and compare operator-associated file versions; controlled
verifier execution and authenticated tested-version attestation remain open.
No statement in this feature promotes a reported pass to universal task success.

## Boundaries, limits and privacy

- Only explicit `--artifact NAME=FILE` arguments authorize local artifact reads;
  report text and graph paths never trigger them. Inputs must be bounded regular
  files. Leaf symlinks/reparse points and observed per-file mutations are refused.
  Selected file paths are explicit operator paths, not a filesystem sandbox;
  the sequential reads are not an atomic directory snapshot.
- Names must be normalized NFC portable relative paths. Parent traversal,
  absolute/drive paths, control/surrogate characters, reserved device names,
  trailing spaces/dots and duplicate/case-colliding names are rejected.
- Maximum 100 associated files, 8 MiB each, 64 MiB in total. The selected browser
  directory inventory is capped at 10,000 files. Extra files are counted as
  uninspected and their bodies are not opened. No directory-wide completeness,
  file-permission, dependency or environment equivalence is claimed.
- Browser verification requires native SHA-256. A new comparison removes the
  preceding match state immediately. Close, new folder selection, report
  replacement or execution/task changes prevent pending results from appearing
  in another scope. Completed results are labeled as past comparisons, not
  continuous monitoring. Selected File objects are not retained for future reads.
- No files are uploaded, commands executed, original archives overwritten or
  browser storage written. Hashes and names remain potentially sensitive.
  Existing receipt overwrite refusal and original report/task validation apply.

## Validation

The initial three-case CLI check against the unchanged baseline produced two
failures because `--artifact` did not exist, and one legacy-v1 pass. On the final
source, 31 new core tests passed, covering actual byte hashes, version changes,
Unicode/empty content, malformed manifests, explicit selection and no overwrite.

Completed focused regression commands:

```bash
python -m pytest -q tests/test_task_validation_reports.py \
  tests/test_run_assessment.py tests/test_task_artifact_binding.py
# 136 passed (105 existing, 31 new)

python -m pytest -q tests/test_task_validation_viewer.py -k 'not native'
# 20 passed, 4 pre-existing native cases not selected

python -m pytest -vv tests/test_task_artifact_viewer.py -k 'not native'
# 19 passed, 4 new native cases not selected
```

These cover **175 distinct passing checks** across three commands, not a complete
uninterrupted product suite. The two browser-component groups explicitly reuse
the existing named hashlib digest bridge. They exercise actual File input and
UI/scope behavior, not native WebCrypto acceptance. The old tests are unchanged.

The four new native file-origin cases were attempted separately. All four were
blocked before the journey by `ERR_BLOCKED_BY_ADMINISTRATOR` at `page.goto`.
They remain enabled in normal CI with no bridge, request replacement, new skip
or browser-policy bypass. Four older native cases were not rerun in this batch.
One combined browser command exceeded the command budget after partial progress,
without a final JUnit result; it is preserved as an incomplete attempt, not a
passing combined run. The separate completed commands above are the actual
reported results. Initial Ruff style findings were corrected before final checks.

The baseline was restored from the verified 7f51c21 source bundle and the provided
cd1e0b4 changed-file package. Its reconstructed tree exactly matched the remote
baseline tree before edits. Local environment: Linux/Python 3.13.5 and installed
Chromium. Repository dependencies were not changed; setup used local wheels.
The PR records final source-tree equality, syntax/integrity checks and package
verification. Independent native verification is requested separately on the
pushed commit. No previous verifier report is retargeted or presented as a pass
for this feature.

## Impact and rollback

Six files: one new artifact module, the existing CLI and report-viewer integration,
two new test modules and this audit record. Recorder, graph, provider, server,
layout, existing tests, workflows, dependencies and version metadata are unchanged.
Revert the module and CLI/viewer integration together; v1 receipts still work.
V2 receipts remain standalone records and need no original-data migration.
This is not completion of W01, content-aware redaction, the full provider matrix,
large-run acceptance or final buyer acceptance. Main and release refs are untouched.
