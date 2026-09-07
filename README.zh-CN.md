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

**看清 AI Agent 在你的机器上实际做了什么。**

ExecWeave 是一个 local-first 的 AI Agent 与 AI 开发工具可观测性项目。它把 Provider 层语义与操作系统运行时证据整合到同一个交互式 Execution Graph 中，同时保留不同证据层级之间的边界。

> **Event 是证据；Graph 是由证据物化出的视图。**

<p align="center">
  <img src="docs/assets/codex.gif" alt="ExecWeave 实时 Dashboard 演示" width="100%">
</p>

## 为什么需要 ExecWeave

Agent 可以告诉你它调用了某个工具、修改了某个文件，或连接了某个服务。Provider 语义很有价值，但并不等同于操作系统真正观察到的行为。ExecWeave 把这些层放到同一个界面里检查，同时不会把不同强度的证据混为一谈。

- **Live 与完成后使用同一套 Dashboard。** 运行中页面、完成后的结果和独立 `viewer.html` 使用相同的 Graph 与对话模型。
- **理解 Provider 语义。** Provider 暴露 hook、rollout transcript、plugin 或 runtime API 时，使用可验证的原生信息。
- **观察 OS runtime。** 可独立观察 Process、File 和 Network endpoint，而不只依赖 Agent 自己的描述。
- **证据分层。** Direct observation、exact identity、保守推断与 causal claim 不会被压成同一类关系。
- **Local-first。** Run artifacts 默认保留在本机，除非你主动复制或分享。
- **不局限于单一 Agent。** 即使没有专用 Provider adapter，也可以包装普通本地命令进行 runtime 观察。

## 安装

从 PyPI 安装：

```bash
python -m pip install -U execweave
```

开发安装：

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

## 快速开始

将任意本地命令放在 `execweave live` 后面：

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- antigravity
execweave live --open -- cursor
execweave live --open -- opencode
execweave live --open -- python my_agent.py
```

主要想生成完成后的 artifacts 时：

```bash
execweave record --open -- python my_agent.py
```

希望程序继续在当前 terminal 交互，同时另外查看概览时：

```bash
execweave top -- codex
```

### Provider integration 授权

部分 Agent 或 IDE 第一次启用本地 hook / plugin 时会要求授权。如果你希望看到 Prompt、Response、Tool、Model 与 Conversation 等 Provider-level evidence，请允许 ExecWeave integration。若不允许，OS runtime 观察仍可能工作，但 Provider 语义覆盖会减少。

Google Antigravity 当前实际 CLI 命令为 `agy`；ExecWeave 也接受 `antigravity` 作为易记 alias。

Windows 上直接输入 `cursor` 时，ExecWeave 会根据用户 PATH 指向的 Cursor 安装位置处理；显式给出的 launcher path 会保持不变。

## Ollama

ExecWeave 支持两种常见的本地 Ollama 工作流。

### Managed server capture

先通过 ExecWeave 启动 Ollama Server：

```bash
execweave live --open -- ollama serve
```

然后在另一个 terminal 正常使用 Ollama：

```bash
ollama run deepseek-r1:1.5b
```

SDK、OpenAI-compatible local request 与发送到 managed local endpoint 的 `curl` request，也可以关联到同一个 ExecWeave run。第二个 terminal 不需要再包一层 ExecWeave。

Managed relay 只处理本地 loopback endpoint，不会改写 wildcard 或外部暴露的 Ollama listener。

### Direct client capture

如果 Ollama Server 已经运行，也可以直接包装 client：

```bash
execweave live --open -- ollama run deepseek-r1:1.5b
```

该模式不会启动 Ollama Server，因此仍需要可连接的 upstream server。

## Dashboard

Dashboard 的目标是在大型、多 Agent 场景下仍保持可读，同时不修改底层 evidence。

- **Execution graph：** Agent、Process、File、Network endpoint、Tool、Model/runtime entity 与支持的关系。
- **Conversation rounds：** 新旧轮次都保持在正确 Agent 下，不会被后续消息覆盖。
- **Node details：** 可检查 Process identity、File history、Network endpoint、Tool 和 Provider conversation content。
- **稳定 Live update：** Run 状态变化时原页面持续更新，不整页替换。
- **大型 Graph folding：** 节点过多时可折叠较旧成员，同时保持可检查性。
- **Selection-focused layout：** 选择 Agent 或 runtime object 后，弱化无关 Graph traffic。

大型运行可使用以下参数调节：

```text
--fold-budget N
--viewer-max-nodes N
--viewer-max-edges N
--viewer-max-dom-elements N
```

## 支持的集成

| Integration | OS runtime 观察 | 专用 evidence |
| --- | --- | --- |
| Claude Code | 由 ExecWeave 启动时支持 | native hooks 与 Provider 提供的 conversation/tool content |
| OpenAI Codex | 支持 | lifecycle hooks、validated rollout transcripts、可观察时的 agent/subagent routing |
| Google Antigravity | 支持 | passive hooks 与可观察时的 conversation/subagent routing |
| Cursor | 支持 | native hooks 与可观察时的 task/subagent routing |
| OpenCode | 支持 | project plugin、session/task routing、Provider 提供的 plugin content |
| Ollama | 支持 | managed local relay 与 model-runtime evidence |
| llama.cpp | 支持 | model-runtime event/exchange/probe |
| vLLM | 支持 | model-runtime event/exchange/probe |
| LM Studio | 本地进程可观察时 | model-runtime catalog/runtime evidence |
| LiteLLM Proxy | 本地 proxy 可观察时 | gateway metadata 与 event integration |
| OpenRouter | 只能观察本地 client，无法观察远端 service process | caller-supplied gateway event/exchange evidence |

Tool-call ID、session ID、rollout thread ID、subagent route 等 Provider identifier 是逻辑身份，不等于 OS PID。ExecWeave 只有在证据足够时才会连接不同层。

## Evidence model

ExecWeave 将 evidence 分为几个主要层级：

```text
Agent / IDE semantics 与 supplied content
                ↓
