<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <strong>繁體中文</strong> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave 可以在 AI Agent 或任意 command 還在執行時，持續串流本機 execution graph。

```bash
execweave live --open -- claude
```

## 目前契約

Live runtime collector 刻意使用跨平台的 `portable` backend。從 v0.6.4 起，每個 live run 也可以透過 run-specific sidecar 接收第二條 append-only specialized evidence stream。

ExecWeave 會把 sidecar 路徑以以下環境變數提供給被啟動的 command：

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Specialized evidence 可以透過多種 attribution-safe 路徑自動進入：

- 已設定的 Claude Code、OpenAI Codex、Antigravity、Cursor hooks；
- 已安裝的 OpenCode plugin；
- 當 ExecWeave 啟動支援的本機 Ollama、llama.cpp、vLLM server 時，使用 loopback model-catalog probe；
- 對 `lms server start --port <port>` 使用 success-gated LM Studio post-launch probe，而且 launch 前該相容 endpoint 必須不存在；
- LiteLLM Proxy 已設定一次 ExecWeave custom callback，且 proxy 是在目前這次 `execweave live` 環境內啟動。

這**不代表** `live` 會偷偷修改 provider、gateway 或 runtime 設定。需要 hook/plugin/callback 的整合仍必須先設定一次。自動 model-runtime probe 僅限已辨識的本機 launch command 與 loopback endpoint。OpenRouter routing metadata 仍不是自動的，因為遠端 HTTPS/network observation 無法提供 authoritative provider routing 細節。

Linux `strace` backend 目前是在 command 結束後才解析 trace file。它能提供更強的 syscall-backed attribution，但在目前實作中不是 live event source。ExecWeave 不會把 post-processed evidence 標成 live telemetry。

需要較強的 Linux post-run attribution 時可用：

```bash
execweave record --backend strace --open -- claude
```

## v0.6.4 data flow

```text
specialized producers ─┐
  Agent hooks/plugin   │
  model-runtime probe  ├─→ semantic.jsonl ────────────────┐
  LiteLLM callback     │                                  │
                      ─┘                                  │
                                                         ↓
command ─→ portable ─→ events.jsonl ───────→ incremental live normalizer
                                                         ↓
                                                  GraphAccumulator
                                                         ↓
                                              localhost HTTP server
                                                         ↓
                                                 /live.json deltas
                                                         ↓
                                                   browser / Top
```

OS runtime evidence 仍是獨立的 ground-truth stream。Specialized evidence 只會 provisional 地正規化進 live graph；它不能改寫 raw runtime stream，也不能補造缺少的 evidence。

Browser 與 detached `execweave top` dashboard 會消費帶 sequence number 的 `/live.json` snapshots/deltas。`/graph.json` 仍提供目前 snapshot。Incremental ingestion 只 tail 新 append 的 JSONL bytes，若最後一行尚未有 newline，會先 buffer，等完整後再處理。

當 command 結束時，ExecWeave 會：

1. 驗證完整 runtime event stream；
2. 完成在 launch 前已準備、且 attribution-safe 的 post-command specialized observation；
3. 如果有 specialized evidence，執行 canonical runtime + specialized merge，輸出 `events.semantic.jsonl`；
4. 從這條 canonical stream 重建 final graph，而不是相信 provisional live state；
5. 寫出 `graph.json` 與 standalone `viewer.html`；
6. 將 live graph 標成 finished，短暫提供 final viewer 後關閉 local server。

如果沒有任何 specialized event，final materialization 仍維持 runtime-only。

## 可自動出現在 Live Viewer 的 specialized integrations

| Integration | 自動進入 v0.6.4 Live Viewer |
| --- | --- |
| Claude Code | **是**，需先設定 ExecWeave hooks |
| OpenAI Codex | **是**，需先設定 ExecWeave hooks |
| Antigravity | **是**，需先設定 ExecWeave hooks |
| Cursor | **是**，需先設定 ExecWeave hooks |
| OpenCode | **是**，需先安裝 ExecWeave plugin |
| Ollama | **是**，限已辨識的本機 `ollama serve` launch |
| llama.cpp | **是**，限已辨識的本機 `llama-server` launch |
| vLLM | **是**，限已辨識的本機 vLLM server launch |
| LM Studio | **是**，`lms server start --port <port>` 成功，且 launch 前 endpoint 不存在 |
| LiteLLM Proxy | **是**，callback 已設定，且 proxy 繼承這次 live sidecar |
| OpenRouter | **否**，routing metadata 不會自動取得；仍可觀察本機 client 的 OS/network activity |

這些整合共用同一個 per-run specialized sidecar contract，但仍保留各自的 evidence layer 與語義。Model catalog 不等於 Agent 發起 request；gateway response 不等於某個 OS process 造成 request；缺少的 identity 不會被推測。

## Terminal Top

