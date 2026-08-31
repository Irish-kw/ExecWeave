# ExecWeave v0.8.3 System-Wide Provider / Dashboard Audit

Status: **AUDIT COMPLETE ENOUGH TO BLOCK RELEASE; REMEDIATION NOT DONE**

Audit branch: `audit/0.8.3-system-wide-provider-dashboard`

Audit baseline: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`

Related implementation line: PR #25 (`release/0.8.3-graph-ergonomics`) is intentionally separate and was not modified by this audit.

# V0.8.3_RELEASE_GATE = FAIL

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

The detailed source-of-truth is `bug-inventory.json`; `bug-inventory.md` is the human-readable view and `release-gate.md` defines the conditions required before PASS.

## Highest-severity finding: cross-session conversation merge

`AUD-001` is P0 because it can combine content from two independent provider sessions into one dashboard conversation.

The repository already contains a direct characterization in `tests/test_conversation_identity_merge.py::test_two_same_provider_root_sessions_share_the_synthesized_root_thread`: two distinct OpenCode session agents (`ses_one`, `ses_two`) are projected into one `opencode:root` thread containing both `ANSWER ONE` and `ANSWER TWO`.

That behavior was previously described as a known limitation. For the v0.8.3 release gate it is treated as a correctness defect: root status and provider label are insufficient evidence that two independent sessions are the same conversation.

Required remediation invariant:

> Independent provider-native execution/session identities stay separate unless positive provider evidence proves they are the same thread.

## Endpoint identity domain defects

`AUD-002` and `AUD-003` show the same design error in two inference surfaces.

Local runtimes (`Ollama`, `llama.cpp`, `vLLM`, `LM Studio`) correctly include endpoint identity in the runtime node, but construct request IDs from runtime name plus native request ID. Two independent endpoints can therefore emit the same native request ID and collapse into one `inference_request` graph node.

Inference gateways (`LiteLLM`, `OpenRouter`, generic gateway path) likewise include endpoint identity in the gateway node while request/deployment IDs omit it. A native ID is authoritative only inside the endpoint identity domain that emitted it.

Audit characterization tests reproduce both collisions directly.

## OpenCode identity split

`AUD-004` is confirmed with one plugin payload.

The semantic adapter uses generic `agent:OpenCode`; the full-fidelity/conversation path uses `agent:opencode:session:<sessionID>`. One logical provider session can therefore appear as two root agents, splitting model/tool evidence from conversation evidence.

The remediation must preserve two properties simultaneously:

- one logical OpenCode session -> one canonical graph agent;
- two independent OpenCode sessions -> two distinct graph agents/conversations.

## Antigravity identity/topology cluster

The original real-world symptom remains useful, but the static audit found two directly reproducible upstream correctness defects that should be fixed before reasoning about layout.

### AUD-005 — fabricated root provenance

`antigravity_conversation_archive_events` validates transcript location and conversation ownership, then unconditionally applies `root_topology()`. The default evidence value is `provider_session_root`.

A validated transcript proves that a transcript belongs to a conversation. It does **not** prove that the conversation is the root of the provider execution. Child-shaped conversation evidence can therefore acquire stronger root provenance than the provider actually supplied.

### AUD-006 — split tool/conversation agent identity

Current PostToolUse fallback evidence already carries exact `conversationId`, but its source is generic `agent:Antigravity`. The Stop transcript archive for that same exact ID uses `agent:antigravity:conversation:<conversationId>`.

Graph accumulation is ID-based, so these do not become one logical agent automatically. Tool activity can therefore appear disconnected from the conversation that produced it.

### SUS-001 — historical-turn loss

The user-supplied real Antigravity run showed older turns disappearing after later activity. This remains `SUSPECTED`, not promoted to confirmed, because the audit still lacks a sanitized real transcript fixture reproducing the loss through archive -> graph -> conversation projection -> Chromium.

The required three-round reproduction is documented in `release-gate.md`.

## P2 / coverage findings

`AUD-007` — the workflow named Provider Capability Stage Integrity does not inventory every shipped provider/gateway path. A green gate therefore does not mean every supported integration was covered.

`AUD-008` — several API/gateway surfaces use `model:catalog:<raw model string>`, so unrelated providers can canonicalize to the same model node solely because their labels match.

`AUD-009` — strongly supported: deterministic fallback IDs for responses with no native request ID fingerprint response fields rather than an observation occurrence. Two independent identical observations can therefore receive the same synthesized request ID.

P2 findings do not automatically block release once all P0/P1 items are fixed, but they must be fixed or explicitly accepted/tracked before changing the release gate to PASS.

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

PR #25 separately implements graph ergonomics/routing work and reports real Chromium coverage for adaptive sizing, reversible focus, lane/component placement and routing determinism. Those branch results are useful evidence but **do not** make the v0.8.3 release gate pass. All provider fixes plus PR #25 behavior must be rerun on one assembled release-candidate SHA.

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

- `AUD-002` vLLM endpoint request-ID collision;
- `AUD-003` LiteLLM endpoint request-ID collision;
- `AUD-004` OpenCode generic/session agent split;
- `AUD-005` Antigravity fabricated root provenance;
- `AUD-006` Antigravity tool/conversation identity split.

The tests intentionally assert the current defect so the audit branch remains green and the repository's stage-integrity rule against new `skip`/`xfail` markers is respected. Remediation PRs must invert these characterizations into correctness regressions.

`AUD-001` is already directly characterized by the existing root-session merge test in `tests/test_conversation_identity_merge.py`.

## Release ordering

Do not attempt to hide upstream identity defects with layout changes. Correct remediation order is:

`provider evidence -> identity domain -> topology provenance -> conversation ownership -> graph projection -> dashboard projection -> layout/routing`

Recommended fix batches:

1. P0 conversation identity isolation (`AUD-001`).
2. endpoint/request/deployment identity domain (`AUD-002`, `AUD-003`, and evaluate `AUD-009`).
3. OpenCode canonical session identity (`AUD-004`).
4. Antigravity topology + conversation-scoped identity (`AUD-005`, `AUD-006`).
5. sanitized three-round Antigravity reproduction for `SUS-001`.
6. resolve/accept P2 items.
7. assemble with PR #25 and run the complete release-candidate matrix.

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
