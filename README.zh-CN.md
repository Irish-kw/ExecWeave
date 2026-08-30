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

**看清 AI Agent 在你的机器上究竟做了什么。**

ExecWeave 是一个 source-available、local-first 的可观测性项目，把 AI Agent 活动转换为交互式 execution graph，并明确区分 observed evidence、provider content 与 derived inference。

> **Event 是 ground truth；Graph 是 materialized view。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave animated live demo" width="100%">
</p>

## 安装

从 PyPI 安装最新已发布的 wheel/sdist：

```bash
python -m pip install -U execweave
```

当前正式版本是 **v0.7.9**。

开发安装：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 快速开始

Live OS-runtime telemetry 可用于**任何本地命令**。下面的 Agent/runtime 名称只是示例，并不是白名单。

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- ollama serve
execweave live --open -- python my_agent.py
```

> **第一次出现 Hook 权限提示时请同意。** 首次使用 provider integration 时，Agent/IDE 可能会询问是否允许 ExecWeave 启用本地 Hook；请选择 **Allow / Yes**。如果不同意，OS-runtime telemetry 仍可能工作，但 provider-level 的 tool、model 与 supplied-content observability 会降低或不可用。

Google Antigravity 当前使用 `agy` CLI；ExecWeave 也接受 `antigravity` 作为友好 alias 并自动解析为 `agy`。Cursor 的 `execweave live --open -- cursor` 会先查找 PATH launcher，找不到时在 macOS/Windows 自动尝试标准 Cursor desktop application binary。

或构建 finalized artifact pipeline：

```bash
execweave record --open -- python my_agent.py
```

`execweave top -- codex` 会让 Agent 保持在启动 terminal 中交互，并根据主机环境打开或附加 detached Top dashboard。

**v0.7.9 — 运行中与运行后，同一套 Dashboard。** Live、完成后的画面与 viewer.html 原本是同一批证据的三种渲染，而且运行结束时会去抓另一份文件覆盖读者正在看的页面。现在只有一套 shell：完成只让当前画面转为结束状态，viewer.html 就是同一套 Dashboard 的离线存档。选取一个 agent 只回答一个问题就停——root 显示它的 Prompt 与 Final response，subagent 显示 Task、provider 有公开明文时的 Thinking、以及 Response——而 process、file、网络端点或 model 完全不显示任何对话，因为对话属于 agent。provider 加密的 turn 读作「已观测但未公开明文」，而不是从未记录；provider 加在每个 subagent 前面的内容永远不会被当成某个 agent 的交办；引用了 routing 字眼的回答也完整保留。每个 agent 各自拥有的 provider-neutral、agent-local multi-agent conversation 会跨该次运行写出的所有存档聚合，因此被记录多次的 agent 仍然显示得出它说了什么。发布前的检查会用真实浏览器把出货的 Dashboard 在 live 与 finished 两种状态下走过每一种可操作的选取。

统一 dashboard 把 execution graph、logs 与 conversation records 放进同一条 inspection flow。Finalized run 会生成 `conversations.md` 与 `conversations.json`，经过验证的 provider transcript 也会复制进 run-local SHA-256 content store。Claude Code、OpenAI Codex、Cursor、OpenCode 与 Google Antigravity 都依据各自实际暴露的 evidence 强度建立 multi-agent trace；如果 gateway 或 local runtime 只提供 root request/response，ExecWeave 就只显示 root conversation，不会虚构 subagent 或 hidden routing。

## v0.6.9：full-fidelity observability 与明确的 evidence boundary

v0.6.9 不再只保留精简 metadata。当受支持的 integration point 明确提供内容时，ExecWeave 可以把**来源实际提供的完整值**保存到本地 SHA-256 content-addressed store，而 semantic event stream 只保留 reference。

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

根据 adapter 与上游 hook/API surface 的不同，保存内容可包含 prompt/message、model request/response object、tool input/result、assistant response、上游明确暴露的 reasoning/thinking text、shell/MCP output，以及 provider hook 提供的 file content。

`complete_from_source: true` 只表示 ExecWeave 完整保存了该 integration point 提供的值；**不代表** ExecWeave 看到了 hidden model state、provider 没有暴露的内部阶段、未观察到的最终 wire request，或任何没有被拦截/提供的 bytes。

Full fidelity 同时改变 privacy boundary：如果 application-level secret 被嵌入 content，它会一起保存。已知 transport credential 只会在 adapter 明确定义的 provider-metadata projection 中被过滤；ExecWeave **不是**通用 secret scanner 或 content redactor。

### 支持的 semantic / inference surface

| Integration | 在 ExecWeave 下启动时的 OS-runtime observation | Specialized evidence |
| --- | --- | --- |
| Claude Code | Yes | native hooks + full-fidelity hook content + provider 明确暴露的 subagent result |
| OpenAI Codex | Yes | lifecycle hooks + validated rollout transcript + agent-local task/message/final-response routing |
| Google Antigravity / Antigravity CLI | Yes | passive native hooks + 可验证时的 conversation/subagent routing |
| Cursor | Yes | native hooks + 可获得时的 exact subagent task/summary routing |
| OpenCode | Yes | project plugin + session/task routing + full-fidelity plugin content |
| Ollama | Yes | `execweave-model-runtime event/exchange/probe --runtime ollama` |
| llama.cpp | Yes | `execweave-model-runtime event/exchange/probe --runtime llamacpp` |
| vLLM | Yes | `execweave-model-runtime event/exchange/probe --runtime vllm` |
| LM Studio | 仅当本地 process 由 ExecWeave 启动 | `execweave-model-runtime event/exchange/probe --runtime lmstudio` |
| LiteLLM Proxy | 已配置 proxy 且由 ExecWeave 启动时为 Yes | metadata-oriented gateway callback/event integration |
| OpenRouter | 观察本地 client，而不是远端 service process | `execweave-inference-gateway event/exchange/generation --gateway openrouter` |

OpenRouter `exchange` 是 caller-supplied request+response evidence，不是透明 wire interception。LiteLLM Proxy 在当前 baseline 仍是范围更窄的 metadata-oriented integration。Provider-neutral conversation projection 不会把缺失的 provider evidence 升级为虚构 agent relationship。

## Evidence layers

ExecWeave 不把所有信号压成一条 trace，而是保留不同 evidence layers：

```text
Agent / IDE semantic + supplied content evidence
          ↓
