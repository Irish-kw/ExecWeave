# Changelog

## 0.8.35 — observation integrity and release hardening

The `v0.8.35` tag, its GitHub Release, and the PyPI upload are the release record. Until
they exist, this entry describes unreleased code on `main`; the version metadata moves to
0.8.35 only in a separate release-only change. Final verification results for a published
version are recorded in its GitHub Release notes.

Observation-integrity and release-hardening work from PR #112:

- Separate process exit, independent task verification, observation completeness, and
  archive finalization. `finalization.json` persists a durable `run_assessment` bound to
  the exact `graph.json` SHA-256/size instead of deriving the result only in the viewer.
- Preserve unknown-owner watch-root files for equal/nested/external output layouts, add
  bounded metadata reconciliation, and report polling loss / silent hooks explicitly.
- Make `live` hook inspection read-only; explicit rootless hook install/status records
  time-qualified start/end configuration state and never treats configuration as delivery.
- Replace live query-token bootstrap with one-time POST pairing and an HttpOnly,
  SameSite=Strict cookie. API clients still use the private header token; no live credential
  is printed inside the announced URL.
- Give `live`/`top` an explicit provider/model plaintext policy. Full content is recorded by
  default because the run stays on the user's machine; `--metadata-only` opts out and
  `--capture-content` selects the default explicitly. Invalid policy values fail closed to
  metadata-only at automatic recorder boundaries without changing the observed workload's
  explicit SDK behavior.
- Write run evidence through private-file primitives: POSIX owner-only mode is established
  before sensitive bytes are published, Windows uses a protected owner DACL, and final
  component symlink/reparse, hardlink, and non-regular targets are rejected. Event streams,
  semantic streams, graph/viewer/conversation exports, finalization receipts, and content
  blobs use the hardened path.
- Emit durable observation-only risk records for actually observed privilege launchers and
  sensitive system-path changes. Records carry `default_decision=deny` and
  `enforced=false`; ExecWeave does not claim runtime prevention.
- Add strict graph reader version gates, explicit environment/task/operator failure domains,
  file-only upgrade/rollback tests, and readable finalized evidence for launch failures.
- Extend run-integrity verification with an optional externally supplied
  `manifest_body_sha256`. The local manifest still declares `external_trust_anchor=false`;
  only an independently stored digest can act as an external anchor.
- Add reproducible negative-observation and release-hardening regression tests while
  preserving all historical test IDs through exact SHA-256-pinned migrations.

Release gates for 0.8.35: full Linux/macOS/Windows CI (including real Windows ACL checks),
a safe real-provider acceptance path, and a new exact-SHA independent Grok Bot review of the
release-only commit must all pass before the `v0.8.35` tag, GitHub Release, or PyPI upload is
made. Clean-venv installation from public PyPI is verified after publication.
