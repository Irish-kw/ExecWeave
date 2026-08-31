# ExecWeave v0.8.3 Provider Audit Matrix

Audit baseline: `main@1ec0dcb0171f9346f8232a99e857cbd6b3168f08`.

Status vocabulary: **CONFIRMED** = reproduced or directly characterized by current code/tests; **STRONGLY SUPPORTED** = code path establishes the risk but a provider/runtime reproduction is unavailable; **KNOWN LIMITATION** = provider/platform surface does not expose enough evidence; **NOT A BUG** = investigated and dismissed.

| Provider / integration | Collection path | Conversation support | Multi-agent support | Native identity | Parent-child evidence | Tool visibility | Model visibility | Transcript support | Known schema risk | Confirmed bug count | Confidence |
|---|---|---|---|---|---|---|---|---|---|---:|---|
| Claude Code | official hooks, `claude_adapter.py`, `claude_full_fidelity.py`, `conversation_archive.py` | yes | yes | session ID + subagent ID | exact lifecycle hook / validated child transcript | name, input/output depending hook | model observation where exposed | main + validated subagent JSONL archived | low/medium; contract is explicit but payload versions can move | 0 | high |
| OpenAI Codex | hooks + rollout trace, `codex_adapter.py`, `codex_rollout_trace*`, archive | yes | yes | session/rollout thread + subagent ID | rollout session meta / provider routing evidence | tool and call semantics from hook/rollout | yes | validated rollout JSONL archived | medium; hook and rollout surfaces differ | 0 | high |
| Google Antigravity | hooks + live-verified brain transcript wire | yes | partial/conservative | conversation ID; generic root identity also exists | exact only when `validated_subagent_links()` succeeds | partial; current PostToolUse can lack tool identity | model name when hook exposes it | validated brain JSONL snapshot | **high**; transcript linkage is observed implementation wire, not stable public schema | 2 | high for code defects; medium for provider wire |
| Cursor Agent | official hooks, delegation/full-fidelity modules | yes | yes | conversation/session/generation + exact `subagent_id` when present | exact `subagentStart`/`subagentStop` | before/after tool, shell, MCP, file hooks | model fields in hook payload | transcript path exposed by provider; ExecWeave evidence varies by hook | medium; official hook contract is current | 0 | high |
| Cursor Tab/autocomplete | capability probe / provider lifecycle | no agent transcript contract | no | request/feature evidence only | n/a | limited | yes where probe exposes | no | medium; distinct surface from Cursor Agent | 0 | medium |
| Gemini CLI | official hooks + `gemini_adapter.py` / full fidelity | yes where transcript/hook content is supplied | root-only in current ExecWeave contract | provider session ID | no provider subagent contract used | before/after tool payloads; no documented unique call ID | yes | session/transcript evidence where supplied | medium | 0 | high; one known limitation |
| OpenCode | plugin hooks + event bus, adapter/full-fidelity/agent trace | yes | yes when parent session ID is published | provider session ID, call ID, parent session ID | exact when `parentID` exists | tool name/input/output/call ID | yes | plugin/event content, no external cache dependency required | medium/high; normalized hook shim and event bus must stay aligned | 2 | high |
| Anthropic API | direct response or caller-supplied exchange | yes for supplied request/response content | no agent topology contract | response/request ID | n/a | tool-use/result blocks visible when supplied | requested + resolved model | caller-supplied exchange / response archive | low | 1 (shared model-catalog namespace) | high |
| OpenAI-compatible endpoint | direct response or caller-supplied exchange | yes for supplied messages/input/response | no agent topology contract | response/request ID + endpoint digest | n/a | tool calls/results visible when supplied | requested + resolved model | caller-supplied exchange / response archive | high by definition: compatibility surface varies | 1 (shared model-catalog namespace) | high |
| OpenRouter | `inference_gateway.py` + full-fidelity gateway content | request/response content where supplied | no agent topology contract | generation/response ID | n/a | response tool structures via OpenAI-compatible content path where supplied | requested/resolved/provider/deployment | gateway response / generation metadata | medium; OpenRouter generation IDs are documented, routing metadata evolves | 1 | high |
| LiteLLM | `inference_gateway.py`, callbacks / gateway content | request/response content where supplied | no agent topology contract | OpenAI-format response ID + gateway metadata | n/a | callback/exchange dependent | requested/resolved/provider/deployment | gateway/callback evidence | medium/high; proxy and SDK surfaces differ | 1 | high |
| Ollama | `model_runtime.py`, auto-specialized local probe | inference response evidence, not agent conversation | no | response fields; often no stable request ID | n/a | native API does not represent agent tool lifecycle | model + load/runtime telemetry | no provider conversation transcript | low for API, polling scope limitation | 1 | high |
| llama.cpp | `model_runtime.py`, OpenAI-compatible local runtime probe | inference response evidence | no | response ID if supplied | n/a | OpenAI-compatible response only | model/runtime telemetry | no agent transcript | medium | 1 | high |
| vLLM | `model_runtime.py`, OpenAI-compatible local runtime probe | inference response evidence | no | response ID if supplied | n/a | OpenAI-compatible response only | model/runtime telemetry | no agent transcript | medium | 1 | high |
| LM Studio | `model_runtime.py`, OpenAI-compatible local runtime probe | inference response evidence | no | response ID if supplied | n/a | OpenAI-compatible response only | model/runtime telemetry | no agent transcript | medium | 1 | high |