Inference gateway / routing evidence
          ↓
Model runtime / inference-server evidence
          ↓
OS runtime evidence: process / file / network
```

只有底层 telemetry 真正支持 causal claim 时，relationship 才会标为 causal。Tool → Process bridge 仍是保守的 derived evidence：

```text
inferred: true
causal: false
```

存在歧义就不建立 edge。Gateway 与 Model Runtime 之间的 exact shared request identity 仍只是 identity evidence，而不是 causal evidence：

```text
identity_exact: true
inferred: false
causal: false
```

## Agent / IDE integrations

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude

execweave-codex-hook --print-config
execweave-codex-record --open -- codex

execweave-antigravity-hook --print-config
execweave-antigravity-record --open -- antigravity

execweave-cursor-hook --print-config
execweave-cursor-record --open -- cursor

execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

Provider-integrated recorder 会把 raw runtime、semantic、correlated 与 conversation artifacts 分开保存。Cursor `tool_use_id`、Codex rollout thread identity、OpenCode `sessionID + callID` 这类 stable provider identifier 能证明 provider 内部的 logical identity，但它们不是 OS PID。只有 provider 明确暴露 route、delegation 或 result 时，跨 agent content 才会显示。Legacy Gemini CLI hook entry points 仍保留给现有安装兼容使用；新的 Google CLI 使用方式请改用 Antigravity (`agy`)。

## Inference gateway 与 model runtime

捕获 OpenRouter 或 LiteLLM gateway evidence：

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway event --gateway litellm --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
```

捕获 Ollama、llama.cpp、vLLM 或 LM Studio 的 model-runtime evidence：

```bash
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` 是 response-only evidence；`exchange` 保存 caller-supplied request+response object，不声明透明 interception。Runtime catalog relation 保留来源本身语义：`LOADED_MODEL`、`SERVES_MODEL`、`ADVERTISES_MODEL` 不能互换。LM Studio catalog visibility 仍表示 `ADVERTISES_MODEL`，不代表 model weights 已 resident in memory。

## Security analysis、evidence grades 与 bounded rule packs

运行内置分析：

```bash
execweave analyze run.graph.json --output analysis.json
```

Finding 会显示独立于 severity 的 evidence grade。当前 grade 为 `A`、`B`、`C`、`D`、`U`，从直接 syscall attribution 到 inferred/unknown provenance。这些 grade 是 evidence-strength category，**不是 probability，也不是 trust score**。

Local rule pack 可以加入 bounded、可解释的**单一 edge observation** policy，而且不执行第三方代码：

```bash
execweave-rule-pack graph.json --rule-pack local-policy.json --output report.json
```

Rule pack 不能执行 code、定义 regex/path program，也不能声称 byte-level data flow 或 exfiltration；rule-pack finding 始终保持 observation-only。

Security finding 对更强 claim 继续明确保留 non-claim：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

## Run integrity

对已完成的 run 创建 seal，之后验证 regular-file inventory 是否仍与 seal 一致：

```text
execweave-integrity seal .execweave/runs/<run-id>
execweave-integrity verify .execweave/runs/<run-id>
```

Deterministic manifest 记录 file size/SHA-256，并拒绝 symbolic link。封存后若文件丢失、修改、替换，或出现新增 regular file，验证会失败。

