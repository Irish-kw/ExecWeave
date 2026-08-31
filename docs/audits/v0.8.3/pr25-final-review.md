# PR #25 Final Pre-Merge Review

Audited PR: #25 `release/0.8.3-graph-ergonomics`

Audited head: `8362e74acd91d703991efd8cac2f0826c86cad3a`

Base: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`

This review was triggered by the final seven-item review left by the PR #25 implementation agent. Each item was re-checked against the repository instead of being accepted verbatim.

## Result

`PR25_PREMERGE_GATE = BLOCKED`

The product work is directionally sound and its current workflows are green, but the audited head still contains several merge-time regressions/gaps. The most important are live-layout x-position stickiness, camera bounds that still assume 160×50 nodes, incomplete tool-call ownership relation handling, and an integrity-test allowance that would remain open to future branches.

## Findings

### PM-001 — live layout keeps stale x after lane widths change

**Status:** CONFIRMED  
**Severity:** P1  
**Merge blocker:** YES

`execweaveBuildTopology()` recomputes `laneX` from current measured widths, but `fullLayout()` preserves an existing node as `{x: old.x, y: old.y}`. A live update that introduces a wider upstream lane therefore moves only newly placed nodes; existing downstream nodes keep the old x coordinate.

This directly violates the intended combination of adaptive lane widths and incremental live stability: y may remain stable, but x must follow the current lane geometry.

Required regression:

- render a live graph with ordinary-width upstream nodes;
- introduce a long upstream label that widens a lane;
- verify already-existing nodes in downstream lanes move to the new lane x;
- verify their y positions do not jump unnecessarily.

### PM-002 — camera/fit bounds still assume fixed 160×50 nodes

**Status:** CONFIRMED  
**Severity:** P1  
**Merge blocker:** YES

`live_view_script_c.py` still computes:

- graph max x from the largest node origin plus `160`;
- graph max y from `maxY + 50`;
- latest/follow/focus centers from `p.x + 80` and `p.y + 25`.

The PR introduces widths up to 320 and taller wrapped nodes, so Fit graph, Follow latest, Jump latest safe-zone checks and focus centering can all use the wrong geometry. The old `graphBounds()` loop also does not update `maxY` from positions before adding the fixed 50.

Required remediation:

- bounds must use each node's actual `execweaveWidthOf(id)` / `execweaveHeightOf(id)` (or an equivalent authoritative geometry source);
- latest/follow/focus must center on each node's actual width/height;
- retain a safe fallback for contexts where readability geometry is unavailable.

Required Chromium regression:

- wide one-line node;
- wrapped/taller node;
- Fit graph includes the full node rectangle;
- Follow latest and focus center on the actual node center, not the old 160×50 center.

### PM-003 — DOM text measurement has no cache

**Status:** CONFIRMED  
**Severity:** P2 performance  
**Merge blocker:** YES for this PR because the cost is newly introduced in the live layout loop and the fix is local

`execweaveMeasure()` calls `getComputedTextLength()` for every request. The function is used by node-width calculation, wrapping, prefix scans and ellipsis fitting, and topology rebuilds occur during live updates. Repeated labels/substrings can therefore cause repeated synchronous SVG text measurement.

Required remediation:

- cache measurements by text for the current label font context;
- keep the cache bounded or reset it at an appropriate graph/theme/font boundary;
- do not replace actual browser measurement with a hard-coded global approximation.

Evidence should include a regression or instrumentation showing repeated measurement of the same string does not repeatedly call the browser layout API.

### PM-004 — barycentre ordering ignores root-owned evidence

**Status:** CONFIRMED, narrower than the original wording  
**Severity:** P2  
**Merge blocker:** YES because PR #25 explicitly claims evidence-lane crossing reduction

Both `agentBarycenter()` and `sourceBarycentre()` only accept sources found in `childOrder`. Root agents are absent from that map. A file/model/endpoint written or used directly by the root therefore receives no barycentre signal and falls back to stable/alphabetical ordering.

The defect is not simply "duplicate barycentre code". The correctness issue is the source-order domain: all visible agent sources that participate in the execution spine must be representable, including roots.

Required regression:

- root directly owns/writes several evidence nodes whose names are deliberately reverse/alphabetically misleading;
- ordering must follow graph-source placement rather than filename/name order;
- child-agent behavior must remain unchanged.

### PM-005 — tool-traffic panel recognizes only one agent→tool-call ownership relation

**Status:** CONFIRMED; original provider attribution was incomplete  
**Severity:** P1 observability  
**Merge blocker:** YES

`viewer_agent_panel.py::toolCallsFor()` currently asks only for `REQUESTED_TOOL_CALL`, and `callersOf()` walks back only through that relation.

That is not sufficient across the repository:

- OpenCode event-bus/agent-trace `_tool_part_events()` emits `OBSERVED_TOOL_CALL` from the session agent to the tool call;
- Antigravity PostToolUse without tool identity emits `OBSERVED_TOOL_CALL` from the Antigravity agent to a `tool_call_observation`;
- the lifecycle relation inventory also recognizes `OWNED_TOOL_CALL` as an agent-owned tool-call relation.

Therefore the PR's new tool-traffic surface can silently omit legitimate provider evidence even though the raw graph contains it.

Required remediation:

- treat the supported agent→call ownership relation family explicitly (`REQUESTED_TOOL_CALL`, `OBSERVED_TOOL_CALL`, and `OWNED_TOOL_CALL` where present);
- do not rewrite provider evidence into a relation it did not emit;
- preserve the distinction in the raw graph while presenting all legitimate calls in the panel.

Required Chromium regression:

- existing `REQUESTED_TOOL_CALL` fixture;
- an OpenCode-style `OBSERVED_TOOL_CALL` fixture;
- an Antigravity observation with unavailable tool identity must be described as observed/identity-unavailable rather than disappearing;
- no duplicate card when the same logical call has more than one compatible ownership relation.

### PM-006 — panel graph lookup is unnecessarily quadratic

**Status:** CONFIRMED  
**Severity:** P2 performance  
**Merge blocker:** YES for the dense-graph scope of this PR

`relatedTo()` scans all raw edges and then resolves every result through `rawNode()`, which itself linearly scans all raw nodes. `toolCallLine()`, `toolCallsFor()` and `callersOf()` repeat those operations. This is avoidable O(E×N) behavior in a panel that is intended to remain usable on dense graphs.

Required remediation:

- build/reuse a node-by-id map and relation-aware incoming/outgoing edge indexes for the current raw graph snapshot;
- invalidate/rebuild the index when the underlying graph/edge/node collection changes;
- keep presentation behavior identical.

A synthetic large-tool-traffic regression/benchmark should prevent accidental return to repeated full scans.

### PM-007 — Stage Integrity test-change allowance is not scoped to PR #25

**Status:** CONFIRMED  
**Severity:** merge-process blocker  
**Merge blocker:** YES

The workflow adds an allowance for `tests/test_conversation_agent_focus.py` whenever that path appears in the diff. Unlike the release-metadata allowance above it, the condition is not restricted to the exact PR #25 branch.

`check_release_stage_integrity.py::_assert_existing_tests_untouched()` interprets `--allow-test-change PATH=REASON` as permission to change assertions in that baseline test file while retaining node IDs. If the current workflow lands, a future branch that edits the same file automatically receives the exception.

Required remediation:

- require `HEAD_REF == release/0.8.3-graph-ergonomics` (or an equivalently exact one-PR condition) **and** require the file to actually differ before granting this allowance;
- do not broaden the checker;
- rerun Stage Integrity on the new head.

## Merge priority

Fix in this order:

1. PM-001 sticky x regression
2. PM-002 dynamic camera/bounds geometry
3. PM-007 scope the integrity allowance
4. PM-005 complete tool-call ownership relation family
5. PM-004 include root-owned evidence in barycentre ordering
6. PM-003 measurement cache
7. PM-006 raw-graph lookup indexes

The ordering is for implementation convenience, not severity. All seven should be closed before merging PR #25 because each is either a direct regression introduced by the PR, a gap in a feature the PR claims to add, or an avoidable integrity/performance regression in the same touched code.

## Re-audit gate after a new PR #25 head appears

Do not reuse CI from `8362e74acd91d703991efd8cac2f0826c86cad3a` after any fix commit.

For the new head:

1. refetch latest `main` and PR #25;
2. require `behind_by=0` and `mergeable=true`;
3. inspect the exact diff for PM-001..PM-007;
4. require behavioral regressions for PM-001, PM-002, PM-004 and PM-005;
5. require performance evidence/regressions for PM-003 and PM-006;
6. require the PM-007 allowance to be branch-scoped and self-closing;
7. require all applicable workflows green on that exact head;
8. require zero unresolved review threads or explicit resolution;
9. only then change `PR25_PREMERGE_GATE` back to PASS.

## Gate summary

```text
PR25_AUDITED_HEAD=8362e74acd91d703991efd8cac2f0826c86cad3a
PM_001=CONFIRMED_P1_BLOCKER
PM_002=CONFIRMED_P1_BLOCKER
PM_003=CONFIRMED_P2_PERF_BLOCKER
PM_004=CONFIRMED_P2_BLOCKER
PM_005=CONFIRMED_P1_BLOCKER
PM_006=CONFIRMED_P2_PERF_BLOCKER
PM_007=CONFIRMED_MERGE_PROCESS_BLOCKER
PR25_PREMERGE_GATE=BLOCKED
V0.8.3_RELEASE_GATE=FAIL
```
