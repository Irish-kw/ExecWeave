> Codex + AGY 与其余受支持 provider 现已完成 conversation history、dashboard graph、raw event 与 file target 对齐。

# ExecWeave

<!-- i18n-nav:start -->
<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.ko.md">한국어</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.de.md">Deutsch</a> |
  <a href="README.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

<p align="center">
  <a href="https://pypi.org/project/execweave/"><img src="https://img.shields.io/pypi/v/execweave" alt="PyPI"></a>
  <a href="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml"><img src="https://github.com/Irish-kw/ExecWeave/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue" alt="License"></a>
</p>

**看清 AI Agent 在你的机器上究竟做了什么。**

ExecWeave 是一个 source-available、local-first 的可观测性项目，把 AI Agent 活动转换成交互式 execution graph，并明确区分 observed evidence、provider 明确提供的内容与 derived inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

本 README 对应 **v0.8.9**。

## 为什么是 ExecWeave

- **一个本地 inspection surface。** Live run、完成后的 run 与 standalone `viewer.html` 使用同一套 dashboard renderer，把 graph、logs、conversation 与 node details 放在一个界面里。
- **Evidence-aware。** Direct observation、identity link、保守 inference 与 causal claim 不会被混成同一种关系。
- **理解 Provider，但不虚构 Provider 没提供的行为。** ExecWeave 只使用 provider 真正暴露的 routing / identity evidence；缺失的证据就保持缺失。
- **不只支持特定 Agent。** OS-runtime telemetry 可以包住任意本地命令；有 provider adapter 时再补上更强的 semantic evidence。

## 安装

从 PyPI 安装最新已发布版本：

```bash
python -m pip install -U execweave
```

开发安装：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 60 秒快速开始

Live OS-runtime telemetry 可用于**任意本地命令**。下面的 Agent/runtime 名称只是示例，不是白名单。

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **首次出现 Hook 权限提示时请同意。** 第一次使用 provider integration 时，Agent/IDE 可能会询问是否允许 ExecWeave 启用本地 Hook；请选择 **Allow / Yes**。如果不同意，OS-runtime telemetry 仍可能工作，但 provider-level 的 tool、model、conversation 与 supplied-content observability 会降低或不可用。

Google Antigravity 当前使用 `agy` CLI；ExecWeave 也接受 `antigravity` 作为 friendly alias 并解析到 `agy`。Cursor 的 `execweave live --open -- cursor` 会先寻找普通 PATH launcher，找不到时在 macOS / Windows 尝试标准 Cursor desktop application binary。

建立 finalized run artifacts：

```bash
execweave record --open -- python my_agent.py
```

如果希望 Agent 保持在原 terminal 里交互，同时打开 detached overview：

```bash
execweave top -- codex
```

## Dashboard

ExecWeave 不会在 run 结束时换成另一套 viewer；Live、finished 与 standalone viewing 都沿用同一个 dashboard model。

- **Execution graph：** 展示 agents、processes、files、network endpoints、tools、model/runtime entities 与受支持的 semantic relations。
- **Conversation rounds：** 最新一轮可直接阅读，较旧轮次仍可分别展开，不会被新回答覆盖。
- **Node details：** process node 展示 command / PID context，file node 展示 path / history context，network node 展示 endpoint / process context。
- **Large-run readability：** 每种类型超过预算后只保留最新成员直接绘制，旧成员收进可检查 aggregate。阈值由 `--fold-budget N` 控制。
- **Selection clarity：** multi-agent layout 保持稳定 root / child hierarchy，选中 agent 时淡化无关 edges。

### v0.8.3 Dashboard 变化

v0.8.3 的重点是让 dense、multi-round run 更易读，同时不改变 raw evidence：

- conversation panel 改为以 round 为单位，不再把旧 prompt 与新 reply 错配；
- 用户明确设置的展开 / 收起状态会跨 800 ms Live refresh 保留；
- subagent response 会继续归属于真正产生它的 agent；
- 选中 process、file、network 后不再出现空白 detail panel；
- 高基数 node type 会按可配置预算折叠，避免 graph 被数百或数千个 node 淹没；
- lifecycle return edge 不再扭曲 root / child rank，共享 tool/model traffic 使用更清晰的 routed geometry。

这些都是 presentation-layer change。Raw graph evidence 不变，Live、finished 与 `viewer.html` 仍共享同一 renderer。

## 支持的 Integrations

| Integration | 在 ExecWeave 下启动时的 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity supplied hook content + provider 明确暴露时的 exact subagent results |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcripts + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 可验证时的 conversation/subagent routing |
| Cursor | Yes | native hooks + 可获得时的 exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity supplied plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 仅限本地 process 由 ExecWeave 启动 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 已配置 proxy 且由 ExecWeave 启动时为 Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | 观察本地 client，而不是远端 service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

Cursor `tool_use_id`、Codex rollout thread identity、OpenCode `sessionID + callID` 这类 stable provider identifier 可以证明 logical provider identity，但它们不是 OS PID。只有 provider 明确暴露 route、delegation 或 result 时，cross-agent content 才会显示。若 gateway / local runtime 只提供 root request/response，ExecWeave 就保持 root-only，不会虚构 subagent 或 hidden routing。

OpenRouter `exchange` 是 caller-supplied request+response evidence，不是 transparent wire interception。LiteLLM Proxy 在当前 baseline 仍是较窄的 metadata-oriented integration。Google CLI 使用场景应改用 Antigravity (`agy`)。

## Evidence model

ExecWeave 不会把所有 signal 压成一条 trace，而是维持 evidence layer 边界：

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底层 telemetry 真正支持 causal claim 时，relationship 才会标成 causal。保守的 Tool → Process bridge 会保持 derived evidence 标记：

