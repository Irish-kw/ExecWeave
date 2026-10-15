# Native OpenAI Agents SDK tracing (v0.8.37 candidate)

The optional Agents SDK bridge captures authoritative tracing callbacks from
`agents.Agent`, `Runner.run(...)`, `@function_tool`, and SDK handoff spans.
It is **not** the existing `OpenAIAgentRecorder.wrap(OpenAI())` integration:
the latter wraps calls to OpenAI Responses / Chat Completions clients directly.

## Install and start

Install an unpublished PR build from the checked-out branch, or after release:

```bash
python -m pip install -e '.[agents]'
```

Add this setup **before the first** `Runner.run` or `trace` context:

```python
from agents import Agent, Runner, function_tool
from execweave.openai_agents_sdk import install_agents_sdk_tracing

recorder = install_agents_sdk_tracing(capture_mode="metadata_only")

@function_tool
def local_status() -> str:
    return "ok"

agent = Agent(name="Example", instructions="Call local_status.", tools=[local_status])
result = Runner.run_sync(agent, "Call the status tool and summarize the result.")
print(result.final_output)
```

Capture this program using ExecWeave:

```bash
execweave live --open -- python your_agents_sdk_program.py
# Or:
execweave record -- python your_agents_sdk_program.py
```

No SDK processor is registered when launched outside ExecWeave; ordinary
execution continues normally. The SDK provides tracing callbacks only if SDK
tracing is enabled. The install function is additive: it **does not disable**
the SDK's default exporter or control any telemetry that the SDK may send to
other destinations. Independently configure provider tracing/export privacy.

To save exposed prompt and tool payloads locally, pass
`capture_mode="prompt_and_response"`. The default `metadata_only` stores
no prompt/tool input or response plaintext. Do not collect secrets; redaction
filters credential-shaped keys and hidden reasoning keys, but **cannot reliably
remove secrets within free-form strings**. Protect the run directory.

## Scope, provenance and coverage

| SDK source | Recorded observation | Boundary |
| --- | --- | --- |
| SDK trace and task/turn spans | Run task identity, phase/turn boundaries and coverage | Span end is not business-task success |
| Agent span | Agent identity, start/stop, available tools | Available tools are **not** executed or selected tools |
| Generation / Responses span | Model request/response/failure, model identity | Model output is provider evidence, not independent action proof |
| Function span | Named tool call, result/failure, span identities | Function return is **not** an OS or remote-host success receipt |
| Handoff span | Source/target of the reported handoff | No receive event is invented |
| Trace completion | Observation coverage counts and missing spans | A complete trace is not complete OS/runtime observation |

A model identity that becomes available only at span completion is explicitly\nmarked with `model_identity_resolved_at_end`; the earlier request record\nremains `unknown`, preserving the true observation boundary.\n\nEvery emitted model/tool observation includes `sdk_trace_id`,
`sdk_span_id`, `sdk_parent_span_id` and
`evidence_source=agents_sdk_tracing_callback`. SDK span IDs are used for
stable run-local linking; raw content is stored only by explicit policy in
ExecWeave's content-addressed store. Trace-end coverage includes a count by
span type, unattributed spans, unclosed spans and callback processing errors.
It is a coverage **receipt**, not an assurance that unexposed SDK events
occurred or a cryptographic signature. See `execweave-integrity` for
the existing local consistency verifier and its threat-model limits.

SDK traces can include multiple Agent spans and tool calls within a process.
Agent identity and OS process identity are different: the adapter binds the
Agent to its current SDK-owning process, **not** to a remote command it emits.
To attest remote Windows effects, observe the target machine independently and
correlate with trustworthy identifiers; the processor intentionally does not
infer effects from socket sends or tool return text.

A two-phase workflow that runs a selector Agent and then constructs a new Agent
is recorded as two SDK traces unless the user wraps both runs in an explicit
SDK trace context. The selector's generated JSON is **model output**. A list
of selected tools becomes authoritative only when the application observes
its validated selection or the subsequent Agent span enumerates availability.
The adapter never labels a proposed choice as an executed tool.

## Acceptance and review

Offline fixtures in `tests/test_openai_agents_sdk.py` check Agent, generation,
function and handoff lifecycles; attribution; content controls; missed callback
coverage; repeated callbacks; failed spans; and the separation between tool
returns and independently observed runtime facts. They do not use a paid API
key, execute any system command or establish a network connection.

Before publishing a release, validate a non-destructive real Agents SDK
workflow in a clean environment on all supported OSes, inspect `graph.json`,
`semantic.jsonl`, `finalization.json`, and the generated conversation panels,
and run the normal release gates. Re-run with content capture only in a
synthetic-data environment to confirm redaction and source completeness.

Trace-start records a canonical SDK trace task; Runner task/turn spans retain
their own SDK identities and event boundaries. The SDK conversation group,
when present, is recorded as a SHA-256 reference rather than cleartext.
Neither SDK task-span end nor turn-span end is promoted to a successful
business outcome. Nested task/turn spans inherit the nearest independently
observed Agent parent; disconnected ancestry remains unattributed.
