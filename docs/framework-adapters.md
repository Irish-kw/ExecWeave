# Framework Adapter SDK

ExecWeave framework adapters are authoritative semantic integrations. They do not
infer agent conversations from process names, ports, or model text. A framework
integration must call the adapter at the framework boundary that actually knows
the logical agent, task, message, model call, or tool call.

## Canonical contract

The public API is in `execweave.framework_adapters`:

- `AdapterContext` owns the run, session, conversation, sidecar, process
  correlation, and content-capture policy.
- `EntityRef` gives agents, tasks, messages, models, tools, model calls, and
  observed content stable run-scoped identities.
- `AgentRecord`, `TaskRecord`, `MessageRecord`, `ModelCallRecord`, and
  `ToolCallRecord` are the typed boundary records.
- `SemanticWriter` appends schema-versioned JSONL records to the configured
  `EXECWEAVE_SEMANTIC_SIDECAR` without embedding prompt or response bodies in
  the sidecar.
- `ContentWriter` reuses ExecWeave's SHA-256 content-addressed store. Content is
  opt-in through `metadata_only`, `content_ref_only`, `prompt_only`, or
  `prompt_and_response`. Hidden reasoning markers are always rejected.
- `FrameworkAdapterRegistry` discovers built-ins and third-party adapters with
  the `execweave.framework_adapters` entry-point group.

Stable IDs are derived only from the framework, run ID, entity kind, and the
framework's native identifier. They do not contain timestamps or message text.
Metadata is recursively stripped of transport credentials such as API keys,
authorization headers, cookies, passwords, and access tokens. Full-fidelity
content, when explicitly enabled, remains outside the JSONL sidecar as a local
content reference; review the run directory before sharing it.

Example:

```python
from execweave.framework_adapters import AdapterContext, CAMELAdapter, ContentCapturePolicy

context = AdapterContext.from_environment(
    "camel",
    capture_mode="prompt_and_response",
)
adapter = CAMELAdapter(context)
worker = adapter.agent_created("worker-1", name="Builder", role="builder")
task = adapter.task_created("task-1", name="Build the example")
adapter.task_assigned(task, worker)
```

## Compatibility matrix

The matrix describes what has actually been checked for this release branch.
"Verified" is narrower than "installed": it means the authoritative API shape
and the adapter output were exercised. It does not promise that a framework's
model provider, credentials, or hidden provider state are observable.

| Framework | Verified version/ref | Agent | Task | Message | Model | Tool | Conversation | Real E2E |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAMEL | `camel-ai 0.2.91a7`; `WorkforceCallback` | callback smoke | callback smoke | callback/stream smoke | wrapper boundary | not exposed by callback | run-scoped IDs | PASS: real Workforce + local Ollama at `127.0.0.1:12345`; 2 parallel tasks, 5 model calls, root `TaskState.DONE` |
| AutoGen | `autogen-agentchat/core 0.7.5`; AgentChat/Core events | event smoke | wrapper-supplied | real message classes | official Ollama client boundary | real tool event classes | run-scoped IDs | PASS: real `RoundRobinGroupChat` + local Ollama; 2 agents, 4 model calls, 5 AgentChat messages, task contract completed |
| MetaGPT | `metagpt 1.0.0`; `Role`/`Action`/`Message` | real object smoke | action/task smoke | real `Message` object | native `OllamaLLM` `/api/chat` boundary | parser/retry API | run-scoped IDs | PASS: real `Role.run` + `ActionNode.fill`; 1 model call/response, 2 messages, structured parse completed without retry |

AutoGen's official documentation separates Core, AgentChat, and Extensions
layers, and identifies agent messages, internal events, model clients, and tool
execution as distinct surfaces. The adapter therefore exposes explicit observe
methods rather than pretending one callback covers every layer. See the
[AutoGen messages guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/messages.html),
[model guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/models.html),
and [agent/runtime guide](https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/framework/agent-and-agent-runtime.html).

CAMEL Workforce officially exposes callback methods for worker and task
lifecycle, logs, and stream chunks. `CAMELAdapter.workforce_callback()` creates
a callback object from the installed CAMEL class, so the adapter does not import
CAMEL when ExecWeave itself is imported. The current CAMEL `LogEvent` surface
does not carry the emitting worker or recipient; those log messages therefore
remain explicitly unrouted, while stream chunks and model/message hooks are
routed when CAMEL exposes the boundary. Missing native message IDs receive a
unique ExecWeave-derived occurrence ID rather than collapsing into `None`. See
the [CAMEL Workforce callback reference](https://docs.camel-ai.org/reference/camel.societies.workforce.workforce_callback).

MetaGPT's roles, messages, actions, and provider calls have changed across
releases. `MetaGPTAdapter` consequently accepts explicit role/task/message/action
and model observations, and exposes parser-failure and retry events instead of
claiming to reconstruct them from stdout. The source framework is documented in
the [MetaGPT repository](https://github.com/FoundationAgents/MetaGPT).

## Live and finished runs

When `execweave live` is used, set `EXECWEAVE_SEMANTIC_SIDECAR` to the live run's
`semantic.jsonl` path before the framework starts. The live dashboard tails the
same semantic stream and the same runtime event stream that are used to produce
the finished `events.semantic.jsonl`, `graph.semantic.json`, and
`viewer.semantic.html` artifacts. Live process references are provisional;
finished merge performs the final exact PID/create-time resolution.

An integration is not complete until it checks parity for:

1. agent/task/message/model/tool node identities;
2. canonical relations and event ordering;
3. content-reference count and SHA-256 values; and
4. unresolved process references and compatibility metadata.

## Evidence and papers

These adapters are implementation integrations, not claims that ExecWeave is a
new multi-agent framework. The framework concepts come from the primary papers:

- Li et al., [CAMEL: Communicative Agents for "Mind" Exploration of Large
  Language Model Society](https://arxiv.org/abs/2303.17760).
- Wu et al., [AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent
  Conversation](https://arxiv.org/abs/2308.08155).
- Hong et al., [MetaGPT: Meta Programming for a Multi-Agent Collaborative
  Framework](https://openreview.net/forum?id=VtmBAGCN7o), ICLR 2024.

The adapter's evidence fields say whether a value is metadata, an explicit
content reference, or a process correlation. They must not be upgraded to
causal claims merely because two events have nearby timestamps.

## Per-agent conversation routing

Framework adapter conversations are indexed per native agent. When a routed
message has both a sender and a recipient, the same content reference is
attached to both agent nodes, preserving the original sender and recipient in
the conversation message. A model request and response are attached to the
requesting agent as well, so the agent's visible history includes the context
it received from other participants.

This routing never invents recipients. CAMEL and AutoGen integrations must pass
provider-exposed recipient fields when available; MetaGPT uses the native
Message sender and send-to fields. If a provider omits a route, ExecWeave keeps
the message on the observed side and does not claim a delivery that was not
reported. Full prompt/response text requires the prompt_and_response content
policy (or another content-enabled policy); metadata_only intentionally records
lifecycle metadata without conversation bodies.

The repeatable full-dashboard acceptance is
`scripts/framework_dashboard_acceptance.py`. It materializes the merged event
stream, graph, offline viewer, `conversations.json`, `conversations.md`, and a
`dashboard-audit.json` that checks node/edge/event coverage, content-store
paths and hashes, per-agent visible messages, and process-reference resolution.
