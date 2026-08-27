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

Current Antigravity hook evidence is intentionally bounded to values actually supplied by the hook contract. ExecWeave can record:

- invocation lifecycle metadata exposed by `PreInvocation` / `PostInvocation`;
- tool identity, arguments, result/error status exposed by `PostToolUse`;
- declared command or file targets when those fields are present in the supplied tool arguments;
- complete hook-supplied values in the local content-addressed store where supported.

This does **not** claim access to hidden model state, private chain-of-thought, an unseen provider-side request, or any content not delivered to the hook. OS-runtime evidence remains a separate layer.

## Legacy Gemini CLI

The older `execweave-gemini-*` entry points remain available for compatibility with existing installations and archived workflows. They are not the current Google CLI path documented by ExecWeave; new usage should target Antigravity with `agy`.
