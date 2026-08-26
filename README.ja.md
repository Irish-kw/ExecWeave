# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a>
</p>

**AI エージェントが実際にマシン上で何をしたのかを見る。**

ExecWeave は、AI エージェントの活動をインタラクティブな execution graph に変換する local-first のオープンソース observability プロジェクトです。Observed evidence と inference を明確に分離します。

> **Event is ground truth. The graph is a materialized view.**

<p align="center">
  <img src="docs/assets/execweave-viewer.png" alt="ExecWeave Live execution graph" width="100%">
</p>

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

Claude Code、OpenAI Codex、Gemini CLI をライブで観察：

```bash
# Claude Code
execweave live --open -- claude

# OpenAI Codex
execweave live --open -- codex

# Gemini CLI
execweave live --open -- gemini

# Cursor
execweave live --open -- cursor
```

<!-- v0.6.3-live -->
### v0.6.3 ライブ可観測性

同じ live session をブラウザまたは Terminal で確認できます：

```bash
execweave top -- codex          # Terminal dashboard
execweave top --open -- codex   # Terminal + Web Viewer
```

Live 更新は増分 snapshot/delta と有界履歴を使用し、graph 全体の再構築・再送を繰り返しません。Live と standalone Viewer は、設定を保持する Dark/Light 切り替えに対応します。Linux では非常に大きな recursive filesystem scope を事前に確認し、inotify watch 容量が不足する場合は自動的に polling へフォールバックするため、inotify watch exhaustion で session 全体が停止しません。

`execweave live --open -- cursor` は汎用 runtime telemetry に対応します。Cursor semantic hooks と保守的な tool/process correlation が必要な場合は `execweave-cursor-record --open -- cursor` を使用してください。

`execweave-scalability` で graph scalability benchmark を再現でき、CI は 10k、100k、1M synthetic events を検証します。


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