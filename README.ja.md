# ExecWeave

<p align="center">
  <a href="README.md">English</a> |
  <a href="README.zh-TW.md">繁體中文</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <strong>日本語</strong> |
  <a href="README.ko.md">한국어</a>
</p>

**AI Agent があなたのマシン上で実際に何をしたのかを可視化します。**

ExecWeave は open-source / local-first の AI Agent runtime observability プロジェクトです。Agent、Tool、Command、Process、File、Network activity を interactive execution graph に変換し、observed evidence と inference を明確に分離します。

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

Live server は `127.0.0.1` のみに bind します。

## Native Agent Integrations

現在の native semantic adapter は **Claude Code、OpenAI Codex、Gemini CLI** の3つです。

Provider hook は Agent/Tool/Command/MCP layer の logical evidence を記録し、OS collector は machine-level runtime evidence を独立して収集します。ExecWeave は両者を fake causality に統合しません。

### Claude Code

```bash
execweave-claude-hook --print-config
execweave-claude-record --open -- claude
```

詳細: [`docs/claude-code-hooks.ja.md`](docs/claude-code-hooks.ja.md)

### OpenAI Codex

```bash
execweave-codex-hook --print-config
execweave-codex-record --open -- codex
```

`SessionStart` / `PreToolUse` / `PostToolUse` を取り込みます。`PostToolUse` は neutral `TOOL_CALL_RETURNED` として扱い、success/failure を勝手に断定しません。

詳細: [`docs/codex-hooks.ja.md`](docs/codex-hooks.ja.md)

### Gemini CLI

```bash
execweave-gemini-hook --print-config
execweave-gemini-record --open -- gemini
```

`SessionStart` / `BeforeTool` / `AfterTool` を取り込みます。`run_shell_command` は declared command evidence を生成し、file tools は declared target path、`mcp_context` は MCP server/tool entities に正規化されます。

現在の Gemini hook schema には `BeforeTool` と `AfterTool` で共有できる unique tool-call ID がありません。そのため direct identity edge は生成せず、`tool_fingerprint` は diagnostic hint としてのみ保持します。

詳細: [`docs/gemini-hooks.ja.md`](docs/gemini-hooks.ja.md)

## Layered artifacts

Provider-integrated run は runtime-only、semantic、correlated artifacts を分離して保存します。

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

Correlation は raw observed evidence を変更せず、derived stream を追加します。

## Tool → Process Correlation

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

は bounded matcher が独立 runtime evidence から**一意な候補**を得た場合だけ生成されます。

常に：

```text
inferred: true
causal: false
```

です。Ambiguous / no-match / compound / shell builtin / unsupported call は edge を生成しません。

## Viewer

Standalone Viewer は pan/zoom/drag、node/edge details、node-type/relation filters、causal-only、**observed only**、search、Timeline replay、Play/Pause、cluster expansion、1/2-hop focus、Saved Views、Correlation Summary を備えています。

## Runtime Evidence

Portable backend は Linux/macOS/Windows をサポートします。Linux では syscall-backed reference backend も利用できます。

```bash
sudo apt-get install strace
execweave record --backend strace --open -- claude
```

Claude/Codex/Gemini の各 recorder は `--backend auto` で Linux に `strace` があれば優先利用します。

## Fake causality を作らない

ExecWeave は observed causal / observed non-causal / provider semantic / inferred relationship を明確に区別します。Provider hook が child PID を提供しない場合、時間的近接だけで Tool → Process edge を作りません。

また、process が sensitive file を読んだ後に external endpoint へ接続しただけでは、bytes が実際に送信された証明にはなりません。

## Security Analysis

```bash
execweave analyze run.graph.json --output analysis.json
```

Report は `data_flow_proven: false` / `exfiltration_proven: false` を明示的に保持します。

## Current status

ExecWeave は現在 **v0.4.0** です。portable/strace runtime collection、execution graph、live/standalone Viewer、Timeline/focus/condensation/Saved Views、Claude/Codex/Gemini adapters、conservative correlation、Correlation Summary、初期 security analysis が baseline として実装済みです。

今後は Linux eBPF、Windows ETW、macOS Endpoint Security、追加 provider adapter、より強い identity evidence、MCP normalization、long-run scalability を進めます。

## Privacy

ExecWeave は **local-first** です。File content、raw read/write bytes、prompt/transcript content はデフォルトでは収集しません。Command/path/endpoint/session metadata は sensitive になり得るため、artifact 共有前に確認してください。

## Documentation

- [`Phase 1 — Runtime Collection`](docs/phase-1-runtime-collection.ja.md)
- [`Phase 2 — Execution Graph`](docs/phase-2-execution-graph.ja.md)
- [`Live Graph`](docs/live-graph.ja.md)
- [`Semantic Telemetry`](docs/semantic-telemetry.ja.md)
- [`Claude Code Hooks`](docs/claude-code-hooks.ja.md)
- [`OpenAI Codex Hooks`](docs/codex-hooks.ja.md)
- [`Gemini CLI Hooks`](docs/gemini-hooks.ja.md)
- [`Security Analysis`](docs/security-analysis.ja.md)

## Contributing

Linux eBPF、Windows ETW、macOS Endpoint Security、provider adapter、provenance/correlation、Graph UX、privacy/redaction、testing/performance、翻訳の contribution を歓迎します。

## License

[`LICENSE`](LICENSE) を参照してください。
