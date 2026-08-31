# ExecWeave v0.8.3 System-Wide Provider / Dashboard Audit

Status: **AUDIT COMPLETE ENOUGH TO BLOCK RELEASE; REMEDIATION NOT DONE**

Audit branch: `audit/0.8.3-system-wide-provider-dashboard`

Audit baseline: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`

Related implementation lines are intentionally separate from this audit:

- PR #25: `release/0.8.3-graph-ergonomics` at `8362e74acd91d703991efd8cac2f0826c86cad3a`.
- stacked PR #27: `fix/0.8.3-pr25-premerge-hardening` at validated head `c7d338ca95839e1fd30829c9208fc9d1eda62137`.

# V0.8.3_RELEASE_GATE = FAIL

`PR25_HARDENING_STACK_GATE = PASS`, but `PR25_BRANCH_PREMERGE_GATE = BLOCKED` until PR #27 is explicitly merged into the PR #25 branch and the resulting new PR #25 head is revalidated. This audit did not perform that merge.

## Executive summary

The release risk is not one Antigravity `/root` rendering bug. The audit found a broader identity-domain problem spanning conversation reconstruction, provider session identity, inference endpoint identity, and Antigravity topology provenance.

Current inventory:

- 1 confirmed P0
- 5 confirmed P1
- 2 confirmed P2
- 1 strongly-supported P2
- 1 suspected P1 requiring sanitized real-provider reproduction
- 5 known limitations that are not independently release-blocking

The P0/P1 release blockers are:

1. `AUD-001` — independent root sessions can merge into one synthesized provider-root conversation.
2. `AUD-002` — local model runtime request identity is not endpoint scoped.
3. `AUD-003` — inference gateway request/deployment identity is not endpoint scoped.
4. `AUD-004` — one OpenCode session can materialize generic and session-scoped agent identities.
5. `AUD-005` — Antigravity transcript archival fabricates provider-root provenance from conversation identity alone.
6. `AUD-006` — Antigravity tool evidence and conversation evidence use incompatible agent identities even when they share an exact `conversationId`.
7. `SUS-001` — real Antigravity historical-turn loss remains unresolved until reproduced or dismissed with sanitized provider evidence.

The detailed source-of-truth is `bug-inventory.json`; `bug-inventory.md` is the human-readable view, `release-gate.md` defines the conditions required before PASS, and `remediation-plan.md` turns the confirmed findings into reviewable implementation batches.

## Highest-severity finding: cross-session conversation merge

`AUD-001` is P0 because it can combine content from two independent provider sessions into one dashboard conversation.

The repository already contains a direct OpenCode characterization in `tests/test_conversation_identity_merge.py::test_two_same_provider_root_sessions_share_the_synthesized_root_thread`: two distinct OpenCode session agents (`ses_one`, `ses_two`) are projected into one `opencode:root` thread containing both `ANSWER ONE` and `ANSWER TWO`.

PR #26 now independently reproduces the same mechanism with two distinct Antigravity conversation-scoped graph agents. They collapse into one synthesized `antigravity:root` conversation containing both root answers. That establishes the defect as a conversation-identity contract problem, not an OpenCode-specific special case.

Root cause is the combination of two choices:

- `conversation_preview._agent_identity()` synthesizes `<provider>:root` for root-shaped observations without a provider-native thread;
- `_conversation_records_core._conversation_identity_keys()` can then use that ExecWeave-derived thread together with `/root` scope as positive merge evidence.

Required remediation invariant:

> Independent provider-native execution/session identities stay separate unless positive provider evidence proves they are the same thread. An ExecWeave-derived presentation thread is not positive provider identity.

## Endpoint identity domain defects

`AUD-002` and `AUD-003` show the same design error in two inference surfaces.

Local runtimes (`Ollama`, `llama.cpp`, `vLLM`, `LM Studio`) correctly include endpoint identity in the runtime node, but construct request IDs from runtime name plus native request ID. Two independent endpoints can therefore emit the same native request ID and collapse into one `inference_request` graph node.

Inference gateways (`LiteLLM`, `OpenRouter`, generic gateway path) likewise include endpoint identity in the gateway node while request/deployment IDs omit it. PR #26 separately characterizes both the LiteLLM request collision and a deployment-ID collision across two endpoints. A native request or deployment identifier is authoritative only inside the endpoint identity domain that emitted it.

The OpenRouter response/generation reconciliation path must therefore be changed with the same endpoint-scoping helper rather than fixed independently.

## OpenCode identity split

`AUD-004` is confirmed with one plugin payload.

The semantic adapter uses generic `agent:OpenCode`; the full-fidelity conversation path uses `agent:opencode:session:<sessionID>`. The strengthened PR #26 characterization also proves that full-fidelity provider metadata itself can use the generic agent in the same processing cycle while chat content is session-scoped.

One logical provider session can therefore split model/tool/metadata/conversation evidence across different graph roots.

The remediation must preserve two properties simultaneously:

- one logical OpenCode session -> one canonical graph agent across semantic, metadata, full-fidelity, agent-trace, model and tool evidence;
- two independent OpenCode sessions -> two distinct graph agents/conversations.

## Antigravity identity/topology cluster

The original real-world symptom remains useful, but the static and behavioral audit found two directly reproducible upstream correctness defects that should be fixed before reasoning about layout.

### AUD-005 — fabricated root provenance

`antigravity_conversation_archive_events` validates transcript location and conversation ownership, then unconditionally applies `root_topology()`. The default evidence value is `provider_session_root`.

A validated transcript proves that a transcript belongs to a conversation. It does **not** prove that the conversation is the root of the provider execution. Child-shaped conversation evidence can therefore acquire stronger root provenance than the provider actually supplied.

The existing topology model already supports the right invariant: positive child evidence uses disjoint attributes and can remain authoritative regardless of event order. The fix should remove the fabricated archive root claim rather than infer a new hierarchy.

### AUD-006 — split tool/conversation agent identity

Both current Antigravity PostToolUse paths are affected:

- the exact `toolCall` path in `antigravity_adapter_base`;
- the 2.0/no-tool-identity fallback path in `antigravity_adapter`.

Both can carry an exact `conversationId` while sourcing agent evidence from generic `agent:Antigravity`. Stop transcript archive for the same ID uses `agent:antigravity:conversation:<conversationId>`.

Graph accumulation is ID-based, so these do not become one logical agent automatically. Tool activity can therefore appear disconnected from the conversation that produced it.

Importantly, validated Antigravity child linkage already uses `agent:antigravity:conversation:<childId>`. The remediation therefore does not require an ID migration: it should promote one shared conversation-agent helper and replace the child linkage's legacy bare `agent_path` claim with evidence-scoped topology while preserving conservative abstention on invalid/torn implementation wires.

### SUS-001 — historical-turn loss

The user-supplied real Antigravity run showed older turns disappearing after later activity. This remains `SUSPECTED`, not promoted to confirmed, because the audit still lacks a sanitized real transcript fixture reproducing the loss through archive -> graph -> conversation projection -> Chromium.

The required three-round reproduction is documented in `release-gate.md` and `remediation-plan.md`. A synthetic parser fixture is useful coverage but is not sufficient to close this real-provider report.

## P2 / coverage findings

`AUD-007` — the workflow named Provider Capability Stage Integrity does not inventory every shipped provider/gateway path. A green gate therefore does not mean every supported integration was covered.

`AUD-008` — several API/gateway surfaces use `model:catalog:<raw model string>`, so unrelated providers can canonicalize to the same model node solely because their labels match.

`AUD-009` — strongly supported: deterministic fallback IDs for responses with no native request ID fingerprint response fields rather than an observation occurrence. Two independent identical observations can therefore receive the same synthesized request ID.

P2 findings do not automatically block release once all P0/P1 items are fixed, but they must be fixed or explicitly accepted/tracked before changing the release gate to PASS. The occurrence-identity part of AUD-009 should be evaluated with AUD-002/AUD-003 because they share the inference identity contract.

## Provider surface audited

The provider matrix was built from source rather than from documentation alone. It includes:

- OpenAI Codex
- Claude Code
- Google Antigravity
- OpenCode
- Cursor
- Gemini CLI / legacy compatibility
- Anthropic API
- OpenAI-compatible API paths
- OpenRouter
- LiteLLM / generic inference gateway
- Ollama
- llama.cpp
- vLLM
- LM Studio
- shared provider/model/deployment identity helpers discovered behind those integrations

See `provider-matrix.md` for identity, topology, conversation and tooling observations per surface.

## Dashboard audit conclusions

Several initially suspicious dashboard behaviors were investigated and dismissed rather than promoted to bugs:

- shipped standalone `viewer.html` uses the shared dashboard renderer path;
- finished transition is not the old `/final` + `document.write()` replacement path;
- conversation fold persistence has real Chromium E2E coverage;
- Cursor has a provider-specific subagent/delegation path;
- `collaborationspawn_agent` is a provider-native label and should not be rewritten merely for display.

PR #27 closes the eight PR #25 pre-merge hardening findings (PM-001 through PM-008) on top of the PR #25 branch and is fully green at `c7d338ca95839e1fd30829c9208fc9d1eda62137`, including real Chromium. That proves the hardening stack, **not** the unchanged PR #25 branch itself. PR #27 must first be merged into PR #25 after explicit authorization, and the resulting exact PR #25 head must then be revalidated before PR #25 can be considered merge-ready for `main`.

Even after that, all provider fixes plus the dashboard work must be rerun on one assembled release-candidate SHA before v0.8.3 can pass.

See `dashboard-matrix.md` for the checked behaviors and remaining final-candidate coverage requirements.

## Runtime / OS findings

The audit keeps semantic/provider evidence separate from causal OS evidence.

The following are recorded as known limitations rather than correctness bugs:

- portable polling can miss short-lived sockets;
- descendants that outlive the launched root are not continuously followed after root exit;
- Gemini cannot provide exact before/after pairing when the provider exposes no stable tool-call ID;
- Antigravity child linkage deliberately abstains when its live-verified implementation wire does not validate;
- conversation preview is UI-bounded while archived raw evidence remains available.

These limitations must remain accurately disclosed and must not be represented as complete capture.

## Characterization coverage added by this audit

`tests/test_v083_system_audit_characterization.py` records current broken behavior without modifying production code:

- `AUD-001` Antigravity two-root cross-session conversation merge, complementing the existing OpenCode characterization;
- `AUD-002` vLLM endpoint request-ID collision;
- `AUD-003` LiteLLM endpoint request-ID collision;
- `AUD-003` LiteLLM deployment-ID collision across endpoints;
- `AUD-004` OpenCode generic/session agent split, including generic full-fidelity metadata versus session-scoped chat content;
- `AUD-005` Antigravity fabricated root provenance;
- `AUD-006` Antigravity tool/conversation identity split on both the exact `toolCall` and fallback PostToolUse paths.

The tests intentionally assert the current defect so the audit branch remains green and the repository's stage-integrity rule against new `skip`/`xfail` markers is respected. Remediation PRs must invert these characterizations into correctness regressions.

The exact audit head `e10c4454fef86379b38f854298c45cc4336c187d` passed:

- CI `33377701731` on Ubuntu/macOS/Windows;
- Viewer Agent Isolation `33377701793`, including real Chromium;
- Provider Capability Stage Integrity `33377701728`;
- Windows Launcher Compatibility `33377701746`.

Green audit CI means the characterizations are reproducible and internally consistent. It does **not** mean the characterized defects are fixed.

## Remediation architecture and ordering

Do not attempt to hide upstream identity defects with layout changes. Correct dependency order is:

`provider evidence -> identity domain -> topology provenance -> conversation ownership -> graph projection -> dashboard projection -> layout/routing`

`remediation-plan.md` reduces the confirmed blockers into focused contracts and branches:

1. R1: P0 conversation identity isolation (`AUD-001`).
2. R2: endpoint/request/deployment identity domain (`AUD-002`, `AUD-003`, relevant `AUD-009`).
3. R3: OpenCode canonical session identity (`AUD-004`).
4. R4: Antigravity topology + conversation-scoped identity (`AUD-005`, `AUD-006`).
5. R5: sanitized real three-round Antigravity reproduction for `SUS-001`.
6. R6: resolve/accept P2 items.
7. assemble all fixes with the PR #25 line and run the complete release-candidate matrix.

Production remediation should start from freshly fetched post-PR25 `main`; do not silently stack all fixes unless a real dependency requires it.

## Branch / release rules

This audit branch is investigation-only:

- do not modify `main` from this PR;
- do not modify or force-push PR #25's branch;
- do not merge from this audit merely because CI is green;
- do not tag;
- do not create a GitHub Release;
- do not publish PyPI;
- no force push.

Changing `V0.8.3_RELEASE_GATE` from FAIL to PASS requires the conditions in `release-gate.md` to be demonstrated on the same intended release-candidate SHA.
