# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="README.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>

**AI Agent가 내 컴퓨터에서 실제로 무엇을 했는지 확인하세요.**

ExecWeave는 open-source / local-first AI Agent runtime observability 프로젝트입니다. Agent, Tool, Command, Process, File, Network activity를 interactive execution graph로 만들면서 observed evidence와 inference를 명확히 분리합니다.

> **Event is ground truth. Graph is a materialized view.**

## Quick start

```bash
git clone https://github.com/Irish-kw/ExecWeave.git
cd ExecWeave
python -m pip install -e ".[dev]"
```

Live Graph:

```bash
execweave live --open -- claude
execweave live --open -- codex
execweave live --open -- gemini
```

Live server는 `127.0.0.1`에만 bind합니다.

## Native Agent Integrations

현재 native semantic adapter는 **Claude Code, OpenAI Codex, Gemini CLI** 세 가지입니다.

Provider hook은 Agent/Tool/Command/MCP layer의 logical evidence를 기록하고 OS collector는 machine-level runtime evidence를 독립적으로 수집합니다. ExecWeave는 두 evidence class를 fake causality로 합치지 않습니다.

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

자세한 내용: [`docs/claude-code-hooks.ko.md`](docs/claude-code-hooks.ko.md)

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

현재 `SessionStart`, `PreToolUse`, `PostToolUse`를 수집합니다. `PostToolUse`는 neutral `TOOL_CALL_RETURNED`로 기록하며 success/failure를 임의로 단정하지 않습니다.

자세한 내용: [`docs/codex-hooks.ko.md`](docs/codex-hooks.ko.md)

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

`SessionStart`, `BeforeTool`, `AfterTool`을 수집합니다. `run_shell_command`는 declared command evidence를 만들고, 일부 file tools는 declared target path를 기록하며, `mcp_context`는 MCP server/tool entities로 정규화합니다.

현재 Gemini hook schema에는 `BeforeTool`과 `AfterTool`이 공유하는 unique tool-call ID가 없습니다. 따라서 direct identity edge를 만들지 않고 `tool_fingerprint`는 diagnostic hint로만 사용합니다.

자세한 내용: [`docs/gemini-hooks.ko.md`](docs/gemini-hooks.ko.md)

## Layered artifacts

Provider-integrated run은 runtime-only, semantic, correlated artifacts를 분리해 보존합니다.

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

Correlation은 raw observed evidence를 변경하지 않고 derived stream을 추가합니다.

## Tool → Process Correlation

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

는 bounded matcher가 독립 runtime evidence에서 **유일하게 지지되는 후보**를 찾을 때만 생성됩니다.

항상:

```text
inferred: true
causal: false
```

를 유지합니다. Ambiguous / no-match / compound / shell builtin / unsupported call은 edge를 생성하지 않습니다.

## Viewer

Standalone Viewer는 pan/zoom/drag, node/edge details, node-type/relation filters, causal-only, **observed only**, search, Timeline replay, Play/Pause, cluster expansion, 1/2-hop focus, Saved Views, Correlation Summary를 지원합니다.

## Runtime Evidence

Portable backend는 Linux/macOS/Windows를 지원합니다. Linux에서는 syscall-backed reference backend도 사용할 수 있습니다.

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

Claude/Codex/Gemini recorder의 `--backend auto`는 Linux에서 `strace`가 있으면 우선 사용합니다.

## Fake causality를 만들지 않음

ExecWeave는 observed causal / observed non-causal / provider semantic / inferred relationship을 구분합니다. Provider hook이 child PID를 제공하지 않으면 단순한 시간 근접성만으로 Tool → Process edge를 만들지 않습니다.

또한 process가 sensitive file을 읽은 뒤 external endpoint에 연결했다는 사실만으로 bytes가 실제 전송되었다고 증명할 수 없습니다.

## Security Analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

Report는 `data_flow_proven: false` / `exfiltration_proven: false`를 명시적으로 유지합니다.

## Current status

ExecWeave는 현재 **v0.4.0**입니다. portable/strace runtime collection, execution graph, live/standalone Viewer, Timeline/focus/condensation/Saved Views, Claude/Codex/Gemini adapters, conservative correlation, Correlation Summary, 초기 security analysis가 baseline으로 구현되어 있습니다.

향후 Linux eBPF, Windows ETW, macOS Endpoint Security, 추가 provider adapter, 더 강한 identity evidence, MCP normalization, long-run scalability를 진행합니다.

## Privacy

ExecWeave는 **local-first**입니다. File content, raw read/write bytes, prompt/transcript content는 기본적으로 수집하지 않습니다. Command/path/endpoint/session metadata는 민감할 수 있으므로 artifact 공유 전에 확인하세요.

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ko.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ko.md)
- [`Live Graph`](docs/live-graph.ko.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ko.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ko.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ko.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.ko.md)
- [`Security Analysis`](docs/security-analysis.ko.md)

## Contributing

Linux eBPF, Windows ETW, macOS Endpoint Security, provider adapter, provenance/correlation, Graph UX, privacy/redaction, testing/performance, 번역 contribution을 환영합니다.

## License

[`LICENSE`](LICENSE)를 참고하세요.
