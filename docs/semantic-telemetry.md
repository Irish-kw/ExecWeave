<!-- i18n-nav:start -->
<p align="center">
  <strong>English</strong> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave combines provider/framework semantic observations with independent OS runtime evidence without rewriting the original runtime capture. Provider evidence explains what an Agent, tool, gateway, or model-runtime integration point exposed; OS evidence explains what the machine collector observed. Correlation remains a separate derived layer and is never silently promoted to causal proof.

## Workflow

A provider adapter writes a run-bound semantic sidecar, then ExecWeave validates a new merged stream:

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`run.jsonl` is never modified by `semantic-merge`. Run-bound recorders keep runtime, semantic, and correlated artifacts as separate files.

## Full-fidelity content in v0.6.5

Semantic telemetry is no longer limited to small metadata summaries. When a supported integration point explicitly supplies content, v0.6.5 can store the complete supplied value in a local content-addressed store and put only a reference in the JSONL event.

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

A content reference records SHA-256, relative path, media type, byte size, content kind, representation, and whether the stored value is complete from that integration point. `complete_from_source: true` means ExecWeave preserved the complete value it received; it does **not** claim that a provider exposed hidden model state, an unseen final wire request, or any field the integration point did not deliver.

Supported native adapters now use this mechanism for the content their hook/API surface exposes, including prompts, tool inputs/results, assistant/model responses, reasoning/thinking text when explicitly provided, file content when explicitly supplied by the provider hook, and provider request/response objects where the adapter contract supports them.

The compact semantic summary remains useful for graph materialization even if the content store fails. Native hook adapters are fail-open by default so a content-storage failure does not intentionally block the Agent operation.

## Evidence boundary

Semantic content is observed provider/integration evidence, not OS causality. A stored tool input does not prove that a process executed it; a stored file body supplied by a hook does not prove an OS read completed; and a request/response pair supplied by a CLI does not imply transparent network interception.

Tool → Process bridges are created only by the separately defined conservative correlation layer and remain:

```text
inferred: true
causal: false
```

Unknown or ambiguous attribution produces no bridge. Byte-level data flow and exfiltration are not inferred merely because file and network observations coexist.

## Privacy

Full-fidelity content is intentionally sensitive. Do **not** assume prompt text, tool arguments, tool output, model responses, file content, or application-level secret values have been redacted. The content store preserves the complete value supplied by the supported integration point.

ExecWeave filters known transport credentials from provider-metadata projections where the adapter contract defines that filtering, but that is not a general secret scanner and does not remove secrets embedded inside content payloads. Content blobs remain local by default and are not inlined into graph events, but they are still part of the run evidence and must be reviewed before sharing.

Provider-specific documents define exactly which fields each integration can observe. See the Claude Code, Codex, Gemini, Cursor, OpenCode, Inference Gateway, and Model Runtime documentation for those boundaries.
