<!-- i18n-nav:start -->
<p align="center">
  <a href="live-graph.md">English</a> |
  <a href="live-graph.zh-TW.md">繁體中文</a> |
  <a href="live-graph.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="live-graph.ko.md">한국어</a> |
  <a href="live-graph.fr.md">Français</a> |
  <a href="live-graph.de.md">Deutsch</a> |
  <a href="live-graph.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Live Graph

ExecWeave は AI Agent または任意の command が実行中でも、local execution graph を継続的に stream できます。

```bash
execweave live --open -- claude
```

## 現在の契約

Live runtime collector は意図的にクロスプラットフォームの `portable` backend を使用します。v0.6.4 では、各 live run が run-specific sidecar を通じて、2 本目の append-only specialized evidence stream も取り込めます。

ExecWeave は起動した command に sidecar path を次の環境変数として渡します。

```text
EXECWEAVE_SEMANTIC_SIDECAR
```

Specialized evidence は複数の attribution-safe path から自動で到着できます。

- 設定済みの Claude Code、OpenAI Codex、Gemini CLI、Cursor hooks；
- インストール済みの OpenCode plugin；
- ExecWeave が対応する local Ollama、llama.cpp、vLLM server を起動した場合の loopback model-catalog probe；
- `lms server start --port <port>` に対する success-gated LM Studio post-launch probe。ただし launch 前に同じ compatible endpoint が存在していないこと；
- ExecWeave custom callback を一度設定済みで、現在の `execweave live` 環境内で起動された LiteLLM Proxy。

これは `live` が provider、gateway、runtime の設定を勝手に変更するという意味では**ありません**。必要な hook/plugin/callback integration は事前に一度設定する必要があります。自動 model-runtime probe は、認識済みの local launch command と loopback endpoint に限定されます。OpenRouter の routing metadata は自動ではありません。remote HTTPS/network observation だけでは authoritative な provider routing 情報を取得できないためです。

Linux `strace` backend は現在、command 終了後に trace file を parse します。より強い syscall-backed attribution を提供しますが、現在の実装では live event source ではありません。ExecWeave は post-processed evidence を live telemetry として扱いません。

より強い Linux post-run attribution が必要な場合：

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

OS runtime evidence は独立した ground-truth stream のままです。Specialized evidence は provisional に live graph へ正規化されますが、raw runtime stream を書き換えたり、存在しない evidence を作ったりすることはできません。

Browser と detached `execweave top` dashboard は sequence-number 付きの `/live.json` snapshots/deltas を利用します。`/graph.json` は current snapshot endpoint として引き続き利用できます。Incremental ingestion は新しく append された JSONL bytes だけを tail し、末尾行が未完の場合は newline が来るまで buffer します。

Command 終了時、ExecWeave は：

1. completed runtime event stream を validate する；
2. launch 前に準備された attribution-safe な post-command specialized observation を完了する；
3. specialized evidence が存在する場合、canonical runtime + specialized merge を `events.semantic.jsonl` に行う；
4. provisional live state を信用せず、その canonical stream から final graph を再構築する；
5. `graph.json` と standalone `viewer.html` を書く；
6. live graph を finished とし、final viewer を短時間 serve してから local server を停止する。

Specialized event が一件も到着しなければ、final materialization は runtime-only のままです。

## 自動的に Live Viewer へ入る specialized integrations

| Integration | v0.6.4 Live Viewer への自動配信 |
| --- | --- |
| Claude Code | **Yes**、ExecWeave hooks 設定後 |
| OpenAI Codex | **Yes**、ExecWeave hooks 設定後 |
| Gemini CLI | **Yes**、ExecWeave hooks 設定後 |
| Cursor | **Yes**、ExecWeave hooks 設定後 |
| OpenCode | **Yes**、ExecWeave plugin インストール後 |
| Ollama | **Yes**、認識済み local `ollama serve` launch の場合 |
| llama.cpp | **Yes**、認識済み local `llama-server` launch の場合 |
| vLLM | **Yes**、認識済み local vLLM server launch の場合 |
| LM Studio | **Yes**、`lms server start --port <port>` が成功し、launch 前に endpoint が存在しなかった場合 |
| LiteLLM Proxy | **Yes**、callback 設定済みで proxy が live sidecar を継承した場合 |
| OpenRouter | **No** automatic routing metadata。local client の OS/network activity は観測可能 |

これらの integration は同じ per-run specialized sidecar contract を共有しますが、evidence layer と意味は分離されたままです。Model catalog は Agent が request を発生させた証拠ではありません。Gateway response は特定 OS process が request を発生させた証拠ではありません。欠けた identity は推測しません。

## Terminal Top

`top` は Agent terminal の上に描画しません。元の terminal は Agent 用に interactive のまま保ち、dashboard は同じ localhost live session に別 terminal window から attach します。

```bash
execweave top -- codex
execweave top --open -- codex
```

`--open` は browser Viewer も追加します。Detached dashboard は attach-only client であり、2 つ目の Agent を起動しません。内部 attach URL は localhost HTTP のみに制限されます。

