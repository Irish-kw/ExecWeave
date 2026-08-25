# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a>
</p>

**看见 AI Agent 在你的电脑上实际做了什么。**

ExecWeave 是开源、local-first 的 observability 项目，将 AI Agent 活动转换为互动式 execution graph，同时明确区分 observed evidence 与 inference。

> **Event 是 ground truth；Graph 是 materialized view。**

## 安装

ExecWeave 已正式发布到 PyPI。安装最新已发布版本：

```bash
python -m pip install -U execweave
```

`main` 可能比当前 PyPI release 更新。若要直接测试最新 mainline：

```bash
python -m pip install --upgrade --force-reinstall "execweave @ git+https://github.com/Irish-kw/ExecWeave.git@main"
```

开发安装：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 性能与空间占用

Reference benchmark 从实际安装的 wheel 运行。图采用常见的 trade-off 表达：X 轴为额外 peak process-tree RSS（低→高），Y 轴为 runtime overhead（低→高），bubble 面积表示每次 run 的 median artifact size；左下角更理想。

![ExecWeave overhead trade-off](docs/benchmarks/v0.6.0-github-actions.svg)

Reference 环境：GitHub Actions Ubuntu runner、Intel Xeon Platinum 8573C、4 logical CPUs、Python 3.12.14、`n=7`。

| Profile | Median wall time | Runtime overhead | 额外 peak RSS | Median artifacts/run |
| --- | ---: | ---: | ---: | ---: |
| ExecWeave OFF | 236.221 ms | 0.0% | 0.0 MB | 0 KB |
| Portable ON | 391.580 ms | 65.768% | 27.852 MB | 741.355 KB |
| Strace ON | 1226.076 ms | 419.038% | 37.653 MB | 572.838 KB |

同一 build 产生约 **113 KB wheel**、**198 KB sdist**；安装后的 ExecWeave distribution 本身约 **849 KB**，不包含 Python 与 dependency footprint。

这是一个很短、file/process-heavy 的 **reference microbenchmark**，不是所有 Agent workload 的普遍 overhead 结论。部署或容量评估前应在目标主机与真实 workload 上重新运行：

```bash
execweave-overhead --iterations 7 --strace auto \
  --output-json benchmark-results.json \
  --output-svg benchmark-overhead.svg
```

原始数据与方法：[`docs/benchmarks/`](docs/benchmarks/)。

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

只有底层 telemetry 能直接支持时，relationship 才会标记为 causal。

## Integrations

Agent / IDE：Claude Code、OpenAI Codex、Gemini CLI、Cursor、OpenCode。

Inference Gateway：OpenRouter、LiteLLM Proxy。Requested model、resolved model、provider、deployment 分开保存，没有 authoritative metadata 时不推测 routing facts。

Model Runtime：Ollama、llama.cpp、vLLM、LM Studio。Prompt、generated content、reasoning content 不保存；敏感 local model path 会 redaction。LM Studio catalog 使用 `ADVERTISES_MODEL`，不会把 catalog visibility 当成 loaded-memory evidence。

Tool → Process correlation 始终保持：

```text
inferred: true
causal: false
```

ambiguous / no-match 不建立 edge。

若 Gateway 与 Model Runtime 拥有明确 shared request identity，可建立 `SAME_INFERENCE_REQUEST`：

```text
identity_exact: true
inferred: false
causal: false
```

Raw shared ID 不落盘，仅保存 SHA-256-derived identity hash。

## Runtime evidence

Portable collector 支持 Linux、macOS、Windows；Linux 另有 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
```

从 v0.6.1 开始，所有 recorder 在启动 child command 前都会使用共享的跨平台 launcher resolver。Linux / macOS 保持正常 PATH executable 行为；Windows 通过 PATH/PATHEXT 正确解析 `.exe`、`.cmd`、`.bat`，显式 `.ps1` 则交给 PowerShell 启动。专用 Windows CI 会从 `cmd.exe` 和 Windows PowerShell 实际启动 Codex / Cursor recorder；完整 Cursor semantic/correlation integration 同时由 Windows、macOS、Ubuntu matrix 覆盖。

Portable filesystem observation 是 session-correlated，不是 process-causal。未来 native collectors 包括 Linux eBPF、Windows ETW、macOS Endpoint Security。

## Viewer / Graph / Security

Standalone Viewer 完全 local、自包含，支持 pan/zoom、inspection、filters、**observed only**、search、Timeline replay、cluster expansion、focused neighborhood、Saved Views 与明确 edge semantics。

```bash
execweave graph-summary run.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave analyze run.graph.json --output analysis.json
```

Security findings 会保留 evidence limits；possible sensitive-file → network path 不等于 byte-level exfiltration。

## 当前状态

ExecWeave `main` 当前为 **v0.6.1**，baseline 已包含 runtime collection、execution graph、五种 Agent/IDE integrations、OpenRouter/LiteLLM、Ollama/llama.cpp/vLLM/LM Studio、exact Gateway ↔ Runtime identity、已发布的 PyPI packaging、reference overhead benchmark、跨平台 command launcher compatibility 与 cross-platform CI。

## 隐私

ExecWeave 是 local-first。Runtime events、semantic sidecars、graphs、reports 与 Viewers 默认留在本机。项目不刻意采集 file content 或 raw read/write buffers；分享 artifacts 前请检查 command、path、endpoint、identifier 与 model metadata。

## 文档

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-CN.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-CN.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-CN.md)
- [`Inference Gateway`](docs/inference-gateway.zh-CN.md)
- [`Model Runtime`](docs/model-runtime.zh-CN.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)
- [`Security Analysis`](docs/security-analysis.zh-CN.md)

## License

请参阅 [`LICENSE`](LICENSE)。