这个 local seal **不是**在 evidence 与 manifest 都位于同一 writable trust boundary 时的 adversary-resistant tamper evidence。Manifest 明确记录 `malicious_writer_resistance: false` 与 `external_trust_anchor: false`；需要更强保证时，应把 manifest digest 复制/保护到该 boundary 之外。

## Runtime evidence 与 graph operations

Portable collector 支持 Linux、macOS、Windows。Linux 另有 syscall-backed `strace` reference backend。

```bash
execweave doctor
execweave run --backend portable -- your-command
execweave run --backend strace -- your-command
execweave graph-summary run.graph.json
execweave graph-filter run.graph.json --causal-only --output causal.graph.json
execweave graph-focus run.graph.json NODE_ID --hops 2 --output focused.graph.json
execweave path run.graph.json SOURCE TARGET --causal-only
```

Portable filesystem observation 是 session-correlated，而不是 process-causal；polling 也可能漏掉足够短暂的活动。Linux `strace` 在受支持 execution 上提供更强的 process-attributed syscall evidence。Linux eBPF、Windows ETW、macOS Endpoint Security native collector 仍是未来计划。

## Performance 与 large-run safety

ExecWeave 包含 bounded filesystem/viewer protection、incremental Live JSONL tailing、large-graph safety guard、detached Top，以及 configured provider integration 使用的 provisional live sidecar。

可复现的 incremental `GraphAccumulator` reference result 在文档化 GitHub Actions workload 上，1M synthetic events 达到 **164,273 ev/s**。这是 graph accumulation benchmark，而不是 end-to-end collector/browser throughput。

请在代表性主机与 workload 上重新运行 package-level overhead benchmark：

```bash
execweave-overhead --iterations 7 --strace auto --output-json benchmark-results.json
execweave-scalability
```

Reference data 与 methodology：[`docs/benchmarks/`](docs/benchmarks/)。

## Layered artifacts

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
└── integrity.json            # explicit seal 后才会出现
```

Derived correlation 不会重写 raw runtime 或 provider sidecar evidence。

## Privacy

ExecWeave 是 local-first：capture、content blob、graph、report、viewer 默认留在本地。**OS runtime collector** 不会有意捕获 file content 或 raw read/write byte buffer；但这个边界不能与 v0.6.9 的 **provider full-fidelity content store** 混为一谈。受支持 hook/API 如果明确提供 prompt、tool argument/result、model response、reasoning/thinking text、shell output、file content 或其他敏感值，ExecWeave 可以完整保存。

Conversation isolation 是 attribution/display 规则，而不是 redaction boundary。如果 provider 明确把 Agent 1 的内容发送给 Agent 2，这个 routed evidence 可以合理地出现在参与端。不要假设 content 已经过 secret redaction。Command、path、endpoint metadata、identifier、model metadata、prompt、tool value、content blob 都可能敏感；分享前请检查整个 run directory。

## 当前状态

v0.7.9 组合 cross-platform runtime collection、materialized execution graph、standalone/live dashboard、保守的 provider↔runtime correlation、content-addressed full-fidelity provider evidence、可归属的 multi-agent execution trace、run-local conversation access，provider-neutral projection 上的 agent-local conversation isolation，以及 standalone 与 live dashboard 上的 per-agent conversation focus。各 integration 只保留 provider 实际暴露的最强 identity/routing evidence，证据不足时选择 abstain。Observed evidence 与 inference 从设计上保持分离。

## 文档

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.zh-CN.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.zh-CN.md)
- [`Live Graph`](docs/live-graph.zh-CN.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.zh-CN.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.zh-CN.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.zh-CN.md)
- [`Google Antigravity Hooks`](docs/antigravity-hooks.md)
- [`Cursor Hooks`](docs/cursor-hooks.zh-CN.md)
- [`OpenCode Plugin`](docs/opencode-plugin.zh-CN.md)
- [`Inference Gateway / OpenRouter / LiteLLM`](docs/inference-gateway.zh-CN.md)
- [`Model Runtime / Ollama / llama.cpp / vLLM / LM Studio`](docs/model-runtime.zh-CN.md)
- [`Runtime Threat Model`](docs/runtime-threat-model.zh-CN.md)
- [`Evidence Grades`](docs/evidence-grades.zh-CN.md)
- [`Rule Packs`](docs/rule-packs.zh-CN.md)
- [`Run Integrity`](docs/run-integrity.zh-CN.md)
- [`Security Analysis`](docs/security-analysis.zh-CN.md)
- [`Performance Benchmarks`](docs/benchmarks/README.md)

## 贡献

欢迎贡献，尤其是 native OS collector、Agent/IDE adapter、inference gateway、model runtime、evidence/correlation method、privacy/redaction、graph UX、multi-agent conversation attribution 与 performance evaluation。

## License

从 v0.6.8 起，ExecWeave 采用 **PolyForm Noncommercial License 1.0.0**。依许可条款可以进行非商业使用、修改和分发；商业用途需要另外取得许可方的书面商业许可。详见 [`LICENSE`](LICENSE)。
