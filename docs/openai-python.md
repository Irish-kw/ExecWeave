# Custom Python with an OpenAI API key (single or multi-agent)

ExecWeave can launch any Python program under `execweave record` or `execweave live`, with local process, file and network evidence. An arbitrary HTTPS request alone **does not** reveal the model, prompt, response or multi-agent role. To collect *authoritative* OpenAI SDK call evidence, explicitly wrap the client with the optional `OpenAIAgentRecorder` adapter.

## Install and execute

```bash
python -m pip install 'execweave>=0.8.35' openai
export OPENAI_API_KEY='your-key-from-your-secret-manager'
execweave record -- python my_agent.py
# Or run the portable live dashboard:
execweave live --open -- python my_agent.py
```

Do not put the key in argv; the official OpenAI SDK reads `OPENAI_API_KEY` itself. If you are reviewing an unreleased ExecWeave branch, install **the same tested wheel** rather than assuming it is published on PyPI.

### One Agent: `my_agent.py`

```python
from openai import OpenAI
from execweave.openai_agents import OpenAIAgentRecorder

trace = OpenAIAgentRecorder()  # metadata_only: no prompt/response plaintext
client = trace.wrap(OpenAI())  # API key stays in the SDK; not passed to trace
with trace.agent("Researcher"):
    response = client.responses.create(model="gpt-5.6", input="Summarize the task.")
    print(response.output_text)
```

The run-scoped `semantic.jsonl` receives `AGENT_CREATED`, `MODEL_REQUEST` and `MODEL_RESPONSE`, plus OS evidence in `events.jsonl`. `record` merges these into `graph.json`; `live` consumes the same sidecar. If `ExecWeave` has not launched the program, the adapter is a no-op.

To explicitly save request/response content instead of metadata, use `OpenAIAgentRecorder(capture_mode="prompt_and_response")`. This can capture sensitive prompts and model outputs in local content-addressed artifacts. Review them before sharing. Credential-shaped keys are removed from structured payloads, but secrets typed **inside** prompts cannot be reliably detected.

### Multiple Agents and handoffs

```python
from openai import OpenAI
from execweave.openai_agents import OpenAIAgentRecorder

trace = OpenAIAgentRecorder()
client = trace.wrap(OpenAI())

with trace.agent("Planner"):
    plan = client.responses.create(model="gpt-5.6", input="Draft a plan.")
    # Your own application must actually perform this send.
    trace.sent("handoff-42", "Planner", "Reviewer")

with trace.agent("Reviewer"):
    # Record only when your application actually observes the receive.
    trace.received("handoff-42", "Planner", "Reviewer")
    result = client.chat.completions.create(
        model="gpt-5.6",
        messages=[{"role": "user", "content": plan.output_text}],
    )
```

If the send was observed but the receive was **not**, record `trace.sent(...)` without `trace.received(...)`. ExecWeave can report `receive_not_observed` for that exact sender/recipient pair. It does **not** prove network delivery failed. Do not emit `received` optimistically or infer roles from which model was called.

For tool execution owned by a known Agent, call `call_id = trace.tool_started("shell", arguments={...})`, then `trace.tool_finished(call_id, result=..., failed=False)` after actually observing execution. Model-generated tool proposals are not execution proof.

## Scope and restrictions

- Supported wrapped SDK surfaces: synchronous and async `client.responses.create(...)` and `client.chat.completions.create(...)`. Other SDK resources continue to work but are not automatically semantically recorded.
- Streaming `stream=True`: the **request** event is recorded, but the wrapper does not claim a completed model response from a stream iterator. Do not interpret absence as a model failure.
- No transparent HTTPS decryption, no interception of unwrapped requests, no automatic discovery of multiple user-defined Agent roles, and no guarantee of portable polling coverage for short-lived subprocesses.
- Launch arguments are redacted in recorded Session/Process entities by default, although the launched Python program still receives the original argv unchanged. Environment values are not copied into framework metadata.
- `capture_mode="metadata_only"` is the secure SDK default independent of the CLI content policy. Use explicit opt-in for content, and never put real credentials in fixtures or issue reports.
- This module is an **opt-in SDK instrumentor**, not a claim that every Python script using an OpenAI API key is automatically fully observed.

Offline verification uses a mock OpenAI-compatible client; no external paid key is needed. Use a separate controlled end-to-end test before asserting correctness for a particular installed OpenAI SDK version.
