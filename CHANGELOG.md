# Changelog

## 1.0.1

- README banner is now an animated GIF, and README images use absolute URLs so they render on PyPI.

## 1.0.0

First release of the ExecWeave 1.0 line.

- `execweave` command-line interface: `record`, `live`, `top`, `hooks`, and the run-integrity tools.
- Local execution graphs (`graph.json`) with sender/recipient handoff tracking and explicit **receive not observed** diagnostics.
- Native adapters for Claude Code, Codex, Cursor, OpenCode, and Antigravity, plus framework adapters for the OpenAI Agents SDK, CAMEL, AutoGen, and MetaGPT, and local-runtime capture for Ollama and OpenAI-compatible endpoints.
- Local-only run-integrity sealing and verification, a live dashboard with token-authenticated access, and eight localized README and documentation sets.
- Includes all changes listed below.

## Changes since 0.8.35

- Added explicit recipient-specific **receive not observed** diagnostics and a prominent Dashboard alert. Missing receive telemetry remains observation uncertainty, not proof of message delivery failure.
- Removed the external GitHub integrity publication and expected-digest verification features. `execweave-integrity seal` and `verify` now perform **local consistency checks only**. A writer with permission to rewrite and re-seal the run can defeat these checks. Both continue to return machine-readable JSON and the historical local exit-code contract.
- Added reader provenance to validation and integrity verification output. Future or missing stream schema versions are rejected explicitly; reader downgrade to 0.8.34 is unsupported for new observations.
- Updated all eight Run Integrity locale guides. The integrity manifest schema retains its historical fixed `external_trust_anchor: false` field solely for archive compatibility; it is not an implemented external service or a security claim.
- Historical baseline tests and Stage Integrity remain unchanged. The external-anchor tests were replaced with local-only regressions.

## 0.8.35 — observation integrity and release hardening

Observation-integrity and release-hardening work:

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
- Run-integrity verification originally accepted an optional externally supplied
  `manifest_body_sha256`; that option was later removed (see Changes since 0.8.35). The local manifest
  declares `external_trust_anchor=false`.
- Add reproducible negative-observation and release-hardening regression tests while
  preserving all historical test IDs.
