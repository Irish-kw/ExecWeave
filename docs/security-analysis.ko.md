<!-- i18n-nav:start -->
<p align="center">
  <a href="security-analysis.md">English</a> |
  <a href="security-analysis.zh-TW.md">繁體中文</a> |
  <a href="security-analysis.zh-CN.md">简体中文</a> |
  <a href="security-analysis.ja.md">日本語</a> |
  <strong>한국어</strong> |
  <a href="security-analysis.fr.md">Français</a> |
  <a href="security-analysis.de.md">Deutsch</a> |
  <a href="security-analysis.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Security Analysis

ExecWeave는 completed execution graph 위에 conservative하고 explainable한 rule layer를 제공합니다.

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

현재 analysis schema는 `0.2`입니다.

## Goal

목표는 graph evidence의 review priority를 정하는 것입니다. Agent가 sensitive resource에 접근하거나 network를 사용했다는 사실만으로 malicious라고 판단하지 않습니다.

> **Co-occurrence 또는 process lineage를 data-flow claim으로 바꾸지 않는다.**

## Current rules

### Sensitive-file access

`~/.ssh/*`, `~/.aws/credentials`, `~/.kube/config`, Docker config, `.npmrc`, `.pypirc`, `.netrc`, `.env`, SSH private key 등 흔한 sensitive location/name을 확인합니다. Causal syscall-backed process edge는 non-causal session observation보다 stronger evidence입니다.

### External network

Process에서 external endpoint로 향하는 edge를 찾고 loopback/private/link-local address는 제외합니다. DNS/domain correlation은 future work입니다.

### Possible same-process path

동일 process가 causal sensitive-file access 후 causal external network activity를 보이면 review finding을 만들 수 있습니다.

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

하지만 finding은 다음을 명시합니다.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

동일 process가 두 action을 순서대로 수행했다는 것은 증명하지만 file bytes가 connection으로 전송됐다는 것은 증명하지 않습니다.

### Delegated path

Chronological causal `SPAWNED` chain을 따라 parent sensitive read → spawn → child external network의 possible path를 표시할 수 있습니다.

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED`는 process creation/lineage evidence이지 memory, pipe, socketpair, shared memory, environment-secret transfer의 증명이 아닙니다. 실제 data-flow claim에는 taint tracking, IPC-aware provenance 또는 byte-level telemetry가 필요합니다.

## Severity

`high / medium / low / info`는 investigation priority이며 vulnerability score가 아닙니다. Delegated path는 process boundary를 넘는 data transfer가 입증되지 않았기 때문에 equivalent same-process path보다 보수적으로 다룹니다.

## Backend dependence

Linux `strace`는 supported operation에 process-attributed syscall evidence를 제공합니다. Portable filesystem attribution은 더 약하므로 동일한 process-level conclusion을 지원할 수 없습니다. Analyzer는 graph의 `causal` metadata를 존중합니다.

## Output

Report에는 schema/session/finding count/severity, limitations, rule ID, related nodes/edges, evidence event IDs, rule-specific attributes가 포함됩니다. Delegated finding은 process chain과 explicit negative guarantees도 기록합니다.

Provider semantic evidence와 `CORRELATED_WITH_PROCESS` inferred edge가 graph에 있어도 `inferred: true / causal: false`를 OS-observed causality로 upgrade하면 안 됩니다.

## Future

Credential/secret resolution, DNS/domain context, explicit IPC, environment/handle provenance, Agent/Tool/MCP context, anomaly detection, attack-path ranking, byte-level taint, runtime policy 등을 고려하고 있습니다.

모든 layer는 observed evidence / inferred risk / process lineage / proven data flow를 계속 구분해야 합니다.
