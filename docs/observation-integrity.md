# Observation integrity (0.8.35)

This document describes the observation-integrity semantics introduced by PR #112
and their honest limits. **It is not release approval.** The version metadata moves
to 0.8.35 only in a separate release-only change; whether 0.8.35 was published, and
with which verification evidence, is recorded by the `v0.8.35` tag, its GitHub
Release notes, and the PyPI upload.

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

## Security and privacy hardening in this checkpoint

`live` and `top` now set an explicit provider-content policy for every observed child.
The default is `full`: complete provider/model plaintext exposed by an integration is
recorded, because the run stays on the user's machine. `--metadata-only` is the explicit
opt-out, and `--capture-content` selects the default explicitly. An invalid configured
value resolves to metadata-only. The policy is enforced at automatic
hook/proxy/callback/probe boundaries, not inside the low-level content store, so
observability does not change an application's explicit SDK capture semantics.

The browser no longer receives the API token through a query string. The announced live
URL contains no credential. A one-time pairing code is POSTed to `/pair` and exchanged for
an `HttpOnly; SameSite=Strict` cookie; query-token authentication is rejected. Header-token
access remains available for non-browser local API clients such as `top`.

Sensitive run writers establish private permissions before publishing bytes. POSIX uses
owner-only mode; the Windows implementation applies a protected owner DACL and verifies
the resulting security descriptor. Final-component symbolic/reparse links, non-regular
files, and multiply linked targets are rejected. This covers the primary event and semantic
streams, content blobs, graph/viewer/conversation exports, and finalization receipts.
Actual Windows certification remains a release-CI requirement.

When ExecWeave actually observes a privilege launcher or a create/modify/delete operation
under a sensitive system path, it records a durable risk event with
`default_decision=deny` and `enforced=false`. This is an observation/default-policy record,
not proof that ExecWeave prevented the operation. Hook configuration is sampled at session
start and end; the event timestamps provide the time-qualified receipt and delivery remains
separate.

`finalization.json` now persists the derived run assessment and binds it to the exact
`graph.json` SHA-256/size. Execution failures distinguish `task`, `environment`, and
`operator` domains. Graph readers accept the documented supported schema set and reject
unknown future versions instead of attempting a best-effort parse.

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

## Release gates and honest limits

The source-level requirements above are implemented, but **release acceptance is not
automatic**. The finished candidate must pass the complete Linux/macOS/Windows matrix,
including native Windows ACL behavior, and a new independent exact-SHA review. A safe real
provider run must be used where the verifier can guarantee that the provider cannot escape
into privileged/system paths; an unsafe passwordless-sudo host remains BLOCKED rather than
being treated as a passing test.

The local `integrity.json` still truthfully declares `external_trust_anchor: false`.
`execweave-integrity verify --expected-manifest-body-sha256 <digest>` can compare against a
digest supplied from an external trust domain, but the digest only becomes an anchor when
it is actually stored somewhere the observed process cannot rewrite (for example a CI or
review record controlled outside the run). A same-UID home file is not such a boundary.

File-reader upgrade/rollback behavior and incomplete/environment-failure archives now have
regression coverage. Hard-kill behavior still cannot be represented as a successful
finalization event when the recorder itself is forcibly terminated; consumers must treat a
missing terminal receipt as incomplete evidence, not reconstruct a fictitious success.

The code stage merges to `main` without a version change. The 0.8.35 version bump is a
separate release-only change, and no tag, GitHub Release, or PyPI upload is made until full
CI and a new exact-SHA independent acceptance of that release commit both pass.
Published-PyPI clean-install verification remains a separate post-publication gate.