```text
inferred: true
causal: false
```

Gateway 与 Model Runtime 之间 exact shared request identity 代表 identity evidence，不代表 causal evidence：

```text
identity_exact: true
inferred: false
causal: false
```

存在歧义时就不建立 edge。

### Full-fidelity supplied content

从 **v0.6.9** 起，受支持的 integration point 可以把 provider / hook / API 明确提供的完整值保存在本地 SHA-256 content-addressed store，而 semantic event stream 只保留 reference：

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

根据 integration，不同保存内容可能包括 prompt/message、request/response object、tool input/result、assistant response、上游明确暴露的 reasoning/thinking text、shell/MCP output，以及 provider hook 提供的 file content。

`complete_from_source: true` 只表示 ExecWeave 完整保存了该 integration point 提供的值；**不代表**看到了 hidden model state、provider 未暴露的内部阶段、未观察到的 final wire request，或没有被拦截的 bytes。

## 常用命令

### Agent / IDE recorders

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateways 与 model runtimes

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl

execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` 是 response-only evidence；`exchange` 保存 caller-supplied request+response object，不会宣称 transparent interception。Runtime catalog relation 保留各自来源语义：`LOADED_MODEL`、`SERVES_MODEL`、`ADVERTISES_MODEL` 不可互换。LM Studio catalog visibility 仍是 `ADVERTISES_MODEL`，不能视为 weights 已在 memory 中 resident 的证明。

### Runtime、graph、security 与 integrity

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
execweave analyze run.graph.json --output analysis.json
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Security finding 的 evidence grade 与 severity 分开。现有 grade 为 `A`、`B`、`C`、`D`、`U`；它们是 evidence-strength category，不是 probability 或 trust score。Rule pack 是 bounded、explainable 的 single-edge observation policy，不会执行 third-party code，也不能证明 byte-level exfiltration。

## Run artifacts

Provider-integrated run 可能包含：

```text
.execweave/runs/<run-id>/
├── events.jsonl
├── graph.json
├── viewer.html
├── semantic.jsonl
├── content/sha256/...
├── conversations.md
├── conversations.json
├── events.semantic.jsonl
├── graph.semantic.json
├── viewer.semantic.html
├── events.correlated.jsonl
├── graph.correlated.json
├── viewer.correlated.html
└── integrity.json            # after an explicit seal
```

Derived correlation 不会覆盖 raw runtime 或 provider sidecar evidence。

## 限制与隐私

- Portable collector 可在 Linux、macOS、Windows 运行。Portable filesystem observation 是 session-correlated，不是 process-causal；polling 也可能漏掉非常短命的 activity。
- Linux 另有 syscall-backed `strace` reference backend，可为受支持执行提供更强的 process-attributed syscall evidence。
- Native Linux eBPF、Windows ETW、macOS Endpoint Security collector 仍是 planned work，不是当前已经完成的能力声明。
- Full-fidelity provider content 可能完整保存 prompt、tool value、model response、shell output 或 supplied file 内的 secret。ExecWeave **不是**通用 secret scanner 或 content redactor。
- Conversation isolation 是 attribution/display rule，不是 redaction boundary。若 provider 明确把内容 route 到其他 agent，参与端点仍可能合理地看到该内容。
- Commands、paths、endpoints、identifiers、model metadata、prompts、tool values 与 content blobs 都可能敏感；分享前请检查整个 run directory。
- Local integrity seal 可检测相对于 manifest 的文件变化，但如果 evidence 与 manifest 都位于同一个可写 trust boundary，就不能把它描述成 adversary-resistant tamper evidence。

## 性能

ExecWeave 包含 bounded filesystem/viewer protection、incremental Live JSONL tailing、large-graph safety guard、detached Top，以及针对已配置 provider integration 的 provisional live sidecar。

可复现的 incremental `GraphAccumulator` reference result 在文档化 GitHub Actions workload 上、1M synthetic events 时达到 **164,273 ev/s**。这是 graph-accumulation benchmark，不是 end-to-end collector / browser throughput。

请在有代表性的 host/workload 上运行 package-level benchmark：

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data 与 methodology 位于 [`docs/benchmarks/`](docs/benchmarks/)。

## 文档

| 区域 | 文档 |
| --- | --- |
| Runtime 与 graph | [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.md) · [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.md) · [`Live Graph`](docs/live-graph.md) · [`Semantic Telemetry`](docs/semantic-telemetry.md) |
| Agent / IDE integrations | [`Claude Code`](docs/claude-code-hooks.md) · [`OpenAI Codex`](docs/codex-hooks.md) · [`Google Antigravity`](docs/antigravity-hooks.md) · [`Cursor`](docs/cursor-hooks.md) · [`OpenCode`](docs/opencode-plugin.md) |
| Gateways 与 runtimes | [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.md) · [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.md) |
| Trust 与 analysis | [`Runtime Threat Model`](docs/runtime-threat-model.md) · [`Evidence Grades`](docs/evidence-grades.md) · [`Rule Packs`](docs/rule-packs.md) · [`Run Integrity`](docs/run-integrity.md) · [`Security Analysis`](docs/security-analysis.md) |
| 性能 | [`Benchmarks`](docs/benchmarks/README.md) |

## 贡献

欢迎围绕 native OS collector、Agent/IDE adapter、inference gateway、model runtime、evidence/correlation method、privacy/redaction、graph UX、multi-agent conversation attribution 与 performance evaluation 提交贡献。

## 许可证

从 v0.6.8 起，ExecWeave 采用 **PolyForm Noncommercial License 1.0.0**。根据许可条款可进行非商业使用、修改与再分发；商业使用需要与 licensor 另行取得书面 commercial license。详见 [`LICENSE`](LICENSE)。
