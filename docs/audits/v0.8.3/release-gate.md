# ExecWeave v0.8.3 Release Gate

Baseline audit branch point: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`.

# V0.8.3_RELEASE_GATE = FAIL

The audit still has one confirmed P0, five confirmed P1 defects, two confirmed P2 defects, one strongly-supported P2 issue, and one unresolved suspected P1 Antigravity history-loss report. v0.8.3 must not ship until the mandatory conditions below are satisfied on one assembled release-candidate SHA.

## PR #25 merge gate is separate from the release gate

The PR #25 implementation branch itself is still:

- PR #25 head: `8362e74acd91d703991efd8cac2f0826c86cad3a`
- base: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`
- `PR25_BRANCH_PREMERGE_GATE = BLOCKED`

That branch has not yet received the hardening that closes `PM-001` through `PM-007`.

The hardening exists separately as stacked PR #27:

- PR #27 base: `release/0.8.3-graph-ergonomics` (PR #25 branch)
- validated PR #27 head: `c7d338ca95839e1fd30829c9208fc9d1eda62137`
- `PR25_HARDENING_STACK_GATE = PASS`
- CI run `33376194384`: success on Ubuntu/macOS/Windows
- Viewer Agent Isolation run `33376194481`: success, including real Chromium
- Provider Capability Stage Integrity run `33376194392`: success
- Windows Launcher Compatibility run `33376194426`: success

PR #27 closes the seven source-level findings from `pr25-final-review.md` and also closes `PM-008`, a GIF replay/export adaptive-geometry defect discovered during hardening. The final re-audit additionally removed a live performance regression where every newly added node was treated as an existing-node dimension change and caused a whole-graph rerender.

This means **PR #27 is ready to be merged into PR #25's branch**, but **PR #25 must not yet be merged into `main`**. After PR #27 is merged into the PR #25 branch, the new immutable PR #25 head must receive the same exact-head CI/Chromium/stage-integrity/launcher revalidation. No merge has been authorized or performed by this audit.

Even after PR #25 eventually passes and merges, the provider/conversation identity blockers below remain. No version bump, tag, GitHub Release, or PyPI publication is authorized.

## Mandatory conditions before PASS

### 1. Fix AUD-001: cross-session root conversation merge

Two independent provider sessions must never become one synthesized `<provider>:root` conversation merely because both are roots.

PASS evidence:

- invert the existing OpenCode characterization to require two conversation identities;
- add at least one second provider/root-session fixture proving the rule is system-wide;
- provider-native threads are not duplicated by synthesized threads;
- messages from independent sessions cannot appear in one conversation panel.

### 2. Fix AUD-002 and AUD-003: endpoint-scoped inference identity

Native request IDs are authoritative only inside the endpoint/runtime/gateway identity domain that emitted them.

PASS evidence:

- two vLLM instances with the same native request ID produce distinct request nodes;
- two LiteLLM proxy endpoints with the same native request ID produce distinct request nodes;
- OpenRouter/gateway generation reconciliation stays within the same endpoint scope;
- deployment IDs cannot join unrelated gateway instances;
- ID-less repeated observations do not accidentally become one occurrence.

### 3. Fix AUD-004: OpenCode split agent identity

One OpenCode provider session must use one canonical graph agent identity across semantic events, full-fidelity content, conversation reconstruction, model calls and tool calls.

PASS evidence:

- one plugin cycle cannot materialize both `agent:OpenCode` and `agent:opencode:session:<sessionID>` as separate logical roots;
- two independent OpenCode sessions stay distinct;
- parent/child session topology still works when `parentID` is exposed.

### 4. Fix AUD-005 and AUD-006: Antigravity topology/identity cluster

A validated Antigravity transcript proves conversation identity/content; it does not by itself prove root status. Tool/model/content observations that already carry an exact `conversationId` must resolve consistently to the conversation's agent identity.

PASS evidence:

- a child-shaped Stop transcript is not assigned `root_topology_evidence=provider_session_root` solely from `conversationId` + transcript path;
- PostToolUse + Stop sharing a conversation ID resolve to one logical agent;
- validated parent -> child mapping still uses positive evidence and continues to abstain on an invalid/torn implementation wire;
- abstention never turns a child conversation into a fabricated independent provider root.

### 5. Reproduce or dismiss SUS-001: Antigravity historical-turn loss

A sanitized real Antigravity three-turn fixture must be exercised through archive, graph, conversation projection and Chromium.

PASS evidence:

- round 1 remains present and folded;
- round 2 remains present and folded;
- current round 3 remains open;
- repeated Stop/live poll updates do not delete earlier rounds;
- manually opened/closed historical folds persist;
- root and child conversation content remain isolated.

