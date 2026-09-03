# Provider Capability Matrix (0.7.5)

This document records the evidence contract for the 0.7.5 capability probe. It is an
internal implementation note, not a release-support claim.

## Scope

The probe is offline. It reads only caller-supplied existing JSON/JSONL artifacts and
repository source used for the narrow Codex local-decryptor marker audit. It performs no
network capture, endpoint rewriting, TLS interception, decryption, or provider login.

The machine-readable inventory and matrix are emitted by:

```bash
python scripts/probe_provider_capability.py --inventory-only
python scripts/probe_provider_capability.py
```

A concrete artifact is attached to exactly one inventory combination:

```bash
python scripts/probe_provider_capability.py \
  --artifact codex-cli:subscription=tests/fixtures/codex_multi_agent/rollout-main.jsonl
```

When a client has multiple auth modes or surfaces, the selector must name the ambiguous
part explicitly. A missing artifact never deletes the row: every required field remains
in the matrix as `not_observed` with a reason.

## Required inventory

Tier A is release-blocking and contains these clients:

- Codex CLI
- Claude Code
- Antigravity
- Cursor Agent
- OpenCode
- Ollama

Every combination defined by the inventory probes at least: `system`, `prompt`,
`messages`, `tool_definitions`, `tool_arguments`, `tool_results`, `assistant_output`,
`reasoning`, and `usage`.

Tier B is environment-dependent and currently covers Cursor autocomplete/Tab plus local
LM Studio, llama.cpp, and vLLM surfaces. Untested Tier B rows remain explicit rather than
being silently omitted.

## Evidence boundaries

Conversation completeness remains owned by `agent_topology.py` and is not changed by
this stage. Field-level availability is defined separately in
`evidence_availability.py`. Therefore this is valid:

```text
conversation_completeness = provider_transcript
reasoning_availability    = opaque_encrypted
```

A single unavailable or encrypted field must never downgrade an otherwise archived
provider transcript.

`available` and `complete_from_surface` have fixed precedence:

- `available`: content is readable, but the probe cannot prove the full surface value was
  preserved.
- `complete_from_surface`: the surface observation boundary is known and the complete
  value supplied by that surface was preserved.
- If both appear applicable, `complete_from_surface` wins. They are never emitted
  simultaneously for one field observation.

`complete_from_surface` means complete from the observed integration surface. It does
not claim visibility into hidden model/provider state.

## Codex encrypted reasoning

The checked-in Codex rollout fixture contains a reasoning item with
`encrypted_content` beginning with the Fernet-shaped `gAAAAA` prefix. That is direct
evidence only that an opaque encrypted payload was observed.

The repository source audit looks for a small set of Codex-local decryptor markers. If
none are observed, the matrix may state:

```text
availability   = opaque_encrypted
decryptability = no_local_decryptor_observed
```

This is an absence observation. It must never be upgraded to `server-side-only`, or to
`provider_documented_unavailable`, without provider documentation or direct verifiable
evidence.

## Output semantics

Each matrix row records client, tested client version when directly present in the
artifact, provider, auth mode, surface, transport mode, field, availability,
decryptability, evidence source, evidence strength, tier, and notes.

The probe stores paths and classifications, not copied prompt/tool/reasoning content.
This stage is capability discovery only; it does not add a second full-fidelity storage
or conversation-ingestion path.
