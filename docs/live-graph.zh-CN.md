<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="live-graph.ja.md">日本語</a> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave 可以在 AI Agent 或任意 command 仍在运行时持续串流本机 execution graph。

```bash
execweave live --open -- claude
```

## 当前契约

Live runtime collector 有意使用跨平台 `portable` backend。从 v0.6.4 起，每个 live run 还可以通过 run-specific sidecar 接收第二条 append-only specialized evidence stream。

ExecWeave 会把 sidecar 路径通过以下环境变量提供给被启动的 command：

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Specialized evidence 可以通过多种 attribution-safe 路径自动进入：

- 已配置的 Claude Code、OpenAI Codex、Antigravity、Cursor hooks；
- 已安装的 OpenCode plugin；
- 当 ExecWeave 启动受支持的本机 Ollama、llama.cpp、vLLM server 时，使用 loopback model-catalog probe；
- 对 `lms server start --port <port>` 使用 success-gated LM Studio post-launch probe，并且 launch 前该兼容 endpoint 必须不存在；
- LiteLLM Proxy 已配置一次 ExecWeave custom callback，并且 proxy 是在当前这次 `execweave live` 环境内启动。

这**不表示** `live` 会静默修改 provider、gateway 或 runtime 配置。需要 hook/plugin/callback 的整合仍必须先配置一次。自动 model-runtime probe 仅限已识别的本机 launch command 与 loopback endpoint。OpenRouter routing metadata 仍不是自动获取，因为远端 HTTPS/network observation 无法提供 authoritative provider routing 细节。

Linux `strace` backend 当前在 command 结束后解析 trace file。它能提供更强的 syscall-backed attribution，但在当前实现中不是 live event source。ExecWeave 不会把 post-processed evidence 标记为 live telemetry。

需要更强的 Linux post-run attribution 时可用：

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

OS runtime evidence 仍是独立的 ground-truth stream。Specialized evidence 只会 provisional 地规范化进 live graph；它不能改写 raw runtime stream，也不能补造缺失 evidence。

Browser 与 detached `execweave top` dashboard 会消费带 sequence number 的 `/live.json` snapshots/deltas。`/graph.json` 仍提供当前 snapshot。Incremental ingestion 只 tail 新 append 的 JSONL bytes，最后一行如果还没有 newline，会先 buffer，完整后再处理。

当 command 结束时，ExecWeave 会：

1. 验证完整 runtime event stream；
2. 完成 launch 前已准备且 attribution-safe 的 post-command specialized observation；
3. 如果存在 specialized evidence，执行 canonical runtime + specialized merge，写出 `events.semantic.jsonl`；
4. 从这条 canonical stream 重建 final graph，而不是信任 provisional live state；
5. 写出 `graph.json` 与 standalone `viewer.html`；
6. 将 live graph 标记 finished，短暂提供 final viewer 后关闭 local server。

如果没有任何 specialized event，final materialization 仍保持 runtime-only。

## 可自动出现在 Live Viewer 的 specialized integrations

| Integration | 自动进入 v0.6.4 Live Viewer |
| --- | --- |
| Claude Code | **是**，需先配置 ExecWeave hooks |
| OpenAI Codex | **是**，需先配置 ExecWeave hooks |
| Antigravity | **是**，需先配置 ExecWeave hooks |
| Cursor | **是**，需先配置 ExecWeave hooks |
| OpenCode | **是**，需先安装 ExecWeave plugin |
| Ollama | **是**，限已识别的本机 `ollama serve` launch |
| llama.cpp | **是**，限已识别的本机 `llama-server` launch |
| vLLM | **是**，限已识别的本机 vLLM server launch |
| LM Studio | **是**，`lms server start --port <port>` 成功且 launch 前 endpoint 不存在 |
| LiteLLM Proxy | **是**，callback 已配置且 proxy 继承这次 live sidecar |
| OpenRouter | **否**，routing metadata 不会自动获取；仍可观察本机 client 的 OS/network activity |

这些整合共用同一 per-run specialized sidecar contract，但保留各自 evidence layer 与语义。Model catalog 不等于 Agent 发起 request；gateway response 不等于某个 OS process 造成 request；缺失 identity 永远不会被猜测。

## Terminal Top

`top` 不会覆盖 Agent terminal。原本 terminal 保持可交互，dashboard 会 attach 到同一个 localhost live session，并显示在另一个 terminal 窗口：

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` 会另外打开 browser Viewer。Detached dashboard 只是 attach client，不会再启动第二个 Agent。内部 attach URL 仅允许 localhost HTTP。

## Network exposure

Live server 只绑定：

```text
127.0.0.1
```

不会暴露在 `0.0.0.0`，也不是设计给 LAN 上其他 host 访问。

明确指定 port：

```bash
execweave live --port 8765 --open -- claude
```

默认 `--port 0` 表示交给 OS 选择可用 local port。

## Artifacts

默认 run directory：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── semantic.jsonl
├── events.semantic.jsonl      # 仅存在 specialized evidence 时 materialize
├── graph.json
└── viewer.html
```

