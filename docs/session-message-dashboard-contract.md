# Session and message Dashboard contract

The raw graph is evidence, not the display layout. Session/model contexts and
message routes are view-only projections; original records and content hashes
remain intact. In particular, recording membership is not a causal process launch.

## Provider behavior

- An explicitly identified root connects to its recording session. Ambiguous
  multi-session membership is not guessed.
- A session branches to the root's observed models. Returning to an already used
  model reuses that context. Child models never replace the caller's model.
- Tool calls are assigned by their own model hint or observed chronology. Shared
  tools retain distinct per-model call edges and exact invocation histories.
  Incomplete switch chronology stays unattributed rather than invented.
- Child-to-root messages return to the root, regardless of the sender's model.
- Agent communication is collapsed history in the exact agent's inspector. It
  must not leak into another agent or a process/model inspector.

## Framework behavior

CAMEL, AutoGen and MetaGPT use the same root/session presentation where those
identities are observed. Their additional message projection is strictly gated
by `conversation_scope=framework_agent`; it cannot rewrite provider messages.

An observed sender/recipient pair becomes `sender -> message -> recipient`.
Addressed messages and observed deliveries remain distinct. Callback logs without
a recipient are not turned into delivery edges. Task prompts are displayed in
the assigned agent; raw task lifecycle nodes remain available for audit. A later
action lifecycle event cannot replace the real task prompt.

CAMEL's opt-in `observe_task_channel` wraps only the supplied native channel
instance. MetaGPT's `observe_message_delivery` is called after native
`Role.put_message`. AutoGen's real acceptance records incoming messages at native
`on_messages_stream` and SocietyOfMind model-context boundaries. Merely appearing
in a group output stream is not proof that every participant received a message.

## Verification and limits

`test_session_execution_flow.py` covers the 13 provider contracts, model switches,
shared tool calls, root/session geometry, exact-agent history and ambiguous
session abstention. The existing required Chromium CI job runs browser tests on
Windows, Linux and macOS. `test_framework_message_delivery.py` covers native
boundary semantics and framework-only routes.

The real Ollama runners are functional micro-scenarios, **not full paper benchmark
reproductions**. AutoGen's SocietyOfMind coordinator consumes an inner team's
results; its model does not dispatch their original user input. That ordering
must not be fabricated to match a desired picture. OWL is not AutoGen.

`framework_dashboard_acceptance.py` independently reads captured message text,
opens every relevant agent, verifies routes, content hashes, prompts, and live vs
finished parity. Its three-event runtime anchor verifies semantic merging, not
complete native OS collection. Missing browser dependencies fail unless static-only
checking was explicitly requested. Real captures are private local artifacts,
not checked into the repository.

The reported deleted `runs.rar` recordings cannot be replayed or recovered from
their former local paths. New runs and maintained provider fixtures do not prove
the contents of those deleted runs.
