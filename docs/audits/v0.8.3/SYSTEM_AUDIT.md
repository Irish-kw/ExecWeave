# ExecWeave v0.8.3 System-Wide Provider / Dashboard Audit

Status: **IN PROGRESS — RELEASE BLOCKING**

Audit branch: `audit/0.8.3-system-wide-provider-dashboard`

Start `main`: `1ec0dcb0171f9346f8232a99e857cbd6b3168f08`

Related implementation work: PR #25 (`release/0.8.3-graph-ergonomics`) is intentionally separate and must not be modified by this audit.

## Purpose

This PR is an investigation artifact for the v0.8.3 release gate. It is not a broad product-fix branch. The goal is to find the bug cluster before release rather than discover one provider/dashboard defect per patch release.

Allowed changes here are audit documentation, diagnostic scripts, reproducible fixtures, characterization/regression tests, sanitized provider-contract snapshots, and CI/audit tooling. Production behavior should remain unchanged unless a tiny diagnostic change is strictly necessary to prove a defect; if a production fix becomes necessary, stop and document the blocker instead of silently turning this PR into a feature PR.

## Release gate

`V0.8.3_RELEASE_GATE = FAIL` until this audit is completed and all release-blocking findings have a remediation path and regression coverage.

The current preliminary repository audit already identifies a systemic Antigravity identity/topology failure cluster. These are not yet the complete findings and must not be treated as the final inventory.

## Preliminary release blockers

### Antigravity conversation / topology identity cluster

Current source paths indicate several interacting defects/risks that explain the real multi-agent symptom where one root plus multiple subagents can render as several `/root` nodes while provider role names disappear:

1. Antigravity semantic events can be attributed to a generic `agent:Antigravity` identity even though conversation-scoped identities exist elsewhere.
2. Exact parent-child correlation depends on conservative `validated_subagent_links()` logic and may correctly abstain when provider implementation-wire assumptions are not satisfied.
3. A successfully correlated child currently uses legacy-style `agent_path` representation instead of the shared positive-evidence topology contract.
4. Antigravity conversation archival can attach root topology to a conversation independently of whether that conversation is actually a child.
5. Dashboard display-name precedence can prefer path-like identity over provider-native role/type, turning useful child labels into `/root/...`.

The audit must distinguish code-confirmed defects from runtime-confirmed defects. The supplied real Antigravity observation is evidence, but a finding is only `CONFIRMED` when directly reproduced by the audit; otherwise classify it as `STRONGLY SUPPORTED` or `SUSPECTED`.

### PR #25 independence

PR #25 remains the v0.8.3 graph ergonomics/routing implementation line. This audit branch must not edit, force-push, merge, or absorb that branch. Layout work must not be used to hide identity/topology defects upstream.

Correct remediation ordering is:

`provider evidence -> agent identity -> topology provenance -> conversation ownership -> graph projection -> dashboard projection -> layout/routing`

## Audit scope

The audit covers the full pipeline rather than isolated modules:

`provider raw evidence -> semantic event -> graph node/edge -> conversation projection -> dashboard projection -> rendered UI`

Subsystems:

- provider collection and provider identity
- multi-agent topology
- conversation reconstruction and historical turns
- tool calls and model calls
- process/file/network/runtime evidence
- graph projection, canonicalization, layout and routing
- dashboard interactions
- live polling and finished-run transition
- standalone `viewer.html`
- folding, focus, filtering and search
- replay/export
- Linux/macOS/Windows behavior

## Provider inventory requirement

The final provider list must be built from the code. At minimum inspect:

- OpenAI Codex
- Claude Code
- Google Antigravity
- OpenCode
- Cursor
- Gemini CLI / legacy Gemini compatibility
- Ollama
- OpenRouter
- LiteLLM
- Anthropic API
- OpenAI-compatible endpoints
- llama.cpp
- vLLM
- LM Studio

Any additional provider adapter, gateway, runtime, hook, or compatibility integration discovered in source must be added to the matrix.

## Identity contract to test

For each provider record:

- raw provider session ID
- raw conversation/thread ID
- raw child ID
- graph node ID
- provider-native name
- agent role
- agent path
- parent identity
- ExecWeave-derived identity
- conversation thread ID
- dashboard-visible label

