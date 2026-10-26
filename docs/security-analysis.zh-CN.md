<!-- i18n-nav:start -->
<p align="center">
  <a href="security-analysis.md">English</a> |
  <a href="security-analysis.zh-TW.md">繁體中文</a> |
  <strong>简体中文</strong> |
  <a href="security-analysis.ja.md">日本語</a> |
  <a href="security-analysis.ko.md">한국어</a> |
  <a href="security-analysis.fr.md">Français</a> |
  <a href="security-analysis.de.md">Deutsch</a> |
  <a href="security-analysis.ru.md">Русский</a>
</p>
<!-- i18n-nav:end -->

# Security Analysis

ExecWeave 在 completed execution graph 上提供一层保守、可解释的 rule-based analysis：

```bash
execweave analyze run.graph.json
execweave analyze run.graph.json --output analysis.json
```

目前 analysis schema 是 `0.2`。

## 目标

Analysis layer 的用途是把值得人工检查的 graph evidence 排出优先顺序。Agent 接触 sensitive resource 或连到 network，**不等于** Agent 是 malicious。

核心原则：

> **不要把 co-occurrence 或 process lineage 转成 data-flow claim。**

## 目前规则

### Sensitive-file access

目前会辨识常见敏感位置/档名，例如：

- `~/.ssh/*`
- `~/.aws/credentials`
- `~/.kube/config`
- Docker config
- `.npmrc`
- `.pypirc`
- `.netrc`
- `.env`
- 常见 SSH private-key filename

Causal syscall-backed process edge 的 evidence strength 高于 non-causal session observation。

### External network contact

Rule 会找 process 到 external network endpoint 的 edge，同时排除明显 loopback/private/link-local address。

目前 runtime telemetry 主要是 IP endpoint；DNS/domain correlation 仍是后续工作。

### Possible same-process sensitive-file-to-network path

同一个 process 若先有 causal sensitive-file access，之后又有 causal external network activity，ExecWeave 会产生 prioritization finding：

```text
process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── CONNECTED_TO ─→ 8.8.8.8:443
```

Finding 会明确保留：

```json
{
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

Graph 只证明同一 process 按时间顺序做了两件事，**不能**证明 file bytes 被送进那条 connection。

### Possible delegated sensitive-file-to-network path

Schema `0.2` 也会追 chronological causal `SPAWNED` edges：

```text
parent process
  ├── OPENED_READ ──→ ~/.ssh/id_ed25519
  └── SPAWNED ──────→ child process
                         └── CONNECTED_TO ─→ external endpoint
```

只有以下条件都满足才产生 delegated finding：

1. sensitive-file edge 是 causal；
2. `SPAWNED` edge/chain 是 causal；
3. spawn sequence 在 sensitive access 之后；
4. descendant external network evidence 在 spawn chain 之后；
5. traversal 不超过 analyzer 的保守 depth bound。

这能证明 chronological process-lineage path，但仍不能证明 child 收到了 parent 的 file data。

Delegated finding 明确记录：

```json
{
  "causal_process_lineage": true,
  "data_inheritance_proven": false,
  "ipc_proven": false,
  "data_flow_proven": false,
  "exfiltration_proven": false
}
```

`SPAWNED` 只证明 process creation/lineage，不代表 memory inheritance、pipe write、socketpair、shared memory、environment-secret transfer 或任何实际 data movement。

真正的 data-flow/exfiltration claim 需要更强 evidence，例如 taint tracking、IPC-aware provenance 或 byte-level read/write/network telemetry。

## Severity

Severity 是 investigation priority，不是 vulnerability score：

- `high`
- `medium`
- `low`
- `info`

例如 external connection alone 通常只是 informational；sensitive-file access 依 relation/attribution strength 决定；same-process sensitive read + 后续 external connection 可是 high-priority signal；delegated child path 因 process boundary 上的 data transfer 未被证明，会比 equivalent same-process path 更保守。

## Backend dependence

Analysis quality 受 collector quality 上限限制。

Linux `strace` reference backend 可提供支援 operation 的 process-attributed syscall evidence。Portable backend filesystem attribution 较弱，因此不能支持相同 process-level conclusions。

Analyzer 直接尊重 Graph 的 `causal` metadata，不会把 weaker evidence 升级。

## Output

Report 包含：

- analysis schema version
- session ID
- finding count
- severity counts
- explicit limitations
- rule ID
- title / summary
- related node IDs
- related edge IDs
- evidence event IDs
- rule-specific attributes

Delegated finding 另外包含 process chain、delegation-hop count、spawn sequences，以及对 data inheritance/IPC/data flow 的 explicit negative guarantees。

## Provider semantic / inferred edges

Provider semantic evidence 与 `CORRELATED_WITH_PROCESS` inferred bridge 可以出现在 execution graph 中，但 analysis rule 不应把 `inferred: true / causal: false` bridge 当成 OS-observed process causality。Viewer 的 **observed only** 可以用来完全排除 inferred edge 后再检查 runtime neighborhood。

## 后续 analysis layers

可能加入：

- credential / secret entity resolution
- DNS/domain correlation
- explicit IPC edges
- environment-variable / inherited-handle provenance
- 更完整 Agent/Tool/MCP context
- anomaly detection
- attack-path ranking
- byte-level data-flow / taint tracking
- runtime allow / warn / block policy

这些能力都必须持续区分 observed evidence、inferred risk、process lineage 与 proven causal data flow。
