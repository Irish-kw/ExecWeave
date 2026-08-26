<!-- i18n-nav:start -->
<p align="center">
  <a href="semantic-telemetry.md">English</a> |
  <a href="semantic-telemetry.zh-TW.md">繁體中文</a> |
  <a href="semantic-telemetry.zh-CN.md">简体中文</a> |
  <a href="semantic-telemetry.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="semantic-telemetry.fr.md">Français</a> |
  <a href="semantic-telemetry.de.md">Deutsch</a> |
  <a href="semantic-telemetry.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Semantic Telemetry

ExecWeave는 원래 runtime capture를 다시 쓰지 않고 provider/framework semantic event와 OS runtime evidence를 결합할 수 있습니다.

설계 목표는 logical Agent/Tool/MCP evidence와 machine-level process/file/network evidence를 같은 graph에 배치하면서 각 relationship을 어떤 source가 증명했는지 보존하는 것입니다.

```text
agent --REQUESTED_TOOL_CALL--> tool_call --USES_TOOL--> tool
                                                     |
                                                     +--DECLARED_COMMAND--> command

process --OPENED_READ--> file
process --CONNECTED_TO--> network_endpoint
```

Provider hook은 *어떤 logical action이 요청되었는지* 설명할 수 있습니다. Runtime collector는 *machine이 실제로 무엇을 했는지* 설명합니다. ExecWeave는 둘 사이의 temporal proximity를 조용히 causal proof로 바꾸지 않습니다.

## Workflow

먼저 일반적인 ExecWeave run을 capture합니다.

```bash
execweave run --output run.jsonl -- claude
```

Provider adapter 또는 hook은 예를 들어 `semantic.jsonl` 같은 별도 semantic sidecar를 기록합니다.

Sidecar를 **새로운** validated event stream으로 merge합니다.

```bash
execweave semantic-merge run.jsonl semantic.jsonl \
  --output run.semantic.jsonl

execweave validate run.semantic.jsonl
execweave graph run.semantic.jsonl \
  --output run.semantic.graph.json
execweave view run.semantic.graph.json \
  --output run.semantic.html \
  --open
```

`run.jsonl`은 `semantic-merge`에 의해 수정되지 않습니다.

## Sidecar record contract

Semantic sidecar record는 한 줄에 JSON object 하나입니다. Adapter는 semantic observation만 제공합니다.

```json
{
  "timestamp": "2026-08-25T10:00:02.123Z",
  "event_type": "semantic.tool.called",
  "relation": "REQUESTED_TOOL_CALL",
  "source": {
    "type": "agent",
    "id": "agent:Claude Code",
    "name": "Claude Code",
    "attributes": {}
  },
  "target": {
    "type": "tool_call",
    "id": "tool-call:provider:session:call-id",
    "name": "Bash",
    "attributes": {}
  },
  "attributes": {
    "attribution": "provider_hook",
    "evidence_source": "provider_hook",
    "causal": false
  }
}
```

Sidecar는 다음을 제공할 필요가 없습니다.

- ExecWeave `session_id`
- ExecWeave `schema_version`
- contiguous `sequence`
- `event_id`(optional이며 생략 시 ExecWeave가 생성)

`semantic-merge`는 runtime session ID를 주입하고 현재 ExecWeave event schema를 사용하며 semantic/runtime body event를 timestamp 순으로 정렬하고 하나의 contiguous sequence를 다시 할당합니다. 또한 `session.started`를 처음에, `session.finished`를 마지막에 유지하고 output file을 commit하기 전에 merged result를 validate합니다.

## Recommended semantic entities

ExecWeave의 generic entity schema는 추가 node type을 이미 지원합니다.

| Type | Example ID | Meaning |
| --- | --- | --- |
| `agent` | `agent:Claude Code` | Logical agent/client |
| `tool_call` | `tool-call:claude:session:tool-use-id` | 하나의 구체적인 logical tool invocation |
| `tool` | `tool:claude:Bash` | Agent-visible tool |
| `mcp_server` | `mcp-server:claude:github` | MCP server/integration |
| `model` | `model:claude:claude-sonnet` | Provider가 노출할 때의 model identity |
| `command` | `command:sha256:...` | Semantic hook이 선언한 command metadata |
| `process_reference` | `process-pid:1234` | Upstream source가 실제 PID를 제공한 경우의 optional bridge |

