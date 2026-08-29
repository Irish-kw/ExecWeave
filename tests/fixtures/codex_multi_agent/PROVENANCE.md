# Codex multi-agent fixture

**Structurally derived from a real failing Codex v0.7.2 run.**
**Sensitive strings sanitized. Provider field structure preserved.**

`rollout-main.jsonl` and `hook-payloads.json` reproduce the record and payload shapes
of a real `gpt-5.6-terra` session that spawned four collaborating subagents. That run
shipped a `conversations.json` containing a single `/root` entry that had absorbed
every child's returns, while its graph carried five agents.

## What is preserved

Every structural field implicated in that failure is kept verbatim:

- `SubagentStop` payloads carrying **both** `transcript_path` (the parent rollout) and
  `agent_transcript_path` (the child rollout). Selecting the parent is what dropped
  every child conversation.
- `session_meta`, ordinals, and `subagent_history_start_ordinal` semantics.
- `spawn_agent` calls with their `call_id`, and the matching `function_call_output`
  carrying `{"task_name": "/root/<child>"}`.
- `SubAgentActivity` items carrying `agent_thread_id` and `agent_path` — the exact
  agent-id-to-agent-path linkage.
- `agent_message` records with `author`, `recipient`, and the
  `Message Type / Task name / Sender` header block.
- Provider session, turn and agent UUIDs, so identity scoping stays realistic.

## What is sanitized

- Host paths and the operating-system username replaced with
  `/workspace/execweave-fixture`.
- Unrelated files observed on the recording machine removed entirely.
- Natural-language prompts, reasoning, assistant answers, web search results and
  provider system instructions replaced with neutral fixture strings.
- Encrypted provider payloads are left as opaque ciphertext markers; they carry no
  readable content.

No credentials, authorization headers, API keys or personal identifiers are present.
Sanitization only replaces string *values*; no field was added, removed or renamed.
