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

## Installation

ExecWeave v0.6.0 は標準 Python wheel / sdist としてパッケージ化済みです。GitHub 側は PyPI-ready で、最初の Trusted Publisher release までは GitHub から直接 pip install できます。

```bash
python -m pip install "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

開発用：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

最初の PyPI release 後は：

```bash
python -m pip install execweave
```

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

Portable filesystem observation は process-causal ではなく session-correlated です。Future native collectors は Linux eBPF、Windows ETW、macOS Endpoint Security を予定しています。

## Viewer / Graph / Security

Standalone Viewer は local self-contained で、pan/zoom、inspection、filters、**observed only**、search、Timeline replay、cluster expansion、focused neighborhood、Saved Views、明示的な edge semantics を備えます。

```bash
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave analyze run.graph.json --output analysis.json
```

Security findings は evidence limit を維持し、possible sensitive-file → network path を byte-level exfiltration の証明として扱いません。

## Current status

ExecWeave は現在 **v0.6.0**。Runtime collection、execution graph、5 種の Agent/IDE integration、OpenRouter/LiteLLM、Ollama/llama.cpp/vLLM/LM Studio、exact Gateway ↔ Runtime identity、PyPI-ready packaging、reference overhead benchmark、cross-platform CI が baseline に含まれます。

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
