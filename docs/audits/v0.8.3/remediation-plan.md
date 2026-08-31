# ExecWeave v0.8.3 — Remediation Plan

This document turns the confirmed PR #26 findings into reviewable implementation batches. It is a handoff artifact only; PR #26 itself remains audit-only and does not change production behavior.

## Preconditions

Current branch state:

- `main = 1ec0dcb0171f9346f8232a99e857cbd6b3168f08`
- PR #25 branch head = `8362e74acd91d703991efd8cac2f0826c86cad3a`
- stacked PR #27 validated head = `c7d338ca95839e1fd30829c9208fc9d1eda62137`
- `PR25_HARDENING_STACK_GATE = PASS`
- `PR25_BRANCH_PREMERGE_GATE = BLOCKED`
- `V0.8.3_RELEASE_GATE = FAIL`

Do not start production remediation from the stale baseline if PR #25 is about to land. After explicit authorization, merge PR #27 into the PR #25 branch, revalidate the exact new PR #25 head, then merge PR #25 to `main` only after separate authorization. All production remediation branches below should then start from that new `main`.

No force push, version bump, tag, GitHub Release or PyPI publication is part of this plan.

---

## Shared identity rules

The audit shows that the release blockers reduce to three identity contracts rather than six unrelated patches.

1. **Conversation identity:** a synthesized presentation thread such as `<provider>:root` is not positive provider identity and must never merge independent executions by itself.
2. **Inference identity:** a provider-native request/deployment ID is authoritative only inside the endpoint/runtime/gateway scope that emitted it.
3. **Agent identity:** when the provider exposes a stable session/conversation ID, semantic, full-fidelity, conversation and tool/model evidence for that execution must use the same canonical agent node.

A fourth rule applies to topology:

4. **Topology provenance:** a transcript proves conversation ownership/content. Root or child status requires its own positive evidence. Missing parent evidence is not permission to stamp `provider_session_root`.

---

## Batch R1 — P0 conversation identity isolation

Closes: `AUD-001`.

### Current failure

`conversation_preview._agent_identity()` synthesizes `<provider>:root` for root-shaped observations. `_conversation_records_core._conversation_identity_keys()` then treats that derived thread as a positive merge key while using `/root` as the agent scope. Two independent root executions therefore enter the same union-find component.

The behavior is already characterized with OpenCode in `tests/test_conversation_identity_merge.py`. PR #26 now also characterizes the same mechanism using two distinct Antigravity conversation-scoped agent IDs.

### Minimal contract change

- A `THREAD_ID_EXECWEAVE_DERIVED` value must not be a cross-agent positive identity key.
- Prefer provider-native execution identity for `agent_scope`: provider-native session/conversation/thread identity when present, otherwise graph source ID, and only then a derived path fallback.
- `THREAD_ID_PROVIDER_NATIVE` remains positive thread identity.
- The UI may still display `opencode:root`, `antigravity:root`, etc. for a single root; presentation compatibility does not justify merging two roots.
- If several distinct executions legitimately publish the same display thread, publication must disambiguate them without pooling messages.

### Expected files

- `src/execweave/_conversation_records_core.py`
- possibly `src/execweave/conversation_preview.py` only if native execution scope is not already available in the preview
- `tests/test_conversation_identity_merge.py`

### Required regressions

- invert the existing OpenCode two-root characterization: two sessions -> two previews, no cross-message leakage;
- invert the PR #26 Antigravity two-root characterization;
- keep Codex multi-evidence child merge green;
- keep child label/path collision isolation green;
- verify canonical provider-native thread still wins over a synthesized alias for one execution.

### Do not do

- do not merge by label, nickname, `/root` path, provider name, or temporal proximity;
- do not solve this by merely changing the rendered thread label.

---

## Batch R2 — Endpoint-scoped inference identity

Closes: `AUD-002`, `AUD-003`; must resolve the relevant part of `AUD-009` at the same time.

### Current failure

`model_runtime._runtime_entity()` and `inference_gateway._gateway_entity()` include a sanitized endpoint digest, but their request IDs do not. Gateway deployment IDs also omit endpoint scope. `openrouter_generation_to_events()` independently reconstructs the same unscoped request format.

Therefore independent vLLM/LiteLLM/OpenRouter instances can join on a native ID that is only locally unique.

### Minimal contract change

Introduce one endpoint identity helper per abstraction (or a shared helper if that stays simple):

