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
```

같은 report를 file에 기록하려면:

```bash
execweave analyze run.graph.json --output analysis.json
```

현재 analysis schema는 `0.2`입니다.

## Goal

Analysis layer는 review할 graph evidence의 priority를 정합니다. Agent가 sensitive resource에 접근하거나 network에 연결했다는 이유만으로 malicious라고 주장하지 않습니다.

Core rule은 다음과 같습니다.

> **Co-occurrence 또는 process lineage를 data-flow claim으로 바꾸지 않는다.**

## Current rules

### Sensitive-file access

Rule은 흔한 sensitive location 또는 filename과 관련된 file edge를 찾습니다. 예:

- `~/.ssh/*`
- `~/.aws/credentials`
- `~/.kube/config`
- Docker config
- `.npmrc`
- `.pypirc`
- `.netrc`
- `.env`
- common SSH private-key filenames

Causal syscall-backed process edge는 non-causal session observation보다 stronger evidence입니다.

### External network contact

Rule은 process에서 external network endpoint로 향하는 edge를 식별하고 명백한 loopback/private/link-local address를 제외합니다.

현재 runtime telemetry는 주로 IP endpoint 기반입니다. DNS/domain correlation은 future work입니다.

### Possible same-process sensitive-file-to-network path

**동일 process**에 causal sensitive-file access evidence가 있고 이후 causal external network activity가 있으면 ExecWeave는 prioritization finding을 emit합니다.

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

Finding은 다음을 기록합니다.

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

Graph는 해당 process가 두 action을 chronological order로 수행했다는 것을 증명합니다. 하지만 file bytes가 connection을 통해 전송되었다는 것은 **증명하지 않습니다**.

### Possible delegated sensitive-file-to-network path

Analysis schema `0.2`는 chronological causal `SPAWNED` edge도 추적합니다.

예:

```text
parent process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── SPAWNED ──────→ child process
                         └── CONNECTED_TO ─→ external endpoint
```

Delegated finding은 다음 조건을 모두 만족할 때만 emit됩니다.

1. sensitive-file edge가 causal;
2. `SPAWNED` edge 또는 chain이 causal;
3. spawn sequence가 sensitive-file access sequence 이후;
4. descendant의 external network evidence가 spawn chain 이후;
5. path depth가 analyzer의 conservative traversal bound 안에 있음.

이는 chronological process-lineage path를 증명합니다. 하지만 child가 parent로부터 file data를 받았다는 것은 여전히 **증명하지 않습니다**.

Delegated finding은 다음을 명시적으로 기록합니다.

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED`는 process creation/lineage evidence이며 memory inheritance, pipe write, socketpair transfer, shared-memory transfer, environment-secret transfer 또는 기타 구체적인 data movement의 evidence가 아닙니다.

실제 data-flow 또는 exfiltration claim에는 taint tracking, IPC-aware provenance, byte-level read/write/network telemetry 같은 더 강한 evidence가 필요합니다.

## Severity

Severity value는 vulnerability score가 아니라 prioritization level입니다.

- `high`
- `medium`
- `low`
- `info`

현재 예:

- external connection alone: informational;
- sensitive-file access: relation과 attribution strength에 따라 다름;
- same-process sensitive read 후 confirmed external connection: high-priority signal;
- delegated child-process path: process boundary를 넘는 data transfer가 증명되지 않았기 때문에 equivalent same-process path보다 낮은 priority.

## Backend dependence

Analysis quality는 collector quality에 의해 제한됩니다.

Linux `strace` reference backend는 supported operation에 대해 process-attributed syscall evidence를 제공할 수 있습니다. Portable backend는 filesystem attribution이 더 약하므로 동일한 process-level conclusion을 지원할 수 없습니다.

Analyzer는 weaker evidence를 upgrade하지 않고 graph의 `causal` metadata를 존중합니다.

## Output

Report에는 다음이 포함됩니다.

- analysis schema version
- session ID
- total finding count
- severity counts
- explicit limitations
- per-finding rule ID
- title and summary
- related node IDs
- related edge IDs
- evidence event IDs
- rule-specific attributes

Delegated finding에는 process chain, delegation-hop count, spawn sequence와 data inheritance/IPC/data flow에 대한 explicit negative guarantee도 포함됩니다.

## Future analysis layers

향후 추가 가능 항목:

- credential and secret entity resolution
- DNS/domain correlation and context
- explicit IPC edges
- environment-variable and inherited-handle provenance
- agent/tool/MCP semantic context
- anomaly detection
- attack-path ranking
- byte-level data-flow / taint tracking
- runtime allow / warn / block policy

이 기능들도 observed evidence, inferred risk, process lineage, proven causal data flow의 구분을 계속 유지해야 합니다.
