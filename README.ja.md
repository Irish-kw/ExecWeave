# ExecWeave

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

**AI エージェントが実際にマシン上で何をしたのかを見る。**

ExecWeave は、AI エージェントの活動をインタラクティブな execution graph に変換する local-first のオープンソース observability プロジェクトです。Observed evidence と inference を明確に分離します。

> **Event is ground truth. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/execweave-live-demo.webp" alt="ExecWeave Live execution graph" width="100%">
</p>

<!-- execweave-demo:start -->
## この Demo を再現する

上のスクリーンショットは、実際の ExecWeave v0.6.3 live session です。この workload は execution graph の挙動が分かりやすくなるよう、複数の Python modules、JSON/CSV files、tests、file inspection、外向き HTTP requests を意図的に発生させます。

ローカルの Agent CLI を ExecWeave の下で実行します。例：

```bash
execweave live --open -- claude
```

その後、次の workload prompt を Agent に貼り付けます：

```text
Create a small Python project in ./execweave-demo with 8 modules,
generate sample JSON and CSV data, run the program and tests,
inspect the generated files, and fetch example.com plus the GitHub API.
```

同じ workload は `codex`、`gemini`、`cursor`、`opencode` でも利用できます。node、edge、event、process、endpoint の数は OS、Agent version、environment によって変わります。ExecWeave が記録するのは実際に観測された runtime evidence であり、上図は固定の期待 graph ではなく一つの実行例です。
<!-- execweave-demo:end -->

## Installation

ExecWeave は PyPI で正式公開されています。最新の公開 release は次でインストールできます。

```bash
python -m pip install -U execweave
```

`main` は現在の PyPI release より新しい patch を含む場合があります。最新 mainline を直接試す場合：

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

開発用：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Live OS-runtime telemetry は **任意のローカル command** に使用できます。以下は whitelist ではなく例です：

```bash
# Agent / IDE CLI
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
execweave live --open -- cursor
execweave live --open -- opencode

# 任意のローカルプログラム
execweave live --open -- python my_agent.py

# ExecWeave から起動するローカル model runtime
execweave live --open -- ollama serve
```

`execweave live` は、起動した command tree の process / file / network evidence をリアルタイム表示します。Agent semantic hooks、model-runtime API metadata、inference-gateway routing metadata は **現在 Live Viewer に自動注入されません**。

#### Live capability matrix

| Integration | Direct OS-runtime live | Specialized metadata | Auto in Live Viewer |
| --- | --- | --- | --- |
| Claude Code | Yes | `execweave-claude-record` / hooks | No |
| OpenAI Codex | Yes | `execweave-codex-record` / hooks | No |
| Gemini CLI | Yes | `execweave-gemini-record` / hooks | No |
| Cursor | Yes | `execweave-cursor-record` / hooks | No |
| OpenCode | Yes | `execweave-opencode-record` / plugin | No |
| Ollama | Yes, ExecWeave から起動する場合（例: `ollama serve`） | `execweave-model-runtime event/probe --runtime ollama` | No |
| llama.cpp | Yes, ローカル server を ExecWeave から起動する場合 | `execweave-model-runtime event/probe --runtime llamacpp` | No |
| vLLM | Yes, ローカル server を ExecWeave から起動する場合 | `execweave-model-runtime event/probe --runtime vllm` | No |
| LM Studio | ExecWeave から起動したローカル process のみ。既存 server には attach しません | `execweave-model-runtime event/probe --runtime lmstudio` | No |
| LiteLLM Proxy | Yes, ローカル proxy を ExecWeave から起動する場合 | `execweave-inference-gateway event --gateway litellm` | No |
| OpenRouter | Remote service 自体は direct live 不可。ローカル client/Agent を live してください | `execweave-inference-gateway event/generation --gateway openrouter` | No |