`top` 不會蓋在 Agent terminal 上。原本 terminal 保持可互動，dashboard 則 attach 到同一個 localhost live session，並在另一個 terminal 視窗顯示：

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` 會另外開 browser Viewer。Detached dashboard 只是 attach client，不會再啟動第二個 Agent。內部 attach URL 僅允許 localhost HTTP。

## Network exposure

Live server 只綁定：

```text
127.0.0.1
```

不會暴露在 `0.0.0.0`，也不是設計給 LAN 上其他 host 連線。

明確指定 port：

```bash
execweave live --port 8765 --open -- claude
```

預設 `--port 0` 代表交給 OS 選擇可用的 local port。

## Artifacts

預設 run directory：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── semantic.jsonl
├── events.semantic.jsonl      # 只有存在 specialized evidence 時才 materialize
├── graph.json
└── viewer.html
```

`events.jsonl` 永遠保持 runtime-only。`semantic.jsonl` 是 raw specialized sidecar，可以包含 Agent/IDE、model-runtime 或 inference-gateway evidence。若有 specialized evidence，final `graph.json` 會從 `events.semantic.jsonl` 建立；否則直接從 `events.jsonl` 建立。

自訂目錄：

```bash
execweave live --output-dir my-live-run --open -- claude
```

既有 non-empty artifact 會被拒絕，不會被覆寫。

## Provisional live normalization

Live run 期間，因為 session 尚未結束，兩條 JSONL stream 都可能還不完整。

因此 live normalizer 採 incremental、conservative 行為。目前已觀察到的 runtime process identity 可以用來解析 specialized process reference，但缺少 identity 時絕不猜測。Specialized event 如果當下還無法正規化，也不會因為「在 live 中看到了」就變成更強的 evidence。

Sidecar truncation 會讓 provisional materialization reset，並從目前檔案重新 replay。不完整的 trailing JSONL record 會先 buffer，而不是當成完整 event。Final graph 仍會在 runtime validation 成功後，從 canonical merge 重新建立。

## Automatic model-runtime probe boundary

自動 model-runtime observation 的邊界刻意很窄。ExecWeave 只 probe 已辨識的本機 server launch command 與 local/loopback endpoint。Probe 失敗採 fail-open，不會影響被啟動 command 的結果。

Ollama、llama.cpp、vLLM 在 server 執行期間可取樣本機 model state/catalog。LM Studio 不同：`lms server start` 是啟動 persistent server 的短命 launcher，因此 ExecWeave 會在 launch 前先準備 observation；如果相容 endpoint 原本就存在，就不會把它歸因到這次 session；只有 launcher 成功離開後，才 materialize post-launch catalog。

Catalog relation 仍保留 runtime-specific 語義。例如 LM Studio catalog visibility 使用 `ADVERTISES_MODEL`，不是「model weights 當下已 resident in memory」的證明。

## LiteLLM callback boundary

LiteLLM Proxy 可以透過 custom-callback config 一次載入 `execweave.litellm_callback.execweave_litellm_callback`。當 proxy 在 `execweave live` 裡執行時，它會繼承 `EXECWEAVE_SEMANTIC_SIDECAR`，並只把 whitelist routing/usage metadata 寫入該 run。

Callback 不會保存 messages、response content、model parameters、arbitrary metadata、API-key metadata 或 provider `api_base`。Provider identity 不會從 model string 或 URL 推測。若沒有 run-specific sidecar 環境變數，callback 就是 no-op。

列印 LiteLLM config fragment：

```bash
execweave-litellm-callback --print-config
```

## Portable-backend limitations

目前 live runtime layer 繼承 portable collector 的限制：

- process discovery 是 polling-based；
- 極短命 process 可能被漏掉；
- filesystem change 是 session-correlated，不是 process-attributed；
- per-process network inspection 取決於 OS visibility 與 permissions。

這些限制會保留在 event attribution metadata。Live Viewer 不會把 non-causal observation 升級成 causal edge。

## Large-session safety

Live update 使用 bounded delta history，不會每次 poll 都 replay 整條 event stream。當 graph 超過 Viewer safety budget 時，live endpoint 會切換成 compact counts-only payload，讓 collection 與 final canonical artifact generation 繼續執行，而不強迫 browser materialize 不安全的大型 SVG graph。

## Future native live backends

規劃中的 collector：

- Linux eBPF；
- Windows ETW；
- macOS Endpoint Security。

目標是在維持相同 ExecWeave event semantics 的前提下，提升 completeness、process attribution 與 runtime overhead。

## CI coverage

Repository CI 目前覆蓋：

- localhost live-session startup 與 final artifact generation；
- 帶 sequence number 的 snapshot/delta 與 resynchronization；
- incomplete trailing JSONL record；
- semantic sidecar 在 runtime identity ready 前就抵達；
- semantic sidecar truncation 與 replay；
- canonical final runtime + specialized rebuild；
- Claude、Codex、Antigravity、Cursor、OpenCode 的 automatic shared-sidecar delivery；
- Ollama、llama.cpp、vLLM automatic local model-runtime probe，以及 attribution-safe LM Studio launch handling；
- LiteLLM callback privacy、fail-open behavior 與 final live-graph materialization；
- detached Top 不會啟動第二個 Agent；
- Top attach URL 僅限 localhost；
- clean-wheel 安裝後的 LiteLLM callback setup command。