## Provider identity notes

### Claude Code

Root semantic identity remains generic (`agent:Claude Code`) while child IDs are session-scoped. Current archive code validates the main transcript filename against `session_id` and validates subagent transcript layout before publishing child topology. No direct cross-agent content leak was found in the inspected Claude path. Multiple independent root sessions in one ExecWeave run still deserve a real-provider regression because the generic-root pattern is shared with the conversation layer.

### Codex

Codex has the strongest provider-native multi-agent evidence in the repository: rollout session metadata, exact child IDs, and existing real multi-agent conversation fixtures. Child/private content isolation and path/nickname labeling already have targeted tests. No new correctness defect was confirmed in this pass.

### Antigravity

Two identity surfaces coexist: generic `agent:Antigravity` semantic observations and conversation-scoped `agent:antigravity:conversation:<conversationId>` archive nodes. In addition, `antigravity_conversation_archive_events()` currently stamps `root_topology()` on every validated Stop transcript even though `conversationId` alone does not establish that the conversation is a provider root. Exact parent-child mapping remains intentionally conservative and depends on a live-verified transcript implementation wire. These are recorded as AUD-005 and AUD-006.

### Cursor

A superficial audit of `cursor_adapter.py` alone would incorrectly report missing subagent support. That is **NOT A BUG**: `cursor_delegation_base.py` handles `subagentStart` and `subagentStop` with exact provider `subagent_id`, and the official hook-contract module explicitly delegates those events. Cursor's current official hook documentation also exposes the corresponding lifecycle events.

### Gemini CLI

Gemini hook evidence exposes session identity and tool before/after payloads but the current official hook contract does not provide a stable unique tool-call ID for pairing. ExecWeave deliberately avoids claiming exact before/after linkage in that case. This is a provider limitation, not an ExecWeave defect.

### OpenCode

This provider has a confirmed split identity. `opencode_adapter.py` attributes semantic model/tool events to generic `agent:OpenCode`, while `opencode_full_fidelity.py` and `agent_trace.py` use `agent:opencode:session:<sessionID>` for conversation/event evidence. The same plugin cycle can therefore materialize both identities. Separately, an existing test demonstrates that two independent OpenCode root sessions are merged into one synthesized `opencode:root` conversation; that test currently characterizes the behavior as a limitation, but the audit classifies the cross-session content merge as a release-blocking P0.

### API / gateway / local runtimes

Direct Anthropic and generic OpenAI-compatible request IDs correctly include an endpoint digest. `inference_gateway.py` and `model_runtime.py` do not: their gateway/runtime node is endpoint-scoped while the child inference-request ID is not. Two independent instances can therefore point at the same graph request node when their native IDs collide. The fallback fingerprint used when no native ID exists is also not a true occurrence identity and can merge repeated identical calls.

## Official-contract notes

- Cursor official hooks were checked against `https://cursor.com/docs/hooks`. `subagentStart`/`subagentStop` are documented contract surfaces.
- Gemini CLI hook behavior was checked against the current official Gemini CLI hooks documentation. The absence of a documented unique tool-call ID is treated as a provider limitation.
- LiteLLM current documentation describes an OpenAI-format response with a response `id`; ExecWeave must still namespace that ID by the particular proxy endpoint because separate LiteLLM instances are independent identity domains.
- OpenRouter documents generation IDs returned in API responses; the endpoint itself remains part of ExecWeave's observation scope and cannot be dropped from graph identity.
- Antigravity transcript record ordering/linkage remains explicitly classified as an observed implementation detail, not a documented contract.