Actively test for duplicate logical agents, collapsed unrelated agents, false roots, missing children, provider-native/synthesized thread duplication, generic-root session merging, role/path precedence errors, routing-only identities shown as executions, fabricated lifecycle, child/root conversation leakage, and multiple independent sessions sharing identity.

Identity merges require positive evidence. Labels alone are never sufficient merge evidence.

## Multi-agent matrix

For providers exposing subagents/multi-agent behavior, characterize where practical:

- 1 agent
- 2 agents
- 5 agents
- 10 agents
- parallel children
- sequential children
- nested children where supported
- identical sibling roles/types
- near-simultaneous siblings
- long role names
- shared tools/files/models
- parent-child messaging
- child stop/completion/failure
- missing/torn transcript
- provider schema mismatch
- repeated delegation operations

Required invariant: every logical agent has exactly one visible identity, child names survive, parent edges are evidence-correct, lifecycle is not fabricated, conversation ownership remains isolated, and shared resources do not collapse agents.

## Conversation contract

At minimum test three rounds:

1. user -> assistant
2. user -> assistant
3. user -> assistant

Expected dashboard state:

- previous round 1 folded
- previous round 2 folded
- current round 3 open

Historical turns must never be deleted by polling or Stop/finalization. Manually opened historical folds must remain open until the user closes them. Agent switching, live updates, finished transition, and standalone `viewer.html` must preserve equivalent history and stable fold state.

## Dashboard behavioral audit

Use real Chromium behavior for Live, Finished and standalone `viewer.html`.

Exercise small (~10), medium (~50), and large (100–300+) graphs with agent-heavy, process-heavy, file-heavy, network-heavy, tool-heavy and mixed workloads.

Record measurable layout baselines where possible:

- edge crossings
- node overlaps
- edge/node intersections
- graph bounding box
- movement between unchanged nodes across polls

Also test long labels, Unicode/Chinese paths, long Windows paths, URLs, IPv6, long tool namespaces, adaptive width determinism, folding at multiple budgets, focus clearing, search/filter combinations, zoom/manual/fit/follow-latest, inspector, replay and export.

## Runtime / OS evidence audit

Audit semantic/provider evidence separately from OS runtime evidence. Classify each finding as one of:

- confirmed bug
- known platform limitation
- provider limitation
- intentional conservative abstention

Pay special attention to portable polling blind windows, short-lived sockets, descendant lifetime, macOS path-only FSEvents attribution, Windows path/case/slash canonicalization, symlinks, duplicated process occurrences, endpoint deduplication, and accidental promotion of semantic evidence into causal OS evidence.

## Finding taxonomy

Every finding must be one of:

- `CONFIRMED` — reproduced directly
- `STRONGLY SUPPORTED` — code path plus evidence strongly implies defect, provider/environment unavailable
- `SUSPECTED` — requires a real provider run
- `KNOWN LIMITATION` — expected architecture/provider/platform limitation
- `NOT A BUG` — investigated and dismissed

Severity:

- P0 — corruption/privacy/cross-agent leak/materially false graph
- P1 — major correctness defect making a common workflow misleading or unusable
- P2 — significant observability/UX defect with workaround
- P3 — minor presentation/polish

Do not inflate severity.

## Required audit artifacts

This directory will contain, before the audit is complete:

- `SYSTEM_AUDIT.md`
- `provider-matrix.md`
- `dashboard-matrix.md`
- `bug-inventory.json`
- `bug-inventory.md`
- `coverage-gaps.md`
- `release-gate.md`

For every confirmed P0/P1 finding, add or propose a behavioral regression that would fail before the remediation. Dashboard behavior should use Chromium; provider wire-format tests should prefer sanitized real evidence when legally/practically possible.

## Audit progress

Initial static review: complete enough to justify opening the audit PR, not complete enough to pass the release gate.

Next audit batches:

1. provider inventory + identity/conversation matrices
2. provider multi-agent/tool/model characterization
3. Chromium Live/Finished/viewer behavioral matrix
4. runtime/cross-platform evidence characterization
5. graph/layout stress metrics
6. final bug inventory + explicit release gate

Do not merge this audit PR. Do not modify `main`. Do not tag/release/publish from this branch.