If the real fixture cannot reproduce the original report, document the exact provider/runtime version and evidence used to dismiss it.

### 6. Land and revalidate the PR #25 hardening stack

Current state:

`PR25_HARDENING_STACK_GATE = PASS`

`PR25_BRANCH_PREMERGE_GATE = BLOCKED`

Before PR #25 may merge to `main`:

1. merge PR #27 into `release/0.8.3-graph-ergonomics` only after explicit merge authorization;
2. fetch the resulting new PR #25 head and verify it actually contains PM-001..PM-008 hardening;
3. discard all workflow evidence from the old PR #25 head;
4. rerun full applicable CI, Chromium viewer behavior, Stage Integrity and Windows Launcher on the exact new PR #25 head;
5. re-audit the exact PR #25 diff against current `main`;
6. only then change `PR25_BRANCH_PREMERGE_GATE` to PASS.

After PR #25 eventually lands, provider/identity remediation should start from the new `main`. When all release blockers are fixed, assemble one intended release-candidate SHA containing both the merged PR #25 work and provider fixes.

PASS evidence on one final candidate SHA:

- adaptive width / wrapping / tooltip / inspector;
- clear focus by control, empty canvas and Escape;
- focus survives or clears coherently across polling/removal/folding;
- file/endpoint lane separation and component packing;
- routing determinism and crossing regression floor;
- fold budgets small/default/no-fold;
- Live, Finished and standalone `viewer.html` parity;
- manual zoom, Fit graph and Follow latest under polling;
- search/filter/Unicode combinations;
- replay/export sanity;
- small, medium and 100–300+ node graphs with no unexplained overlaps/intersections;
- tool traffic still maps to the corrected canonical agent identity after AUD-004/AUD-006 remediation.

### 7. Every confirmed P0/P1 must have a behavioral regression

Source-string assertions alone are not sufficient for the release gate. Provider identity regressions must assert actual graph IDs/topology/conversation identities. Dashboard state regressions must run in Chromium. Sanitized real provider evidence is preferred where available.

### 8. Full release-candidate test/CI matrix must be green

At minimum:

- focused provider/identity/conversation regressions;
- existing full pytest suite;
- Ruff;
- Chromium dashboard E2E;
- Linux/macOS/Windows CI paths applicable to changed files;
- provider-capability/stage-integrity gates;
- package/wheel/launcher workflows where path filters require them.

## P2 policy

P2 findings do not automatically block v0.8.3 once all P0/P1 conditions are green, but each must be fixed or explicitly accepted/tracked before changing this file to PASS.

Current P2 items:

- AUD-007: Provider Capability Stage Integrity inventory omits supported integration paths.
- AUD-008: global raw-string model catalog can merge unrelated providers.
- AUD-009: ID-less response fingerprint is not a true occurrence identity (strongly supported).

AUD-008 or AUD-009 becomes release-blocking if the P1 endpoint/identity repair depends on the same canonicalization path and leaves materially false graph joins.

## Known limitations that do not independently block PASS

- portable polling can miss short-lived sockets;
- descendants that outlive the launched root are not continuously sampled by the portable loop;
- Gemini exact tool before/after pairing can be unavailable when the provider exposes no stable call ID;
- Antigravity child linkage depends on a live-verified implementation wire and intentionally abstains on mismatch;
- conversation preview is UI-bounded while archived raw evidence remains available.

## Current blocker list

1. PR #27 hardening is validated but has not yet been merged into the PR #25 branch; PR #25 exact new head therefore does not exist yet.
2. `AUD-001` — P0 — independent root conversations merge.
3. `AUD-002` — P1 — local-runtime request identity not endpoint scoped.
4. `AUD-003` — P1 — gateway request/deployment identity not endpoint scoped.
5. `AUD-004` — P1 — OpenCode generic/session agent split.
6. `AUD-005` — P1 — Antigravity Stop archive fabricates provider-root provenance.
7. `AUD-006` — P1 — Antigravity tool/conversation identity split.
8. `SUS-001` — suspected P1 — real Antigravity historical-turn loss must be reproduced or dismissed.
9. Final assembled candidate has not rerun the combined provider + dashboard + cross-platform release matrix.

## Rule for changing to PASS

Do not change `V0.8.3_RELEASE_GATE` to PASS because PR #27 is green, because PR #25 is eventually merged, because individual fix PRs are green, or because the existing test suite is green.

Change it only after all mandatory conditions above are verified on the same intended v0.8.3 release-candidate SHA.
