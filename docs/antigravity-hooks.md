# Google Antigravity hooks

ExecWeave supports the current Google Antigravity CLI through its native hooks and OS-runtime collection. The Antigravity CLI executable is `agy`.

```bash
execweave live --open -- antigravity
# ExecWeave resolves this friendly name to the official `agy` CLI binary.
```

On the first provider-integrated run, Antigravity may ask whether the ExecWeave hook should be allowed. Choose **Allow / Yes** if you want provider-level tool and invocation evidence in addition to OS-runtime telemetry.

## Automatic bootstrap

For `agy` / `antigravity`, ExecWeave conservatively merges one named hook definition into:

```text
~/.gemini/config/hooks.json
```

The generated configuration can be inspected without writing it:

```bash
execweave-antigravity-hook --print-config
```

ExecWeave deliberately uses passive observation points:

- `PostToolUse` for tool-call/result evidence.
- `PreInvocation` and `PostInvocation` for invocation lifecycle metadata.
- **No `PreToolUse` hook is installed**, because that hook participates in Antigravity's permission decision and ExecWeave must not approve, deny, or alter a user's tool permission flow.

Existing unrelated named hooks are preserved. ExecWeave refuses to replace an existing hook definition with the same name rather than silently overwriting it.

## Layered recorder

```bash
execweave-antigravity-record --open -- antigravity
```

The recorder keeps runtime evidence, Antigravity semantic evidence, and derived correlation artifacts separate. Normal `execweave live --open -- antigravity` also auto-bootstraps the hook integration and exposes the live graph.

## Evidence scope

Antigravity evidence has two deliberately different boundaries.

The primary hook evidence is bounded to values actually supplied by the hook contract. ExecWeave can record:

- invocation lifecycle metadata exposed by `PreInvocation` / `PostInvocation`;
- tool identity, arguments, result/error status exposed by `PostToolUse`;
- declared command or file targets when those fields are present in the supplied tool arguments;
- complete hook-supplied values in the local content-addressed store where supported.

For a successful `invoke_subagent`, ExecWeave can additionally use the local `transcriptPath` supplied by the hook as **identity-correlation evidence**. The transcript record layout is treated as a live-verified Antigravity implementation wire, not as a public stable provider contract. A child assignment is emitted only when all conservative checks agree, including:

- the parent transcript is a canonical Antigravity brain transcript for the hook's parent `conversationId` and is read as a complete newline-terminated JSONL snapshot;
- exactly one matching `PLANNER_RESPONSE` / `invoke_subagent` request is immediately followed by an `INVOKE_SUBAGENT` result record;
- the transcript request's `Subagents` value exactly matches the successful `PostToolUse` request, and result count/order exactly matches request count/order;
- every child `conversationId` is non-empty, unique, and different from the parent;
- every child `logAbsoluteUri` is a canonical local file URI whose Antigravity brain path agrees with that child ID and the same Antigravity application-data root;
- the expected/inherited workspace is valid, and when the result exposes `workspaceUris`, the expected workspace is present there.

Malformed JSONL, torn writes, ambiguous duplicate matches, count mismatches, non-canonical URIs, workspace mismatches, duplicate/self child IDs, or any other failed validation cause ExecWeave to **abstain** and keep the original request-only evidence. No timestamp proximity is used to bridge transcript records.

When validation succeeds, the graph can contain:

```text
subtask --ASSIGNED_AGENT_TASK--> child agent
```

That edge is exact identity evidence (`identity_exact: true`) with identity method `validated_transcript_record_order_and_provider_ids`. It is **not** a child-lifecycle claim. The parent transcript does not by itself create `SPAWNED_AGENT`, returned-result, close, completion, or child-execution state; child provider hooks remain authoritative for those lifecycle observations.

The assignment edge does not copy `transcriptPath` or child `logAbsoluteUri` into its graph attributes. Hook-supplied metadata may still be preserved separately by the full-fidelity content layer according to the normal provider-metadata rules.

This integration does **not** claim access to hidden model state, private chain-of-thought, an unseen provider-side request, or any content not delivered to an observed local surface. OS-runtime evidence remains a separate layer.

## Legacy Gemini CLI

The older `execweave-gemini-*` entry points remain available for compatibility with existing installations and archived workflows. They are not the current Google CLI path documented by ExecWeave; new usage should target Antigravity with `agy`.
