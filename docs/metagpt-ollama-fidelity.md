# MetaGPT/Ollama recording fidelity

`scripts/real_metagpt_acceptance.py` uses an instance-scoped
`OllamaRecordingMixin`. It preserves the upstream behavior unless
`--preserve-chat-history` is explicitly passed. No installed MetaGPT files,
global classes, provider registrations, headers, or credentials are patched.

## Three boundaries

| Boundary | Content | Meaning |
|---|---|---|
| `aask_entry` | `aask_arguments`, legacy `messages`, `system_messages`, `format_messages`, `stream`, `system_prompt_policy` | Original caller intent and observed provider system policy, **not** transmitted content |
| `acompletion_text` | `final_messages`, `system_messages`, `stream`, `timeout` | After upstream default/suppressed system handling and compression; before Ollama transformation |
| `http_transport` | `provider_payload`, `transport_stream`, `request_timeout` | JSON decoded from the actual serialized `session.request(data=...)` body; independent of the transport's response-stream flag |

`system_messages_stage` defines the meaning of each legacy system field. No
inferred `system_source` is attached to HTTP messages. Compare caller arguments,
the enabled/default system policy, processed messages, and actual payload to
distinguish explicit, default, suppressed and caller-injected system content.
JSON is preserved without `default=str` or lossy message normalization.

All stage content uses the existing local, content-addressed store and capture
policy. Semantic event metadata contains references and IDs, not prompt bodies.
`metadata_only` stores no stage content; `prompt_only` excludes response bodies.
Caller prompts may themselves contain sensitive data; this is not a prompt
redaction system. Headers and API keys are never collected by the new wrapper.

## Identities and outcomes

Existing `MODEL_REQUEST`, `MODEL_RESPONSE`, `MODEL_FAILURE`, and
`HAS_MODEL_CONTENT` relationships continue to mean logical calls. Additive
`MODEL_CONTENT_RECORDED` events have `METAGPT_ACOMPLETION_TEXT`,
`METAGPT_HTTP_TRANSPORT` and `METAGPT_HTTP_TRANSPORT_OUTCOME` relationships.
Each includes `logical_call_id` and canonical `model_call_id`; HTTP events add
`provider_attempt_id`. These stage events must not be counted as model calls.

`ContextVar` isolates overlapping async calls on the same LLM instance. Direct
`acompletion_text`, `acompletion`, and `aask_batch` calls receive fallback logical
identities. Each batch completion is one logical call. Transport retries retain
that logical identity and obtain new attempt IDs.

An `attempted` event means the HTTP client request method was invoked; it is not
proof the server received bytes. Its outcome is `failed` (exception) or
`response_received` (HTTP headers arrived, including 4xx/5xx). Body/stream parsing
can still fail afterwards and produce a logical `MODEL_FAILURE`. Pre-transport
failures are `not_sent` and have no fabricated provider attempt. Independent
proxy evidence is required to prove server-side receipt and payload equality.

ActionNode's actual Tenacity callbacks record retries even when a later attempt
succeeds. Failures after a successful model return are labeled
`structured_output_processing`; that includes parsing/model validation and must
not be confused with an HTTP failure. This helper targets the inspected
`ActionNode._aask_v1` API and preserves its wait/stop/retry policy.

## Explicit compatibility correction

MetaGPT 1.0.0's installed `OllamaMessageChat.apply` reads only `messages[0]` and
relabels text as `user`. This affects all calls through that transformation
with multiple processed turns, including batch history; it is not a claim about
every MetaGPT version or provider. Merely enabling system prompts can make the
system prompt the only transmitted user message.

`--preserve-chat-history` wraps only that LLM's chat message adapter. The
equivalent SDK opt-in is `enable_chat_history_compatibility(llm)`. It preserves
turn order/roles, converts supported text/base64 image parts per message, and
retains generation options. Unsupported remote image URLs/part types fail
explicitly rather than being silently truncated. It does not enable system
prompts, download images, or alter stream behavior. The summary and stage
metadata distinguish `preserve_chat_history` from `unmodified`.

## Reproduction and verification

Use Python with MetaGPT 1.0.0 and its compatible dependencies installed, install
ExecWeave with `python -m pip install -e '.[dev]'`, and start genuine local Ollama
with `llama3.1:8b` available. Use a new output directory for every verification.

```sh
python -m pytest tests/test_metagpt_recording_fidelity.py -q
python scripts/real_metagpt_acceptance.py --output-dir .execweave-acceptance/actionnode --endpoint http://127.0.0.1:12345 --model llama3.1:8b --preserve-chat-history
python scripts/verify_metagpt_ollama_fidelity.py --output-dir .execweave-acceptance/fidelity --endpoint http://127.0.0.1:12345 --model llama3.1:8b
```

The verification script uses an independent loopback proxy. It checks full JSON
equality (including all fields/options), content SHA-256 references, system
semantics, upstream history loss and corrected history, compression, concurrency,
direct/batch calls, stream mismatches, pre-transport and real HTTP failures,
transport retries, successful ActionNode tasks, and failed/recovered parser
retries. The report distinguishes fault injection and mock responses:

- Transport retry: first real response followed by a controlled `ConnectionError`
  at the client boundary. Upstream retries built-in `ConnectionError`; its usual
  `openai.APIConnectionError` translation is not that exception. No assertion
  that every real network failure retries is made.
- Malformed/recovered structured output: actual model HTTP calls occur, but the
  proxy replaces designated response contents. This makes parser faults
  reproducible without claiming the model naturally emitted those contents.
- Image transformation: installed MetaGPT and actual loopback HTTP, with a mock
  response. The chosen text model's vision capability is **not** validated.

## Remaining limits

Verified against the installed package and source hashes in the audit, not an
assumed latest upstream checkout. Requestor/session and ActionNode API changes
require revalidation. The wrapper covers the inspected asynchronous chat paths,
not arbitrary direct client access, synchronous calls, or other providers.
MetaGPT's default system suppression and hard-coded temperature remain upstream
behavior. `config.stream=True` with call `stream=False` can produce an NDJSON
decode failure; recording exposes it without silently changing configuration.
The proxy buffers responses, so this verifies content and stream flags, not
stream timing/backpressure. Local/cloud Ollama equivalence is not claimed.

These logs provide observation, not tamper-proof provenance, adversarial agent
isolation, or task correctness. Recording fidelity, conversation preservation
and ActionNode task success are evaluated separately.
