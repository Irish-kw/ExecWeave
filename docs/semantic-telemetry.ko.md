<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <strong>한국어</strong>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave는 provider/framework semantic events와 OS runtime evidence를 같은 graph에 놓으면서 어떤 source가 어떤 관계를 증명했는지 분리합니다. Raw runtime capture는 수정하지 않습니다.

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     +--DECLARED_COMMAND--> command
process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Provider hook은 logical action을, runtime collector는 machine-level observation을 설명합니다. Temporal proximity를 causal proof로 바꾸지 않습니다.

## Workflow

```bash
execweave run --output run.jsonl -- claude
execweave semantic-merge run.jsonl semantic.jsonl --output run.semantic.jsonl
execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl --output run.semantic.graph.json
```

Raw `run.jsonl`은 그대로 유지됩니다. Claude/Codex에서는 run-bound recorder가 이 pipeline을 자동화합니다.

```bash
execweave-claude-record --open -- claude
execweave-codex-record --open -- codex
```

## Sidecar contract

Semantic sidecar는 한 줄에 JSON object 하나이며 `timestamp`, `event_type`, `relation`, `source`, `target`, `attributes`를 제공합니다. Adapter가 ExecWeave `session_id`, schema version, contiguous `sequence`를 만들 필요는 없습니다. Merge가 session injection, timestamp ordering, sequence reassignment, validation을 수행합니다.

권장 entity: `agent`, `tool_call`, `tool`, `mcp_server`, `model`, `command`, 그리고 upstream이 실제 PID를 제공하는 경우에만 `process_reference`.

## Process-reference bridge

Provider가 정말 PID를 제공할 때만 사용합니다. Create time 또는 unique PID candidate로 conservative하게 resolve하며 ambiguous이면 `unresolved: true`로 남깁니다.

**PID가 없는 provider에 process reference를 만들어내지 않습니다.** Command string과 timestamp만으로 exact Tool → Process를 증명할 수 없습니다.

## Conservative correlation

Declared shell command와 bounded runtime evidence를 비교해 unique process candidate가 하나일 때만 derived stream에:

```text
tool_call --CORRELATED_WITH_PROCESS--> process
```

를 추가합니다. 항상 `inferred: true`, `causal: false`입니다. Ambiguous/no-match/builtin/compound/unsupported call은 no edge이며 confidence는 calibrated probability가 아니라 heuristic score입니다.

## Evidence boundary

Provider semantic edge도 보통 `causal: false`입니다. 이는 hook이 거짓이라는 뜻이 아니라 logical relationship을 OS execution causality로 upgrade하지 않는다는 뜻입니다.

Agent → tool call과 process → file evidence가 동시에 있어도 exact Tool→Process 또는 file-byte→network flow를 자동으로 증명하지 않습니다.

Semantic timestamp는 captured runtime session interval 안에 있어야 하며 다른 run의 event는 merge하지 않습니다.

## Privacy

Adapter는 prompt, file content, raw tool output, credential 같은 고위험 payload 대신 identifier와 bounded metadata를 우선합니다. Shell command/path 자체는 sensitive할 수 있으므로 공유 전에 확인해야 합니다.

Provider-specific docs:

- [`Claude Code Hooks`](claude-code-hooks.ko.md)
- [`OpenAI Codex Hooks`](codex-hooks.ko.md)