Inference gateway / routing evidence
                ↓
Model runtime / inference-server evidence
                ↓
OS runtime evidence: process / file / network
```

只有底层 telemetry 足以支持 causal claim 时，关系才应标为 causal。保守推断会明确保留 derived 标记，例如：

```text
inferred: true
causal: false
```

共享 exact request identity 可以证明 identity，但不代表 causal：

```text
identity_exact: true
inferred: false
causal: false
```

如果 attribution 仍有歧义，ExecWeave 应不建立 edge，而不是猜测更强的关系。

### Full-fidelity supplied content

支持的 Provider hook、plugin 或 API 可以把 Provider 明确提供的完整值保存到本地 SHA-256 content-addressed store：

```text
<run-root>/content/sha256/<sha256>.<json|txt|bin>
```

内容可能包括 Prompt、Message、Request/Response object、Tool input/result、Assistant response、Provider 明确暴露的 reasoning text、Shell output 与 supplied file content。

`complete_from_source: true` 表示 ExecWeave 保存了该 integration point 提供的完整内容；不代表 ExecWeave 看到了未暴露的模型内部状态或 Provider 内部数据。

## 常用命令

### Agent / IDE recorder

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
execweave-antigravity-record --open -- antigravity
execweave-cursor-record --open -- cursor
execweave-opencode-plugin --install
execweave-opencode-record --open -- opencode
```

### Gateway 与 model runtime

```bash
execweave-inference-gateway event --gateway openrouter --sidecar gateway.jsonl
execweave-inference-gateway exchange --gateway openrouter --sidecar gateway.jsonl
execweave-model-runtime event --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime exchange --runtime ollama --sidecar model-runtime.jsonl
execweave-model-runtime probe --runtime ollama --sidecar model-runtime.jsonl
```

`event` 表示单侧 event evidence。`exchange` 保存 caller 提供的 request/response pair，不宣称透明拦截 wire traffic。

### Runtime、Graph、安全与完整性

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
└── integrity.json
```

Raw observation 与 derived semantic/correlation output 保持分离。

## 限制与隐私

- Portable collector 可用于 Linux、macOS、Windows。Portable filesystem observation 属于 session-correlated evidence，不一定形成 process-causal attribution；polling 也可能漏掉非常短暂的活动。
- Linux 另有 `strace` reference backend，可在支持的执行中获得更强的 syscall-attributed evidence。
- Provider semantic coverage 完全取决于 integration 实际暴露的信息。未暴露的 Prompt、hidden reasoning、远端 Provider internals 与 routing 无法可靠重建。
- Full-fidelity Provider content 可能包含 Credential、Secret、Source code、Prompt、Tool value、Model response、Shell output 与 File content。
- Conversation isolation 是 attribution 规则，不是 redaction boundary。Provider 明确路由的内容可能合理地出现在多个参与者上。
- 本地 integrity manifest 可以检查相对 manifest 的文件变化，但如果 evidence 与 manifest 都处在同一个可写 trust boundary，就不是 adversary-resistant trusted logging system。
- 分享前请检查完整 run directory。

## 开发

运行测试：

```bash
python -m pytest
```

运行 lint：

```bash
python -m ruff check .
```

欢迎提交 Issue 和 Pull Request。新增 integration 时，请明确区分“直接观察”“Provider 提供”和“推导所得”的 evidence。

## 许可

ExecWeave 使用 **PolyForm Noncommercial License 1.0.0**。完整条款见 [LICENSE](LICENSE)。