Ollama がすでにバックグラウンドで動作中なら、`execweave-model-runtime probe --runtime ollama` で loaded-model state を snapshot できます。OpenRouter では `live` がローカル client と network activity を観測し、gateway routing/usage metadata は別の evidence layer のままです。

<!-- v0.6.3-live -->
### v0.6.3 ライブ可観測性

同じ live session をブラウザまたは Terminal で確認できます：

```bash
execweave top -- codex          # Terminal dashboard
execweave top --open -- codex   # Terminal + Web Viewer
```

Live 更新は増分 snapshot/delta と有界履歴を使用し、graph 全体の再構築・再送を繰り返しません。Live と standalone Viewer は、設定を保持する Dark/Light 切り替えに対応します。Linux では非常に大きな recursive filesystem scope を事前に確認し、inotify watch 容量が不足する場合は自動的に polling へフォールバックするため、inotify watch exhaustion で session 全体が停止しません。

`live` は汎用 OS-runtime view であり integration whitelist ではありません。Agent semantic、model-runtime、gateway metadata は分離された evidence layer のままで、v0.6.3 では Live Viewer に自動注入されません。

`execweave-scalability` で graph scalability benchmark を再現でき、CI は 10k、100k、1M synthetic events を検証します。

#### Scalability benchmark

GitHub Actions 上の incremental `GraphAccumulator` synthetic workload の reference result（`retain_event_ids=False`）：

| Events | Apply time | Throughput | Nodes | Edges | Apply RSS Δ | Snapshot |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10k | 0.114 s | 87,681 ev/s | 10,001 | 10,000 | 35.9 MiB | 8.5 MiB |
| 100k | 0.654 s | 152,816 ev/s | 10,001 | 10,000 | 25.8 MiB | 8.6 MiB |
| **1M** | **6.087 s** | **164,273 ev/s** | **10,001** | **10,000** | **23.5 MiB** | **8.6 MiB** |

**1,000,000 events** 時点で、incremental in-memory graph は raw event IDs を重複保持しません。Raw evidence は materialized graph とは分離されたままです。この benchmark は graph accumulation と snapshot materialization を測定するもので、end-to-end collector や browser throughput の測定ではありません。

## Performance / footprint

Reference benchmark は editable checkout ではなく、実際にインストールした wheel から実行されます。X 軸は追加 peak process-tree RSS、Y 軸は runtime overhead、bubble 面積は run ごとの median artifact size です。どちらの軸も低→高で、左下が望ましい領域です。

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference environment: GitHub Actions Ubuntu runner, Intel Xeon Platinum 8573C, 4 logical CPUs, Python 3.12.14, `n=7`.

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

同じ build で wheel は約 **113 KB**、sdist は約 **198 KB**、インストール後の ExecWeave distribution は約 **849 KB** でした。Python と dependency footprint は含みません。

これは短時間かつ file/process-heavy な **reference microbenchmark** であり、すべての Agent workload に対する一般的な overhead の主張ではありません。Target host と実 workload で再実行してください。