## Network exposure

Live server は次の address のみに bind します。

```text
127.0.0.1
```

`0.0.0.0` には公開されず、LAN 上の別 host から到達する用途ではありません。

Port を明示する場合：

```bash
execweave live --port 8765 --open -- claude
```

Default の port `0` は OS に available local port を選択させます。

## Artifacts

Default run directory：

```text
.execweave/runs/<session-id>/
├── events.jsonl
├── semantic.jsonl
├── events.semantic.jsonl      # specialized evidence がある場合だけ materialize
├── graph.json
└── viewer.html
```

`events.jsonl` は常に runtime-only です。`semantic.jsonl` は raw specialized sidecar で、Agent/IDE、model-runtime、inference-gateway evidence を含められます。Specialized evidence があれば final `graph.json` は `events.semantic.jsonl` から構築され、なければ `events.jsonl` から直接構築されます。

別 directory を指定する場合：

```bash
execweave live --output-dir my-live-run --open -- claude
```

既存の non-empty artifact は overwrite せず拒否されます。

## Provisional live normalization

Live run 中は session がまだ終了していないため、両方の JSONL stream が incomplete の可能性があります。

そのため live normalizer は incremental かつ conservative に動作します。現時点までに観測した runtime process identity を specialized process reference の解決に使用できますが、欠けた identity は推測しません。Specialized event がまだ正規化できない場合でも、live で見えたという理由だけで evidence が強くなることはありません。

Sidecar truncation が発生した場合、provisional materialization は reset され、現在の file から replay されます。Incomplete trailing JSONL record は complete event として扱わず buffer します。Final graph は runtime validation 成功後に canonical merge から再構築されます。

## Automatic model-runtime probe boundary

Automatic model-runtime observation の範囲は意図的に狭くしています。ExecWeave が probe するのは、認識済み local server launch command と local/loopback endpoint だけです。Probe failure は fail-open で、起動した command の結果を変更しません。

Ollama、llama.cpp、vLLM では server 実行中に local model state/catalog を sample できます。LM Studio は異なります。`lms server start` は persistent server を起動する short-lived launcher なので、ExecWeave は launch 前に observation を準備し、既存 compatible endpoint がある場合は今回の session に帰属させません。Launcher が正常終了した場合のみ post-launch catalog を materialize します。

Catalog relation は runtime-specific semantics を維持します。例えば LM Studio の catalog visibility は `ADVERTISES_MODEL` であり、model weights がその時点で memory resident だった証拠ではありません。

## LiteLLM callback boundary

LiteLLM Proxy は custom-callback configuration から `execweave.litellm_callback.execweave_litellm_callback` を一度読み込めます。Proxy が `execweave live` 内で実行されると、`EXECWEAVE_SEMANTIC_SIDECAR` を継承し、whitelist 済み routing/usage metadata だけをその run に書き込みます。

Callback は messages、response content、model parameters、arbitrary metadata、API-key metadata、provider `api_base` を保存しません。Provider identity を model string や URL から推測しません。Run-specific sidecar 環境変数がない場合、callback は no-op です。

LiteLLM config fragment の表示：

```bash
execweave-litellm-callback --print-config
```

## Portable-backend limitations

現在の live runtime layer は portable collector の制約を引き継ぎます。

- process discovery は polling-based；
- 非常に短命な process は見逃される可能性がある；
- filesystem change は process-attributed ではなく session-correlated；
- per-process network inspection は OS visibility と permissions に依存する。

これらの limitation は event attribution metadata に残ります。Live Viewer は non-causal observation を causal edge に upgrade しません。

## Large-session safety

Live update は bounded delta history を使用し、poll ごとに event stream 全体を replay しません。Graph が Viewer safety budget を超えると、live endpoint は compact counts-only payload に切り替わり、browser に unsafe な大型 SVG graph を materialize させずに collection と final canonical artifact generation を継続できます。

## Future native live backends

予定している collector：

- Linux eBPF；
- Windows ETW；
- macOS Endpoint Security。

同じ ExecWeave event semantics を維持しながら completeness、process attribution、runtime overhead を改善することが目標です。

## CI coverage

Repository CI は次をカバーします。

- localhost live-session startup と final artifact generation；
- sequence-numbered snapshot/delta と resynchronization；
- incomplete trailing JSONL record；
- runtime identity ready 前の semantic sidecar arrival；
- semantic sidecar truncation と replay；
- canonical final runtime + specialized rebuild；
- Claude、Codex、Gemini、Cursor、OpenCode の automatic shared-sidecar delivery；
- Ollama、llama.cpp、vLLM の automatic local model-runtime probe と attribution-safe LM Studio launch handling；
- LiteLLM callback の privacy、fail-open behavior、final live-graph materialization；
- 2 つ目の Agent を起動しない detached Top behavior；
- localhost-only Top attach URL；
- clean-wheel install 後の LiteLLM callback setup command。
