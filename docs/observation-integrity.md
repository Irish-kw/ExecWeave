# Observation integrity: 0.8.35 work in progress

This document describes the first implementation batch in PR #112. **It is not
release approval.** The package version remains 0.8.34 until all release blockers
are resolved, CI is green, and a new exact-SHA Grok Bot verification passes.

## Three different results

| Axis | Example | Meaning |
|---|---|---|
| Execution | `execution_state: succeeded`, return code 0 | The recorded process exited successfully. |
| Task verification | `passed` in the example's independent assertion | The example checked the expected primes output. A provider's claim is not this check. |
| Observation | `observation_incomplete` | Unknown writers, uncaptured file snapshots, zero specialized events, or possible short-lived-process loss remain. |

`graph.json.session_outcome.state` becomes `observation_incomplete` for a finished
run with observation gaps; `execution_state` preserves the actual process result.
`graph.json.observation_assessment` and `finalization.json.observation_assessment`
carry the reasons. `finalization.json.session_status` carries observation status.
The live and saved viewers show the observation axis separately from execution
and independent task validation. Missing old metadata means **not verified**, not
complete. An empty list of known problems is not proof of exhaustive capture.

`finalization.json.state: complete` still means that the named archive exports
were finalized and checked. It does **not** certify observation completeness or
task success. The archive axis is intentionally not overloaded.

## Files and process coverage

When output and watch root are equal, nested, or separate, only recorder-owned
paths are filtered. User files such as `primes.py` and `output.txt` remain visible.
Aggregate directory-modified hints along recorder paths are suppressed to avoid
self-triggering writes; concrete user file events and directory creation,
movement, and deletion are not suppressed by that rule.

A bounded before/after metadata inventory reconciles surviving file changes even
when native notifications were missed. It does not capture file bytes or identify
the writer, and cannot recover a file created and removed between inventories.
Unknown writers remain unknown. Portable process polling may miss short-lived
children; no missing-process count is invented from an absence of evidence.
An inventory limit or access failure produces an observation warning.

## Explicit rootless hook setup

Install ExecWeave in a user-owned virtual environment, then explicitly run:

```bash
execweave hooks install antigravity
execweave hooks status antigravity
execweave live --watch-root ./work --output-dir ./run -- agy
```

The same installation/status commands support `claude`, `codex`, `cursor`, and
`opencode`. `live` checks configuration without installing or rewriting hooks.
Installation as root is refused. Never ask an observed agent to use sudo or
repair an installation in `/usr/local/bin`.

Generated hook commands pin the installing Python interpreter and run the module
with `-I`; they do not depend on the agent's PATH or a shell shim. Do not resolve a
virtual environment's Python symlink to the base interpreter. Moving/removing a
venv requires an explicit reinstall. Provider-side approval may still be needed.
The installation status is `configured_unverified`, never proof of delivery.
A missing/empty/unreadable sidecar produces a durable `hook_no_evidence` warning.
A syntactically recognizable sidecar record is not proof of semantic validity.

## Reproduce the negative example

Using an installed candidate wheel, with a **new** directory:

```bash
python -m execweave.observation_demo --output-dir ./observation-negative
```

The workload writes a prime-number script, executes a short-lived child, and
writes the correct output. An exit-only trace looks successful. A separate
example assertion validates that output. ExecWeave nevertheless fails observation
acceptance because file writers are unknown and historical file snapshots were
not captured. It also declares portable polling's possible process loss and the
absence of specialized provider evidence. No provider, sudo, or system-path write
is involved; this example does not substitute for real `agy` acceptance.

The demo exits 0 when this **negative example** reproduces correctly. Its report
still says `observation_acceptance: FAIL`. General runs retain `task_validation:
unverified` unless a real independent validation contract supplies evidence.

## Remaining release blockers

This first batch does not yet complete privilege/system-path audit records,
time-qualified system-hook presence, privacy-default and redaction fail-closed
changes across all writers, Windows event-stream ACL verification, URL-token
hardening, a genuinely external protected integrity anchor, strict cross-version
evidence-reader coverage, or the file-only kill/upgrade/rollback drill. Main event
streams now use POSIX 0600 and reject final-component symbolic/hard links; that is
not a claim that every artifact writer or hostile same-UID access is protected.

A same-user home directory is **not** outside the observed process's trust domain.
An observation risk label is **not** runtime enforcement. Unsupported environments
or unavailable real-provider tests must be reported as BLOCKED/NOT_RUN, not PASS.
No merge, tag, GitHub Release, or PyPI upload is allowed from this stage. Published
PyPI verification is a separate post-publication gate, not a checkout test.
