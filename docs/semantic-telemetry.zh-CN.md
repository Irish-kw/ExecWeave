<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave 将 provider/framework semantic observation 与独立 OS runtime evidence 结合，但不会改写原始 runtime capture。Provider evidence 说明 Agent、tool、gateway 或 model-runtime integration point 明确暴露了什么；OS evidence 说明 machine collector 实际观察到了什么。Correlation 始终是独立 derived layer，不会被静默升级为 causal proof。

## Workflow

Provider adapter 先写入 run-bound semantic sidecar，再由 ExecWeave 验证新的 merged stream：

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`semantic-merge` 永远不修改 `run.jsonl`。Run-bound recorder 将 runtime、semantic、correlated artifacts 分开保存。

## v0.6.5 full-fidelity content

Semantic telemetry 已不再局限于小型 metadata summary。受支持 integration point 明确提供 content 时，v0.6.5 可以把来源提供的完整值存入本地 content-addressed store，而 JSONL event 只放 reference。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Content reference 记录 SHA-256、relative path、media type、byte size、content kind、representation，以及该值对该 integration point 是否 complete from source。`complete_from_source: true` 表示 ExecWeave 完整保存了收到的值；**不代表** provider 暴露了 hidden model state、未观察到的 final wire request，或 integration point 根本没有提供的字段。

Native adapters 会对 hook/API surface 明确提供的内容使用此机制，包括 prompts、tool inputs/results、assistant/model responses、明确暴露的 reasoning/thinking text、provider hook 明确提供的 file content，以及 adapter contract 支持的 provider request/response objects。

即使 content store 失败，compact semantic summary 仍可用于 graph materialization。Native hook adapters 默认 fail-open，因此 content-storage failure 不会有意阻断 Agent operation。

## Evidence boundary

Semantic content 是 observed provider/integration evidence，不是 OS causality。保存 tool input 不代表某个 process 执行了它；hook 提供的 file body 不代表 OS read 已完成；CLI 提供的 request/response pair 也不代表 transparent network interception。

Tool → Process bridge 只能由单独定义的 conservative correlation layer 创建，并保持：

```text
inferred: true
causal: false
```

未知或 ambiguous attribution 不会建立 bridge。File 与 network observation 同时存在，也不能直接推断 byte-level data flow 或 exfiltration。

## Privacy

Full-fidelity content 本身就是敏感数据。**不要假设** prompt text、tool argument、tool output、model response、file content 或 application-level secret value 已经 redacted。Content store 会保存受支持 integration point 提供的完整值。

ExecWeave 只会在 adapter contract 明确定义时，从 provider-metadata projection 过滤已知 transport credentials；这不是通用 secret scanner，也不会删除 content payload 内嵌的 secret。Content blobs 默认留在本地，且不会 inline 到 graph events，但仍是 run evidence 的一部分，分享前必须检查。

每个 provider-specific 文档会定义该 integration 能观察哪些字段。Claude Code、Codex、Antigravity、Cursor、OpenCode、Inference Gateway 与 Model Runtime 的精确边界请参阅各自文档。
