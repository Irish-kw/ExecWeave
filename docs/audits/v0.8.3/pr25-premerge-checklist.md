# PR #25 Pre-Merge Readiness — v0.8.3 Graph Ergonomics

This document is a pre-merge gate for PR #25 (`release/0.8.3-graph-ergonomics`). It does not authorize a v0.8.3 release and does not change the system-wide release gate in `release-gate.md`.

## Snapshot

- Checked against `main`: `1ec0dcb0171f9346f8232a99e857cbd6b3168f08`
- PR #25 head: `8362e74acd91d703991efd8cac2f0826c86cad3a`
- PR state: open, ready for review, mergeable
- Branch relation to `main`: **ahead 17 / behind 0**
- Unresolved review threads: **0**
- Release metadata: remains `0.8.2` by design

## CI / validation on the checked head

All PR-triggered workflows on `8362e74acd91d703991efd8cac2f0826c86cad3a` completed successfully:

- `CI` — success
- `Viewer Agent Isolation` — success
- `Provider Capability Stage Integrity` — success
- `Windows Launcher Compatibility` — success
- `Documentation i18n` — success

PR #25 reports 894 passed / 6 skipped, Ruff clean, stage-integrity baseline subset preserved, and i18n failures = 0. Browser coverage includes adaptive sizing, lane separation, reversible focus, routing/crossing regression, and tool-traffic presentation.

## Changed-file scope

PR #25 changes 12 paths:

- `.github/workflows/provider-capability-stage-integrity.yml`
- `docs/v0.8.3-graph-ergonomics.md`
- `src/execweave/live_view_markup.py`
- `src/execweave/live_view_readability.py`
- `src/execweave/live_view_script_c.py`
- `src/execweave/viewer_agent_panel.py`
- `tests/test_conversation_agent_focus.py`
- `tests/test_graph_clear_focus_e2e.py`
- `tests/test_graph_edge_routing_e2e.py`
- `tests/test_graph_lane_separation_e2e.py`
- `tests/test_graph_node_sizing_e2e.py`
- `tests/test_tool_traffic_e2e.py`

PR #26 changes only files under `docs/audits/v0.8.3/` plus `tests/test_v083_system_audit_characterization.py`. There is **no changed-path overlap** between PR #25 and PR #26 at this snapshot.

## Interaction with PR #26 findings

PR #25 is mergeable as an isolated dashboard/ergonomics improvement, but it does **not** remediate the release-blocking identity findings from PR #26:

- `AUD-001` cross-session root conversation merge
- `AUD-002` local-runtime request identity missing endpoint scope
- `AUD-003` gateway request/deployment identity missing endpoint scope
- `AUD-004` OpenCode generic/session agent split
- `AUD-005` Antigravity fabricated root provenance
- `AUD-006` Antigravity tool/conversation identity split
- `SUS-001` Antigravity historical-turn loss still awaiting real sanitized replay evidence

Two specific interaction notes must survive the merge:

1. `viewer_agent_panel.py` now surfaces tool traffic by walking the raw graph. That is useful, but existing split agent identities can therefore split tool traffic and conversation content across different visible agent identities. This is an upstream identity defect, not a reason to revert the tool-traffic surface. After identity remediation, rerun the PR #25 tool-traffic Chromium tests on the assembled candidate.
2. `live_view_readability.py` treats agent nodes as execution-spine members even when provider edges are absent, to avoid visually demoting legitimate subagents. This is a layout rule only. It must never be treated as evidence that parent/child topology is correct. PR #26's positive-evidence topology requirements still apply.

## PR #25 pre-merge gate

`PR25_PREMERGE_GATE = PASS`

This PASS means only that PR #25 itself is ready to merge into `main` if the atomic checks immediately before merge still match this snapshot.

It does **not** mean `V0.8.3_RELEASE_GATE = PASS`.

## Atomic checks immediately before merge

Before merging PR #25, perform these checks again from GitHub, in this order:

1. Fetch latest `main`.
2. Fetch latest PR #25 metadata/head.
3. Require PR #25 expected head SHA to still be `8362e74acd91d703991efd8cac2f0826c86cad3a`; if Claude pushes again, stop and audit the new head instead of merging the old snapshot.
4. Require PR #25 to remain `mergeable=true`, open, and non-draft.
5. Compare PR #25 head against latest `main`; require `behind_by=0`. If `main` moved, stop and re-evaluate against the new base before merge.
6. Re-read workflow runs for the exact expected head; require every applicable workflow to be completed/success.
7. Re-check unresolved review threads; require zero unresolved threads or an explicit decision on each.
8. Do not change release metadata, create a tag, create a GitHub Release, or publish PyPI as part of this merge.
9. Merge with an expected-head guard so GitHub rejects the operation if the branch moved between the final read and the write.

## Immediately after merge

After PR #25 lands:

1. Fetch `main` and record the new main SHA / merge SHA.
2. Verify PR #25 is actually merged and its head matches the audited expected SHA.
3. Keep PR #26 open as the release-blocking audit; do not treat it as implicitly resolved by the PR #25 merge.
4. Start provider/identity remediation from the new `main`, not from the pre-merge audit baseline.
5. Preserve remediation ordering: conversation identity -> endpoint identity -> provider session identity -> Antigravity topology/ownership -> real three-turn replay -> P2 cleanup.
6. Only after those fixes are assembled with PR #25 on one release-candidate SHA should the full provider + dashboard + cross-platform matrix be rerun for the v0.8.3 release gate.

## Gate summary

```text
PR25_PREMERGE_GATE=PASS
PR25_EXPECTED_HEAD=8362e74acd91d703991efd8cac2f0826c86cad3a
PR25_BEHIND_MAIN=0
PR25_UNRESOLVED_REVIEW_THREADS=0
PR25_WORKFLOWS=ALL_GREEN
PR25_PR26_PATH_CONFLICT=NONE
PR25_MERGE_AUTHORIZATION=NOT_YET_EXECUTED
V0.8.3_RELEASE_GATE=FAIL
```
