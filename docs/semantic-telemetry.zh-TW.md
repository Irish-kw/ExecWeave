<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <a href="semantic-telemetry.ko.md">한국어</a> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave 會把 provider/framework semantic observation 與獨立 OS runtime evidence 結合，但不會改寫原始 runtime capture。Provider evidence 說明 Agent、tool、gateway 或 model-runtime integration point 明確曝露了什麼；OS evidence 說明 machine collector 實際觀察到什麼。Correlation 永遠是獨立 derived layer，不會被默默升級成 causal proof。

## Workflow

Provider adapter 先寫入 run-bound semantic sidecar，再由 ExecWeave 驗證新的 merged stream：

```bash
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

`semantic-merge` 永遠不修改 `run.jsonl`。Run-bound recorder 會把 runtime、semantic、correlated artifacts 分開保存。

## v0.6.5 full-fidelity content

Semantic telemetry 已不再侷限於小型 metadata summary。當受支援 integration point 明確提供 content 時，v0.6.5 可以把來源提供的完整值存入本機 content-addressed store，而 JSONL event 只放 reference。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

Content reference 會記錄 SHA-256、relative path、media type、byte size、content kind、representation，以及該值是否對該 integration point 而言 complete from source。`complete_from_source: true` 表示 ExecWeave 完整保存收到的值；**不代表** provider 曝露了 hidden model state、未觀察到的 final wire request，或任何 integration point 根本沒提供的欄位。

Native adapters 會對 hook/API surface 明確提供的內容使用此機制，包括 prompts、tool inputs/results、assistant/model responses、明確曝露的 reasoning/thinking text、provider hook 明確提供的 file content，以及 adapter contract 支援的 provider request/response objects。

即使 content store 失敗，compact semantic summary 仍可供 graph materialization 使用。Native hook adapters 預設 fail-open，因此 content-storage failure 不會刻意阻擋 Agent operation。

## Evidence boundary

Semantic content 是 observed provider/integration evidence，不是 OS causality。保存 tool input 不代表某個 process 執行了它；hook 提供的 file body 不代表 OS read 已完成；CLI 提供的 request/response pair 也不代表 transparent network interception。

Tool → Process bridge 只能由另外定義的 conservative correlation layer 建立，而且仍維持：

```text
inferred: true
causal: false
```

未知或 ambiguous attribution 不會建立 bridge。File 與 network observation 同時存在，也不能直接推論 byte-level data flow 或 exfiltration。

## Privacy

Full-fidelity content 本來就屬於敏感資料。**不要假設** prompt text、tool argument、tool output、model response、file content 或 application-level secret value 已被 redacted。Content store 會保留受支援 integration point 提供的完整值。

ExecWeave 只會在 adapter contract 明確定義時，從 provider-metadata projection 過濾已知 transport credentials；這不是通用 secret scanner，也不會移除 content payload 內嵌的 secret。Content blobs 預設留在本機，且不 inline 到 graph events，但仍是 run evidence 的一部分，分享前必須檢查。

每個 provider-specific 文件會定義該 integration 能觀察哪些欄位。Claude Code、Codex、Antigravity、Cursor、OpenCode、Inference Gateway 與 Model Runtime 的精確邊界請參考各自文件。
