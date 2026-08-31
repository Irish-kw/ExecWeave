# ExecWeave v0.8.3 Bug Inventory

Baseline: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`.

Current release gate: **FAIL**.

## Summary

| ID | Severity | Status | Area | Provider | Release blocker |
|---|---|---|---|---|---|
| AUD-001 | P0 | CONFIRMED | conversation identity | system-wide; reproduced with OpenCode + Antigravity | yes |
| AUD-002 | P1 | CONFIRMED | model/runtime identity | Ollama / llama.cpp / vLLM / LM Studio | yes |
| AUD-003 | P1 | CONFIRMED | gateway identity | LiteLLM / OpenRouter | yes |
| AUD-004 | P1 | CONFIRMED | provider identity | OpenCode | yes |
| AUD-005 | P1 | CONFIRMED | topology provenance | Antigravity | yes |
| AUD-006 | P1 | CONFIRMED | provider identity / tool attribution | Antigravity | yes |
| AUD-007 | P2 | CONFIRMED | release-test coverage | multiple | no |
| AUD-008 | P2 | CONFIRMED | model canonicalization | Anthropic / OpenAI-compatible / gateways | no |
| AUD-009 | P2 | STRONGLY SUPPORTED | inference occurrence identity | API/gateway/local runtimes | no |
| SUS-001 | P1 | SUSPECTED | conversation history | Antigravity | yes until reproduced/dismissed |

## AUD-001 — P0 — Independent root sessions merge into one synthesized provider-root conversation

The defect now has two independent provider characterizations.

`tests/test_conversation_identity_merge.py::test_two_same_provider_root_sessions_share_the_synthesized_root_thread` creates `agent:opencode:session:ses_one` and `agent:opencode:session:ses_two`, then asserts that conversation reconstruction returns one preview with `thread_id == "opencode:root"` containing both `ANSWER ONE` and `ANSWER TWO`.

PR #26 additionally constructs two distinct Antigravity conversation-scoped agents and demonstrates that they collapse into one `antigravity:root` preview containing both root answers. This rules out an OpenCode-only explanation.

This is not a harmless label collision. It is content from two independent execution identities being combined into one conversation view. The v0.8.3 audit classifies it as **P0 CONFIRMED** because cross-session mixing is evidence corruption and can become a cross-agent/private-context leak.

Root cause: `conversation_preview._agent_identity()` synthesizes `<provider>:root` for a root without a provider-native thread. `_conversation_records_core._conversation_identity_keys()` can then treat that ExecWeave-derived thread together with `/root` scope as positive merge identity.

Required remediation contract: independent provider execution/session IDs stay independent unless positive provider evidence proves equivalence. `THREAD_ID_EXECWEAVE_DERIVED` is a presentation identity, not cross-agent positive evidence. Existing OpenCode and Antigravity characterizations must be inverted after the fix while Codex positive-evidence multi-source merging stays green.

## AUD-002 — P1 — Local model-runtime request IDs are not endpoint scoped

`model_runtime._runtime_entity()` correctly includes a digest of the sanitized endpoint. `_inference_entities()` then creates `inference-request:<runtime>:<request_native_id>` with no endpoint digest.

Two vLLM instances at different endpoints that both return `req-1` therefore create two runtime nodes and one shared request node. GraphAccumulator is ID-keyed, so this becomes a false graph join. The same identity construction is shared by Ollama, llama.cpp and LM Studio runtime response paths.

PR #26 directly characterizes the collision with two vLLM endpoints and one native request ID.

Required remediation contract: endpoint is part of the request identity domain. A native request ID is authoritative only inside that endpoint/runtime namespace.

## AUD-003 — P1 — Gateway request/deployment IDs are not endpoint scoped

`inference_gateway._gateway_entity()` includes endpoint digest, while request identity is `inference-request:<gateway_name>:<native_id>` and deployment identity is `inference-deployment:<gateway>:<hash(deployment)>`.

Separate LiteLLM proxies or OpenRouter-compatible gateway endpoints can therefore collide if native IDs/deployment labels match. PR #26 now characterizes both a LiteLLM request-ID collision and a distinct deployment-ID collision across two endpoints.

This is especially dangerous because the rendered graph appears to prove that two gateways served/routed the same request or deployment when they did not.

Required remediation contract: sanitized gateway endpoint (or equivalent stable instance scope) participates in request/deployment identity and in every reconciliation path, including OpenRouter response/generation lookup. Same-endpoint reconciliation must remain intact while cross-endpoint joins disappear.

## AUD-004 — P1 — OpenCode emits generic and session-scoped agent identities for one session

`opencode_adapter._agent()` always returns `agent:OpenCode`. `opencode_full_fidelity._agent(payload)` and `agent_trace.opencode_session_agent(session_id)` use `agent:opencode:session:<sessionID>` when the provider exposed the session.

The strengthened PR #26 characterization also proves that `opencode_full_fidelity._metadata()` can source generic `agent:OpenCode` while chat content from the same payload is session-scoped. One processing cycle can therefore split semantic model evidence, provider metadata and conversation evidence across different graph roots.

Required remediation contract: a single canonical OpenCode agent identity helper must be used by semantic, full-fidelity, metadata, agent-trace, model, tool and conversation paths. Session ID present means session-scoped identity; generic identity is reserved for genuinely unscoped evidence. Two independent sessions must remain distinct.

## AUD-005 — P1 — Antigravity Stop archives fabricate provider-root provenance

`antigravity_conversation_archive_events()` validates that `transcriptPath` has the expected brain directory layout for `conversationId`; it does not prove that the conversation is a root. Nevertheless the source agent unconditionally receives `root_topology()` with default evidence `provider_session_root`.

This matters because the same conversation may be a child discovered through a parent's `invoke_subagent`. If linkage abstains because the implementation wire changed or is torn, the child Stop transcript now carries an affirmative root claim that the provider never supplied.

Required remediation contract: transcript/conversation identity must be separable from topology. Root provenance requires a positive root fact; no-parent-observed is not the same evidence as provider-reported-root. Validated child evidence must remain authoritative regardless of event order.

## AUD-006 — P1 — Antigravity semantic and conversation evidence disagree on agent identity

Both PostToolUse paths are confirmed affected:

- the exact `toolCall` path in `antigravity_adapter_base` emits source `agent:Antigravity`;
- the no-tool-identity fallback in `antigravity_adapter` also emits source `agent:Antigravity`.

Both payload shapes already carry exact `conversationId`. Stop/archive evidence for that same exact ID uses `agent:antigravity:conversation:<conversationId>`.

That produces two agent nodes for one logical conversation and can split tool evidence away from the conversation panel. In multi-agent runs it also gives the generic node ownership over observations originating from different child conversations.

Validated Antigravity child linkage already uses `agent:antigravity:conversation:<childId>`, so remediation does not require a new ID scheme. Required contract: every evidence producer with exact provider conversation ID uses one canonical conversation-agent identity. Child linkage should attach evidence-scoped topology instead of relying on a legacy bare `agent_path`, while invalid/torn linkage continues to abstain.

## AUD-007 — P2 — Provider Capability Stage Integrity does not inventory the shipped provider surface

`REQUIRED_CAPABILITY_INVENTORY` and `docs/internal/provider-capability-matrix.md` cover the historical CLI/runtime set but omit supported paths such as Antigravity, OpenRouter, LiteLLM, standalone Anthropic API and generic OpenAI-compatible endpoints.

The workflow runs on every PR and is named as an integrity gate, but green status cannot detect a capability regression in those omitted paths.

Required remediation contract: one authoritative supported-provider registry, or an explicit audited allowlist that forces every adapter/gateway/runtime into `required`, `optional`, or `intentionally ungated` status.

## AUD-008 — P2 — Model nodes can merge unrelated providers by raw model label alone

Anthropic API, OpenAI-compatible API and inference gateway helpers all create `model:catalog:<model>`. There is no provider/endpoint namespace or explicit catalog equivalence proof.

Two unrelated providers that publish the same string therefore share a graph model node. A common label is not sufficient evidence that two provider-facing model identities are globally equivalent.

Required remediation contract: provider-qualified model identity by default; optional cross-provider catalog canonicalization only through explicit mapping/evidence.

## AUD-009 — P2 — ID-less inference fallback fingerprint is not an occurrence identity

When a provider response has no request ID, multiple adapters hash a subset of response fields such as model, created/time fields and usage. Recording the same values twice deterministically yields the same graph request ID.

The code defect is direct; the production frequency is provider-dependent, so this is **STRONGLY SUPPORTED** rather than promoted to a release-blocking confirmed bug without a representative provider fixture.

Because AUD-002/AUD-003 already require endpoint-scoped inference identity changes, the relevant occurrence-identity portion of AUD-009 should be fixed or explicitly resolved in the same R2 remediation batch rather than left as a second incompatible fallback scheme.

## SUS-001 — P1 — Antigravity historical turns disappear in a real run

A real Antigravity observation showed earlier rounds disappearing instead of remaining as folded history. This audit has not yet reproduced that loss from a sanitized Antigravity transcript fixture, so it remains **SUSPECTED**, not a confirmed root cause claim.

The required regression is a real/sanitized three-turn provider transcript/hook sequence exercised through archive -> graph -> conversation records -> dashboard -> Chromium with repeated Stop/poll updates. Rounds 1/2 must remain present/folded, round 3 open, manual historical fold state sticky, and root/child content isolated.

A synthetic parser fixture may supplement coverage but cannot close SUS-001 by itself.

# Known limitations

### KL-001 — Portable network polling can miss short-lived sockets

`RuntimeCollector` samples `psutil` connections at intervals. A connection that opens and closes between samples cannot be observed. This must be disclosed as a polling limitation rather than represented as complete network provenance.

### KL-002 — Descendants that outlive the root are not continuously followed

The collector loop ends when the launched root process exits. A still-running child may remain known but is no longer sampled afterward. This matches the architectural limitation raised in external feedback and should not be confused with provider semantic causality.

### KL-003 — Gemini exact tool-call pairing can be unavailable

Current Gemini hook evidence does not guarantee a unique call ID for BeforeTool/AfterTool. ExecWeave's conservative non-linkage is correct. **KNOWN LIMITATION, not a bug.**

### KL-004 — Antigravity child linkage uses an implementation wire

`validated_subagent_links()` explicitly says its transcript ordering/layout is a live-verified implementation wire, not a public stable schema. Abstention on mismatch is intentional. The bug is when downstream projection turns that absence into stronger provenance than observed.

### KL-005 — Conversation preview is capped at 80 messages

The conversation-record projection retains a UI preview of first 10 + last 70 when more than 80 messages exist. Archived raw content remains available. This is a UI completeness limit and must be labeled, not mistaken for raw-evidence deletion.

# False positives investigated and dismissed

- **viewer.html separate renderer:** dismissed. `viewer_projection.py` routes static output through `dashboard_shell` and the shared live dashboard shell.
- **finished page still uses `/final` + `document.write()`:** dismissed on emitted `LIVE_HTML`; `live_view.py` patches the legacy path out.
- **historical fold state has no Chromium test:** dismissed. `tests/test_dashboard_round_fold_state_e2e.py` exercises open/close persistence, polling, payload changes and agent switching.
- **Cursor lacks subagent support:** dismissed. Subagent lifecycle is handled in `cursor_delegation_base.py` using exact provider `subagent_id`.
- **timestamp-prefix agent labels are current behavior:** dismissed. `tests/test_agent_node_labels.py` guards namespaced path/nickname labeling.
- **`collaborationspawn_agent` needs a synthetic separator:** dismissed. It is provider-native observed naming; changing it would fabricate presentation data not observed from the provider.

# Remediation reference

See `remediation-plan.md` for the R1–R6 implementation batches, required regressions, expected files, and explicit anti-patterns. PR #26 remains audit-only; green audit CI proves these characterizations are reproducible, not that the defects are fixed.
