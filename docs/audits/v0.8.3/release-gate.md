# ExecWeave v0.8.3 Release Gate

Baseline audit branch point: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`.

# V0.8.3_RELEASE_GATE = FAIL

The audit found one confirmed P0, five confirmed P1 defects, two confirmed P2 defects, one strongly-supported P2 issue, and one unresolved suspected P1 Antigravity history-loss report. v0.8.3 must not ship until the mandatory conditions below are satisfied on one assembled release-candidate SHA.

## Mandatory conditions before PASS

### 1. Fix AUD-001: cross-session root conversation merge

Two independent provider sessions must never become one synthesized `<provider>:root` conversation merely because both are roots.

PASS evidence:

- the existing OpenCode characterization test is inverted to require two conversation identities;
- at least one second provider/root-session fixture proves the rule is system-wide;
- no provider-native thread is duplicated by a synthesized thread;
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

### 6. Assemble PR #25 work and rerun all dashboard behavior on the release candidate

PR #25 is separate work and reached ready-for-review state during this audit. Its branch results are not sufficient by themselves for a release PASS.

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
- small, medium and 100–300+ node graphs with no unexplained overlaps/intersections.

### 7. Every confirmed P0/P1 must have a behavioral regression

Source-string assertions alone are not sufficient for the release gate.

Provider identity regressions must assert actual graph IDs/topology/conversation identities. Dashboard state regressions must run in Chromium. Sanitized real provider evidence is preferred where available.

### 8. Full release-candidate test/CI matrix must be green

At minimum:

- focused provider/identity/conversation regressions;
- existing full pytest suite;
- Ruff;
- Chromium dashboard E2E;
- Linux/macOS/Windows CI paths applicable to the changed files;
- provider-capability/stage-integrity gates;
- package/wheel/launcher workflows where path filters require them.

## P2 policy

P2 findings do not automatically block v0.8.3 once all P0/P1 conditions are green, but each must be either fixed or explicitly accepted/tracked before changing this file to PASS.

Current P2 items:

- AUD-007: Provider Capability Stage Integrity inventory omits supported integration paths.
- AUD-008: global raw-string model catalog can merge unrelated providers.
- AUD-009: ID-less response fingerprint is not a true occurrence identity (strongly supported).

AUD-008 or AUD-009 becomes release-blocking if the P1 endpoint/identity repair depends on the same canonicalization path and leaves materially false graph joins.

## Known limitations that do not independently block PASS

These must remain accurately disclosed and must not be represented as complete evidence:

- portable polling can miss short-lived sockets;
- descendants that outlive the launched root are not continuously sampled by the portable loop;
- Gemini exact tool before/after pairing can be unavailable when the provider exposes no stable call ID;
- Antigravity child linkage depends on a live-verified implementation wire and intentionally abstains on mismatch;
- conversation preview is UI-bounded while archived raw evidence remains available.

## Current blocker list

1. `AUD-001` — P0 — independent root conversations merge.
2. `AUD-002` — P1 — local-runtime request identity not endpoint scoped.
3. `AUD-003` — P1 — gateway request/deployment identity not endpoint scoped.
4. `AUD-004` — P1 — OpenCode generic/session agent split.
5. `AUD-005` — P1 — Antigravity Stop archive fabricates provider-root provenance.
6. `AUD-006` — P1 — Antigravity tool/conversation identity split.
7. `SUS-001` — suspected P1 — real Antigravity historical-turn loss must be reproduced or dismissed.
8. Final assembled candidate has not yet rerun the combined provider + dashboard + cross-platform release matrix.

## Rule for changing to PASS

Do not change `V0.8.3_RELEASE_GATE` to PASS because PR #25 is green, because individual fix PRs are green, or because the existing test suite is green.

Change it only after all mandatory conditions above are verified on the same intended v0.8.3 release-candidate SHA.