Entity ID는 하나의 run 안에서 repeated semantic observation을 deduplicate할 수 있을 만큼 안정적이어야 합니다.

## Optional process-reference bridge

일부 provider/framework adapter는 child PID는 알지만 ExecWeave의 전체 process entity ID는 모를 수 있습니다. 이 경우 관측된 PID를 가진 `process_reference`를 emit할 수 있습니다.

Merge 중 ExecWeave는 이러한 reference를 runtime stream에서 실제 관측한 process entity에 대해 resolve합니다. Resolution은 보수적입니다.

1. 명시적인 `create_time`이 process를 고유하게 식별할 수 있음;
2. PID에 runtime candidate가 하나뿐이면 직접 resolve;
3. PID reuse의 경우 semantic timestamp보다 늦지 않은 가장 최근 process creation time이 고유하면 선택 가능;
4. 그 외에는 추측하지 않고 `process_reference`를 `unresolved: true` 상태로 유지.

Resolved event는 원래 reference에서 runtime process로의 mapping을 `attributes.resolved_process_references`에 기록합니다.

**Provider가 PID를 노출하지 않았다면 `process_reference`를 emit하지 마십시오.** Command string과 가까운 process timestamp만으로 exact Tool → Process relationship을 주장할 수 없습니다.

현재 Claude Code native hook adapter는 이 규칙을 따릅니다. Claude hook input은 tool call을 식별하지만 child process PID를 제공하지 않으므로 adapter는 `tool_call --SPAWNED_PROCESS--> process` edge를 만들어내지 않습니다.

## Evidence and causality boundary

현재 provider adapter는 provider hook이 logical tool event가 발생했음을 authoritative하게 보고하더라도 semantic edge를 `causal: false`로 표시합니다. ExecWeave에서 `causal: true`는 두 logical object가 관련되어 있다는 사실보다 더 강한 execution-level attribution을 위해 예약되어 있습니다.

따라서 다음 statement는 서로 분리됩니다.

```text
Claude Code --REQUESTED_TOOL_CALL--> Bash call       semantic provider evidence
process     --OPENED_READ---------> ~/.ssh/id_ed25519 OS runtime evidence
```

이 두 observation만으로는 다음을 증명하지 못합니다.

```text
Bash call --caused--> that exact process
file bytes --flowed to--> a network endpoint
```

향후 semantic/runtime correlation layer는 method와 confidence를 명시적으로 노출해야 하며 observed OS attribution과 구분 가능한 상태를 유지해야 합니다.

## Session boundary

모든 semantic timestamp는 captured runtime session interval 안에 있어야 합니다. Interval 밖의 event는 reject됩니다. 이렇게 하면 관련 없는 provider telemetry가 잘못된 execution에 조용히 attach되는 것을 방지할 수 있습니다.

## Privacy

ExecWeave 자체가 file content를 수집하지 않더라도 semantic sidecar에는 sensitive metadata가 포함될 수 있습니다. Adapter author는 full prompt, tool argument, tool output, credential, secret value보다 identifier와 bounded metadata를 우선해야 합니다.

Claude Code adapter는 `Write` content나 `tool_response`를 의도적으로 저장하지 않습니다. Declared shell command는 execution explanation에 중요하므로 유지하지만 크기가 bounded되어 있으며 여전히 sensitive metadata로 취급해야 합니다.

Generic semantic merge layer는 provider-agnostic입니다. Provider-specific adapter는 별도 integration이며 어떤 upstream field를 사용하고 어떤 claim을 지원하는지 정확히 document해야 합니다.

첫 번째 native provider adapter는 [`Claude Code Hooks`](claude-code-hooks.ko.md)를 참조하십시오.