- sanitize endpoint;
- derive a stable endpoint-scope digest;
- build request IDs as `inference-request:<provider-or-gateway>:<endpoint-scope>:<native-id>`;
- build deployment IDs with the same endpoint scope;
- ensure OpenRouter response and generation metadata use the same helper so legitimate reconciliation still works.

For ID-less observations, the fallback must be explicitly an **observation identity**, not represented as provider-native identity. At minimum it must include:

- endpoint scope;
- observed timestamp/record occurrence scope;
- existing stable response fingerprint fields.

Reprocessing the same stored observation may deduplicate; two independent observations must not collapse solely because their response metadata happens to match.

### Expected files

- `src/execweave/model_runtime.py`
- `src/execweave/inference_gateway.py`
- optionally `src/execweave/inference_identity.py` if the shared helper belongs there
- focused runtime/gateway identity tests

### Required regressions

- two vLLM endpoints + same native request ID -> distinct request nodes;
- two LiteLLM endpoints + same native request ID -> distinct request nodes;
- two LiteLLM endpoints + same deployment ID -> distinct deployment nodes;
- same OpenRouter endpoint response + generation ID -> one request node;
- different OpenRouter endpoints + same generation ID -> distinct request nodes;
- two ID-less repeated observations -> distinct occurrences unless they are the same stored observation replayed.

### Do not do

- do not include credentials/query strings in identity scope;
- do not use raw endpoint text without existing sanitization;
- do not break response/generation reconciliation while fixing collisions.

---

## Batch R3 — Canonical OpenCode session agent

Closes: `AUD-004`.

### Current failure

Three OpenCode paths disagree:

- `opencode_adapter._agent()` always returns `agent:OpenCode`;
- `opencode_full_fidelity._agent(payload)` returns `agent:opencode:session:<sessionID>` when available;
- `agent_trace.opencode_session_agent()` also uses the session-scoped identity.

In addition, `opencode_full_fidelity._metadata()` currently calls `_agent()` without the payload, so one full-fidelity call can itself emit generic metadata plus session-scoped conversation content.

### Minimal contract change

Create one lightweight canonical OpenCode identity helper and use it everywhere:

- when `sessionID` is present: `agent:opencode:session:<sessionID>`;
- only when no session identity is exposed: generic `agent:OpenCode` with explicit unscoped semantics;
- preserve provider-native agent label separately from identity;
- preserve `parentID` topology through the existing positive-evidence path.

### Expected files

- new small identity helper or one existing neutral module;
- `src/execweave/opencode_adapter.py`
- `src/execweave/opencode_full_fidelity.py`
- `src/execweave/agent_trace.py`
- OpenCode semantic/full-fidelity/agent-trace tests

### Required regressions

- one `chat.message` payload -> exactly one session agent across model, metadata and conversation evidence;
- tool before/after for the same session uses the same agent as chat evidence;
- two OpenCode sessions remain distinct;
- `parentID` produces the same child identity and still carries provider parent evidence;
- payloads with no `sessionID` remain explicitly unscoped rather than fabricated into a fake session.

---

## Batch R4 — Antigravity canonical conversation agent + topology provenance

Closes: `AUD-005`, `AUD-006`.

### Current failure

Antigravity already has a correct conversation-scoped identity in collaboration/full-fidelity paths: `agent:antigravity:conversation:<conversationId>`. However:

- semantic PostToolUse in both the exact `toolCall` path and 2.0 no-tool-identity fallback sources evidence from generic `agent:Antigravity`;
- Stop transcript archival uses the conversation-scoped ID but unconditionally expands `root_topology()`, stamping `provider_session_root` without root evidence;
- validated child linkage creates the same conversation-scoped child ID but still carries a legacy `agent_path` instead of the newer evidence-scoped topology contract.

### Minimal contract change

Create/reuse one `antigravity_conversation_agent(conversation_id, ...)` helper and use it for every provider observation that has an exact `conversationId`.

- PostToolUse exact path -> source the conversation agent;
- PostToolUse no-tool-identity path -> source the conversation agent;
- Stop transcript archive -> same conversation agent, **without** `root_topology()` unless independent provider evidence proves root status;
- validated child linkage -> replace legacy bare `agent_path` with `subagent_topology(evidence=EVIDENCE_VALIDATED_CHILD_TRANSCRIPT, parent_scope_id=<parent conversation>)` or the equivalent exact evidence constant used by that linkage;
- allow graph merging of later child evidence to make child topology authoritative regardless of event order;
- keep invalid/torn implementation-wire linkage as abstention.

### Expected files