`events.jsonl` 始终保持 runtime-only。`semantic.jsonl` 是 raw specialized sidecar，可以包含 Agent/IDE、model-runtime 或 inference-gateway evidence。存在 specialized evidence 时，final `graph.json` 从 `events.semantic.jsonl` 建立；否则直接从 `events.jsonl` 建立。

自定义目录：

```bash
execweave live --output-dir my-live-run --open -- claude
```

已有 non-empty artifact 会被拒绝，不会覆盖。

## Provisional live normalization

Live run 期间，因为 session 尚未结束，两条 JSONL stream 都可能还不完整。

因此 live normalizer 采用 incremental、conservative 行为。当前已观察到的 runtime process identity 可以用于解析 specialized process reference，但 identity 缺失时绝不猜测。Specialized event 如果当下还无法规范化，也不会因为“在 live 中看到”就变成更强 evidence。

Sidecar truncation 会让 provisional materialization reset，并从当前文件重新 replay。不完整的 trailing JSONL record 会先 buffer，而不是作为完整 event。Final graph 仍会在 runtime validation 成功后从 canonical merge 重新建立。

## Automatic model-runtime probe boundary

自动 model-runtime observation 的边界有意很窄。ExecWeave 只 probe 已识别的本机 server launch command 与 local/loopback endpoint。Probe 失败采用 fail-open，不会影响被启动 command 的结果。

Ollama、llama.cpp、vLLM 在 server 运行期间可采样本机 model state/catalog。LM Studio 不同：`lms server start` 是启动 persistent server 的短命 launcher，因此 ExecWeave 会在 launch 前先准备 observation；如果兼容 endpoint 原本就存在，就不会把它归因到本次 session；只有 launcher 成功退出后才 materialize post-launch catalog。

Catalog relation 仍保留 runtime-specific 语义。例如 LM Studio catalog visibility 使用 `ADVERTISES_MODEL`，不是“model weights 当时已 resident in memory”的证明。

## LiteLLM callback boundary

LiteLLM Proxy 可通过 custom-callback config 一次加载 `execweave.litellm_callback.execweave_litellm_callback`。当 proxy 在 `execweave live` 内运行时，它会继承 `EXECWEAVE_SEMANTIC_SIDECAR`，并只将 whitelist routing/usage metadata 写入该 run。

Callback 不保存 messages、response content、model parameters、arbitrary metadata、API-key metadata 或 provider `api_base`。Provider identity 不会从 model string 或 URL 推断。没有 run-specific sidecar 环境变量时，callback 就是 no-op。

打印 LiteLLM config fragment：

```bash
execweave-litellm-callback --print-config
```

## Portable-backend limitations

当前 live runtime layer 继承 portable collector 的限制：

- process discovery 是 polling-based；
- 极短命 process 可能被漏掉；
- filesystem change 是 session-correlated，不是 process-attributed；
- per-process network inspection 取决于 OS visibility 与 permissions。

这些限制会保留在 event attribution metadata。Live Viewer 不会把 non-causal observation 升级成 causal edge。

## Large-session safety

Live update 使用 bounded delta history，不会每次 poll 都 replay 整条 event stream。当 graph 超过 Viewer safety budget 时，live endpoint 会切换成 compact counts-only payload，让 collection 与 final canonical artifact generation 继续运行，而不强迫 browser materialize 不安全的大型 SVG graph。

## Future native live backends

规划中的 collector：

- Linux eBPF；
- Windows ETW；
- macOS Endpoint Security。

目标是在保持相同 ExecWeave event semantics 的前提下提升 completeness、process attribution 与 runtime overhead。

## CI coverage

Repository CI 当前覆盖：

- localhost live-session startup 与 final artifact generation；
- 带 sequence number 的 snapshot/delta 与 resynchronization；
- incomplete trailing JSONL record；
- semantic sidecar 在 runtime identity ready 前到达；
- semantic sidecar truncation 与 replay；
- canonical final runtime + specialized rebuild；
- Claude、Codex、Antigravity、Cursor、OpenCode 的 automatic shared-sidecar delivery；
- Ollama、llama.cpp、vLLM automatic local model-runtime probe，以及 attribution-safe LM Studio launch handling；
- LiteLLM callback privacy、fail-open behavior 与 final live-graph materialization；
- detached Top 不会启动第二个 Agent；
- Top attach URL 仅限 localhost；
- clean-wheel 安装后的 LiteLLM callback setup command。
