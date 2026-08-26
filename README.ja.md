# ExecWeave

[![PyPI](https://img.shields.io/pypi/v/execweave?label=PyPI)](https://pypi.org/project/execweave/)
[![Python](https://img.shields.io/pypi/pyversions/execweave?label=Python)](https://pypi.org/project/execweave/)
[![CI](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg)](https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Irish-kw/ExecWeave?style=flat&label=Stars)](https://github.com/Irish-kw/ExecWeave/stargazers)

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

ExecWeave は、AI エージェントの活動を対話的な execution graph に変換し、observed evidence と inference を明確に分離する、オープンソースの local-first observability プロジェクトです。

> **Event が ground truth であり、Graph は materialized view です。**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

## インストール

ExecWeave は標準的な Python wheel/sdist として PyPI で公開されています。最新リリースは次でインストールできます。

```bash
python -m pip install -U execweave
```

`main` ブランチには、現在の PyPI リリースより新しい修正が含まれる場合があります。最新 mainline build を直接試すには次を実行します。

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

開発用インストール：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Claude Code、OpenAI Codex、Gemini CLI をライブで観測：

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini
```

または完全な artifact pipeline を構築します。

```bash
execweave record --open -- python my_agent.py
```

## パフォーマンスとフットプリント

ExecWeave には、インストール済み wheel から実行される再現可能な package-level overhead benchmark が含まれています。Reference plot は、モデルの quality/cost 比較でよく使われる trade-off 表現に従います。

- **X 軸:** 追加の peak process-tree RSS。低 → 高。
- **Y 軸:** runtime overhead。低 → 高。
- **Bubble 面積:** 1 run あたりの median artifact size。
- **望ましい領域:** 左下。

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference environment: GitHub Actions Ubuntu runner、Intel Xeon Platinum 8573C、4 logical CPUs、Python 3.12.14、`n=7`。

| Profile | Median wall time | Runtime overhead | Additional peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

同じ build から約 **113 KB の wheel** と **198 KB の sdist** が生成されました。インストール後の ExecWeave distribution は約 **849 KB** で、Python と dependency footprint は含みません。

これは意図的に短く、file/process-heavy な **reference microbenchmark** であり、あらゆる workload に対する一般的な性能主張ではありません。未計測 baseline が数百ミリ秒しかないため、百分率の overhead は大きく見えます。容量設計を行う前に、対象ホストと代表的な workload で `execweave-overhead` を再実行してください。

```bash
execweave-overhead \
  --iterations 7 \
  --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

Raw reference data と方法論：[`docs/benchmarks/`](docs/benchmarks/)。

## Evidence layers

ExecWeave は、異なる 4 つの evidence layer を 1 本の trace に平坦化せず、意図的に分離します。

```text
Agent / IDE semantic evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

基盤 telemetry がその主張を裏付ける場合にのみ relationship を causal とします。

## Agent / IDE integrations

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

### Cursor

```bash
execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor
```

Cursor は安定した `tool_use_id` を提供するため、pre/post hooks の間で exact logical tool-call identity を確立できます。

### OpenCode

```bash
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Project-local OpenCode plugin は exact `sessionID + callID` identity を使用し、tool output を意図的に転送しません。

Provider-integrated run では runtime、semantic、correlated artifacts を分離して保持します。Tool → Process bridge は常に保守的な derived evidence のままです。

```text
inferred: true
causal: false
```

曖昧な場合は edge を作りません。

## Inference gateway integrations

OpenRouter と LiteLLM Proxy は local model runtime ではなく `inference_gateway` としてモデル化されます。

```bash
execweave-inference-gateway event \
  --gateway litellm \
  --requested-model assistant \
  --resolved-model azure/gpt-5 \
  --provider-name Azure \
  --deployment-id deployment-west \
  --sidecar gateway.jsonl
```

ExecWeave は requested model、resolved model、routed provider、deployment identity を別々の evidence として保持します。Provider/deployment edge は authoritative metadata が供給された場合にのみ生成され、model-name prefix から推測しません。

Caller が Gateway と Model Runtime の observation 間で明示的な shared identity を持つ場合、layer を潰さずに 2 つの request node をリンクできます。

```bash
execweave-inference-link \
  --gateway litellm \
  --gateway-request-id gw-123 \
  --runtime vllm \
  --runtime-request-id rt-456 \
  --shared-request-id trace-789 \
  --sidecar inference.jsonl
```

`SAME_INFERENCE_REQUEST` は exact identity evidence であり causal evidence ではありません。

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared request ID は保存されず、SHA-256-derived identity hash のみが保存されます。

## Model runtime integrations

現在の model-runtime integrations は **Ollama**、**llama.cpp**、**vLLM**、**LM Studio** です。

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime llamacpp --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime vllm --sidecar model-runtime.jsonl
execweave-model-runtime event --runtime lmstudio --sidecar model-runtime.jsonl
```

OpenAI-compatible runtime は response/usage と model-catalog parsing を共用しつつ、runtime-specific evidence semantics を維持します。Prompt、generated content、reasoning content は保存されません。Sensitive local model path は redaction され、llama.cpp では GGUF path により厳しい redaction を適用します。

LM Studio の model-catalog visibility は `ADVERTISES_MODEL` として表現され、model weights がメモリにロード済みである証拠とは扱いません。

## Runtime evidence

Portable collector は Linux、macOS、Windows で動作します。Linux には syscall-backed `strace` reference backend もあります。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

v0.6.1 以降、child command は実行前に共通の cross-platform launcher resolver で解決されます。Linux/macOS は通常の PATH executable 動作を維持します。Windows は PATH/PATHEXT により `.exe`、`.cmd`、`.bat` を解決し、明示的な `.ps1` launcher は PowerShell で実行します。専用 Windows CI は `cmd.exe` と Windows PowerShell の双方から Codex/Cursor recorder を実行し、完全な Cursor semantic/correlation integration は通常の Windows、macOS、Ubuntu matrix でも継続して検証されます。

Portable filesystem watching は session-correlated であり process-causal ではありません。非常に短命な process は polling interval の間に見逃されることがあります。Linux `strace` path は command 終了後に process-attributed syscall evidence を提供します。

将来の native collector として Linux eBPF、Windows ETW、macOS Endpoint Security を計画しています。

## v0.6.2 safety patch

v0.6.2 は evidence semantics や graph schema 0.1 を変更せず、長時間・high-cardinality session のリソース安全性を強化します。

- filesystem root、user home、users-home parent のような過度に広い recursive filesystem scope は、そのまま recursive observation されません。Process、network、semantic collection は継続できます。
- Standalone/Live Viewer は safety budget（1,500 nodes、4,000 edges、または推定 5,000 SVG elements）を超えると SVG materialization を停止し、browser memory exhaustion を防ぎます。Canonical `graph.json` evidence artifact は完全なままです。
- Viewer layout/fit は任意に大きな array を `Math.min` / `Math.max` に spread せず、node dragging 中の edge redraw は animation-frame throttling されます。
- Live server は byte offset から `events.jsonl` の追加 bytes のみを tail し、in-memory `GraphAccumulator` を incremental に更新します。`/graph.json` polling は全 event history を再生せず、newline がない incomplete trailing JSONL line は buffer されます。
- event-count または aggregate-count だけが変化した場合、full topology redraw をせずに Live stats/edge labels を更新します。Viewer budget 超過後は live `/graph.json` が counts-only compact payload に切り替わりますが、collection と最終 canonical validation/full `graph.json` は継続します。

これは polling + incremental-ingestion の safety patch であり、SSE、SQLite、Rust、Canvas architecture migration ではありません。

## Layered artifacts

Provider-integrated run では次の artifacts を生成できます。

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
└── viewer.correlated.html
```

Derived correlation layer が raw evidence を書き換えることはありません。

## Interactive Viewer

Standalone Viewer は local かつ self-contained です。現在の baseline は pan/zoom、draggable nodes、node/edge inspection、node-type/relation/causal filters、**observed only**、search、evidence-sequence replay、progressive cluster expansion、focused neighborhoods、Saved Views、明示的な edge semantics、Correlation Summary を備えています。

## Graph operations

```bash
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --output causal.graph.json --causal-only
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave graph-condense run.graph.json --output compact.graph.json --threshold 8 --keep-expansion
```

## Security analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

Security finding は evidence limit を明示します。Possible sensitive-file → network path は byte-level exfiltration の証明ではありません。

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## 現在の状態

ExecWeave `main` は現在 **v0.6.2** で、活発に開発されています。

Baseline には runtime collection、graph materialization/querying、standalone/live Viewer、Claude/Codex/Gemini/Cursor/OpenCode semantic integrations、保守的な Tool → Process correlation、OpenRouter/LiteLLM gateway metadata、Ollama/llama.cpp/vLLM/LM Studio runtime metadata、exact Gateway ↔ Model Runtime request identity、公開済み PyPI wheel/sdist packaging、再現可能な overhead benchmarking、cross-platform command-launcher compatibility、large-graph browser safety guards、incremental Live JSONL tail/cache、Python 3.10/3.12 の cross-platform CI が含まれます。

## Privacy

ExecWeave は local-first です。Runtime events、semantic sidecars、graphs、reports、Viewers はデフォルトでローカルに残ります。File contents や raw read/write byte buffers は意図的に収集しません。Native adapters も prompts/transcripts/tool output をデフォルトで避けますが、commands、paths、endpoint metadata、identifiers、model metadata には機密情報が含まれる可能性があります。

Artifacts を共有する前に確認してください。

## ドキュメント

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ja.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ja.md)
- [`Live Graph`](docs/live-graph.ja.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ja.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ja.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ja.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.ja.md)
- [`Cursor Hooks`](docs/cursor-hooks.ja.md)
- [`OpenCode Plugin`](docs/opencode-plugin.ja.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.ja.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.ja.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.ja.md)

## Contributing

特に native OS collectors、追加の Agent/IDE adapters、inference gateways、model runtimes、entity/correlation methods、privacy/redaction、graph UX、performance evaluation への貢献を歓迎します。

## License

[`LICENSE`](LICENSE) を参照してください。