```bash
execweave-overhead --iterations 7 --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Raw data / methodology: [`docs/benchmarks/`](docs/benchmarks/)。

## Evidence layers

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

基礎 telemetry が直接支える場合だけ relationship を causal とします。

## Integrations

Agent / IDE: Claude Code, OpenAI Codex, Gemini CLI, Cursor, OpenCode.

Inference Gateway: OpenRouter, LiteLLM Proxy. Requested model / resolved model / provider / deployment は別の evidence として保持し、authoritative metadata がない場合は routing fact を推測しません。

Model Runtime: Ollama, llama.cpp, vLLM, LM Studio. Prompt / generated content / reasoning content は保存しません。Sensitive local model path は redact されます。LM Studio catalog は `ADVERTISES_MODEL` として扱い、catalog visibility を loaded-memory evidence とみなしません。

Tool → Process correlation は常に：

```text
inferred: true
causal: false
```

ambiguous / no-match の場合は edge を作りません。

Gateway と Model Runtime の双方に明示的な shared request identity がある場合だけ、`SAME_INFERENCE_REQUEST` を作れます：

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared ID は保存せず、SHA-256-derived identity hash のみ保持します。

## Runtime evidence

Portable collector は Linux / macOS / Windows で動作し、Linux には syscall-backed `strace` reference backend もあります。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

v0.6.1 以降、すべての recorder は child command を起動する前に共通の cross-platform launcher resolver を使用します。Linux / macOS は通常の PATH executable behavior を維持します。Windows は PATH/PATHEXT に従って `.exe`、`.cmd`、`.bat` を解決し、明示的な `.ps1` は PowerShell 経由で起動します。専用 Windows CI では `cmd.exe` と Windows PowerShell の両方から Codex / Cursor recorder を実際に起動し、通常の Windows / macOS / Ubuntu matrix でも Cursor semantic/correlation integration を継続して検証します。

Portable filesystem observation は process-causal ではなく session-correlated です。Future native collectors は Linux eBPF、Windows ETW、macOS Endpoint Security を予定しています。

## v0.6.3 Safety Patch

v0.6.3 は長時間・high-cardinality session の resource safety を強化しますが、**evidence semantics と graph schema 0.1 は変更しません**。

- filesystem root、user home、users-home parent など過度に広い recursive scope では recursive filesystem observation をそのまま開始せず、process / network / semantic collection は継続できます。
- Standalone / Live Viewer は safety budget（1,500 nodes、4,000 edges、または推定 5,000 SVG elements）を超えると SVG materialization を停止し、browser memory exhaustion を避けます。Canonical `graph.json` evidence artifact は完全なままです。
- Viewer layout/fit は巨大 array を `Math.min` / `Math.max` に spread せず、node drag 中の edge redraw は animation-frame throttling されます。
- Live server は byte offset から `events.jsonl` の追記分だけを tail し、in-memory `GraphAccumulator` で incrementally update します。各 `/graph.json` request で全 event history を replay せず、newline がまだない trailing partial JSONL line は buffer されます。
- event count / aggregate count だけの変化では stats/edge labels のみ更新し、full topology redraw を行いません。Viewer budget 超過後の live `/graph.json` は counts-only compact payload になり、collection と session 終了時の canonical validation/full `graph.json` は維持されます。

これは polling + incremental ingestion の Safety Patch であり、SSE、SQLite、Rust、Canvas への architecture migration ではありません。

## Viewer / Graph / Security

Standalone Viewer は local self-contained で、pan/zoom、inspection、filters、**observed only**、search、Timeline replay、cluster expansion、focused neighborhood、Saved Views、明示的な edge semantics を備えます。

```bash
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave analyze run.graph.json --output analysis.json
```

Security findings は evidence limit を維持し、possible sensitive-file → network path を byte-level exfiltration の証明として扱いません。

## Current status

ExecWeave `main` は現在 **v0.6.3**。Runtime collection、execution graph、5 種の Agent/IDE integration、OpenRouter/LiteLLM、Ollama/llama.cpp/vLLM/LM Studio、exact Gateway ↔ Runtime identity、公開済み PyPI packaging、reference overhead benchmark、cross-platform command-launcher compatibility、large-graph browser safety guards、incremental Live JSONL tail/cache、cross-platform CI が baseline に含まれます。

## Privacy

ExecWeave は local-first です。Runtime events、semantic sidecars、graphs、reports、Viewers は既定でローカルに残ります。File content や raw read/write buffers を意図的に収集しません。Artifact 共有前に command、path、endpoint、identifier、model metadata を確認してください。

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ja.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ja.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ja.md)
- [`Inference Gateway`](docs/inference-gateway.ja.md)
- [`Model Runtime`](docs/model-runtime.ja.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.ja.md)

## License

[`LICENSE`](LICENSE) を参照してください。