- a small Antigravity identity helper or the existing collaboration identity helper promoted to a neutral module;
- `src/execweave/antigravity_adapter.py`
- `src/execweave/antigravity_adapter_base.py`
- `src/execweave/conversation_archive.py`
- `src/execweave/antigravity_full_fidelity.py`
- optionally `src/execweave/antigravity_full_fidelity_collaboration_base.py` to consume the shared helper
- Antigravity identity/topology/linkage tests

### Required regressions

- PostToolUse exact toolCall + Stop with same conversation ID -> one graph agent;
- PostToolUse fallback + Stop with same conversation ID -> one graph agent;
- child-shaped Stop transcript alone does not contain `root_topology_evidence=provider_session_root`;
- validated parent -> child linkage marks child with positive parent evidence and no legacy-only topology claim;
- child archive arriving before or after linkage yields the same final topology;
- torn/invalid transcript linkage still abstains and never fabricates a parent;
- routing-only recipient addresses remain distinguishable from executed child agents until execution evidence arrives.

### Do not do

- do not infer parentage from conversation ID shape, role label, file path similarity or timing;
- do not convert routing-only addresses into executed agents;
- do not restore the generic `agent:Antigravity` source when exact conversation identity is present.

---

## Batch R5 — Antigravity historical-turn reproduction

Resolves or dismisses: `SUS-001`.

This is intentionally separate from R4. The identity fixes may remove the symptom, but that is not proof of causality.

Required artifact: one sanitized real three-turn Antigravity transcript/hook sequence representative of the reported failure.

Exercise the exact same fixture through:

1. transcript archive;
2. graph materialization;
3. conversation record merge/projection;
4. dashboard projection;
5. Chromium live polling/update behavior.

Assertions:

- rounds 1 and 2 remain present and folded;
- round 3 remains current/open;
- repeated Stop updates do not remove history;
- manually opened historical round stays open across polling until user closes it;
- root/child content remains isolated;
- if no repro after R4, document provider/runtime version and fixture evidence before dismissing SUS-001.

A synthetic fixture may be added for parser coverage, but it is not sufficient to close SUS-001 by itself.

---

## Batch R6 — P2 release-quality cleanup

Items: `AUD-007`, `AUD-008`, remaining `AUD-009`.

Run only after the P0/P1 identity contracts are stable, because those fixes may clarify the correct registry/model/observation namespaces.

- AUD-007: make Provider Capability Stage Integrity inventory every shipped adapter/gateway or explicitly classify exclusions.
- AUD-008: stop globally equating model nodes solely because unrelated providers expose the same raw model string, unless an explicit catalog mapping proves equivalence.
- AUD-009: ensure every ID-less observation identity is occurrence-scoped and labelled as ExecWeave-derived rather than provider-native.

P2 does not automatically block the release once every P0/P1 is green, but each item must be fixed or explicitly accepted/tracked before `V0.8.3_RELEASE_GATE` can become PASS.

---

## Recommended branch order after PR #25 lands

Use separate focused branches/PRs, all created from freshly fetched `main`:

1. `fix/0.8.3-conversation-identity` — R1 / AUD-001
2. `fix/0.8.3-inference-endpoint-identity` — R2 / AUD-002, AUD-003, relevant AUD-009
3. `fix/0.8.3-opencode-agent-identity` — R3 / AUD-004
4. `fix/0.8.3-antigravity-agent-topology` — R4 / AUD-005, AUD-006
5. real-fixture characterization branch if SUS-001 evidence is large enough to review separately
6. P2 cleanup only after the P0/P1 branches establish the final identity contracts

Do not stack these branches on one another unless a true dependency requires it. Parallel independent PRs reduce conflict and let each identity contract be reviewed in isolation.

Before every write: fetch latest `main` and the target branch, verify the expected parent SHA, and use non-force updates.

---

## Final release-candidate gate

Individual green PRs are insufficient. After all mandatory fixes land, assemble one intended v0.8.3 candidate SHA and rerun:

- focused identity/conversation/provider regressions;
- full pytest + Ruff;
- real Chromium dashboard E2E;
- Live / Finished / standalone viewer parity;
- manual / Fit / Follow-latest polling behavior;
- multi-agent 1/2/5/10 topology cases;
- small/medium/100–300+ graph stress;
- Linux/macOS/Windows CI;
- provider-capability/stage-integrity;
- package/wheel/launcher workflows required by changed paths.

Only that assembled candidate can change `V0.8.3_RELEASE_GATE` from FAIL to PASS.
