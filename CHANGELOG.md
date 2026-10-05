# Changelog

## Unreleased — target 0.8.35, release blocked

First observation-integrity batch in PR #112:

- Separate process exit, independent task verification, and observation status in
  graph/finalization metadata and live/saved viewers; keep archive finalization's
  own meaning and never infer complete capture from missing warnings.
- Preserve unknown-owner watch-root files when output equals/nests in the watched
  workspace. Add bounded metadata reconciliation and avoid recorder-event feedback.
- Persist polling-loss and silent-hook warnings; report nonexistent artifacts as
  not produced rather than returning apparently usable paths.
- Make `live` hook inspection read-only. Add explicit rootless `hooks install` and
  `hooks status`; pin the installing interpreter in generated hook commands.
- Restrict the primary event stream to POSIX 0600 and reject final-component
  symbolic and hard links. This does not yet harden all artifact writers or ACLs.
- Add a reproducible successful-task / failed-observation example and regression
  tests, including native equal/nested/external paths and the saved viewer.

Unfinished security, compatibility, system-path auditing, full-platform acceptance,
and independent exact-SHA release verification remain blocking. See
[observation integrity](docs/observation-integrity.md). No release has been made.
